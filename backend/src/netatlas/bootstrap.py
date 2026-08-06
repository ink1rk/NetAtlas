"""Composition root: schema bootstrap and admin seeding."""

from __future__ import annotations

import logging
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.config import get_settings
import netatlas.infrastructure.persistence.models  # noqa: F401 — register all ORM tables
from netatlas.infrastructure.persistence.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
    UserRoleModel,
)
from netatlas.infrastructure.persistence.models.base import Base
from netatlas.infrastructure.persistence.session import SessionLocal, engine
from netatlas.infrastructure.security.auth import hash_password
from netatlas.infrastructure.security.rbac import PERMISSIONS, ROLE_PERMISSIONS

logger = logging.getLogger(__name__)

# create_all does not ALTER existing tables — patch columns added after first install.
_SCHEMA_PATCHES = (
    """
    CREATE TABLE IF NOT EXISTS discovery_seeds (
        id UUID PRIMARY KEY,
        target VARCHAR(64) NOT NULL,
        label VARCHAR(128),
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        credential_profile_ids VARCHAR[] NOT NULL DEFAULT '{}',
        options JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS discovery_jobs (
        id UUID PRIMARY KEY,
        status VARCHAR(32) NOT NULL DEFAULT 'pending',
        started_at TIMESTAMPTZ,
        finished_at TIMESTAMPTZ,
        config JSONB NOT NULL DEFAULT '{}'::jsonb,
        stats JSONB NOT NULL DEFAULT '{}'::jsonb,
        error TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "ALTER TABLE discovery_seeds ADD COLUMN IF NOT EXISTS credential_profile_ids VARCHAR[] NOT NULL DEFAULT '{}'",
    "ALTER TABLE discovery_seeds ADD COLUMN IF NOT EXISTS options JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE discovery_seeds ADD COLUMN IF NOT EXISTS label VARCHAR(128)",
    "ALTER TABLE discovery_seeds ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE discovery_jobs ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE discovery_jobs ADD COLUMN IF NOT EXISTS stats JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE discovery_jobs ADD COLUMN IF NOT EXISTS error TEXT",
    "ALTER TABLE discovery_jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ",
    "ALTER TABLE discovery_jobs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ",
    "ALTER TABLE discovery_jobs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    # Device Intelligence columns (additive; safe on existing installs)
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS network_role VARCHAR(32) NOT NULL DEFAULT 'unknown'",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS role_confidence DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS role_reasons JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS role_source VARCHAR(16) NOT NULL DEFAULT 'auto'",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS location VARCHAR(255)",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS rack VARCHAR(128)",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS owner VARCHAR(128)",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS criticality VARCHAR(32) NOT NULL DEFAULT 'normal'",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS description TEXT",
    "CREATE INDEX IF NOT EXISTS ix_devices_network_role ON devices (network_role)",
)


async def _apply_schema_patches(conn) -> None:  # type: ignore[no-untyped-def]
    for stmt in _SCHEMA_PATCHES:
        await conn.execute(text(stmt))
    logger.info("Schema patches applied for discovery tables")


def ensure_jwt_keys() -> None:
    settings = get_settings()
    if settings.jwt_private_key_pem.get_secret_value() and settings.jwt_public_key_pem.get_secret_value():
        return
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    # Mutate cached settings for process lifetime when installer did not inject keys.
    object.__setattr__(settings, "jwt_private_key_pem", type(settings.jwt_private_key_pem)(private_pem))
    object.__setattr__(settings, "jwt_public_key_pem", type(settings.jwt_public_key_pem)(public_pem))
    logger.warning("JWT keys were generated in-process; persist NETATLAS_JWT_* for production")


async def startup() -> None:
    settings = get_settings()
    ensure_jwt_keys()
    if not settings.master_key_b64.get_secret_value():
        import base64
        import os

        generated = base64.b64encode(os.urandom(32)).decode()
        object.__setattr__(settings, "master_key_b64", type(settings.master_key_b64)(generated))
        logger.warning("Master key generated in-process; persist NETATLAS_MASTER_KEY_B64")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _apply_schema_patches(conn)

    async with SessionLocal() as session:
        # Seed permissions
        existing_perms = {
            r.code: r for r in (await session.execute(select(PermissionModel))).scalars().all()
        }
        for perm in PERMISSIONS:
            if perm.code not in existing_perms:
                session.add(PermissionModel(id=uuid4(), code=perm.code, description=perm.description))
        await session.flush()
        perms = {r.code: r for r in (await session.execute(select(PermissionModel))).scalars().all()}

        # Seed roles
        existing_roles = {r.name: r for r in (await session.execute(select(RoleModel))).scalars().all()}
        for role_name, codes in ROLE_PERMISSIONS.items():
            role = existing_roles.get(role_name)
            if role is None:
                role = RoleModel(id=uuid4(), name=role_name, description=f"{role_name} role")
                session.add(role)
                await session.flush()
                existing_roles[role_name] = role
            for code in codes:
                perm = perms[code]
                exists = (
                    await session.execute(
                        select(RolePermissionModel).where(
                            RolePermissionModel.role_id == role.id,
                            RolePermissionModel.permission_id == perm.id,
                        )
                    )
                ).scalar_one_or_none()
                if not exists:
                    session.add(RolePermissionModel(id=uuid4(), role_id=role.id, permission_id=perm.id))

        # Bootstrap admin
        admin_password = settings.bootstrap_admin_password.get_secret_value() or "ChangeMeNow!NetAtlas"
        admin = (
            await session.execute(
                select(UserModel).where(UserModel.username == settings.bootstrap_admin_username)
            )
        ).scalar_one_or_none()
        if admin is None:
            admin = UserModel(
                id=uuid4(),
                username=settings.bootstrap_admin_username,
                email=settings.bootstrap_admin_email,
                password_hash=hash_password(admin_password),
                is_active=True,
            )
            session.add(admin)
            await session.flush()
            admin_role = existing_roles["admin"]
            session.add(UserRoleModel(id=uuid4(), user_id=admin.id, role_id=admin_role.id))
            logger.info("Bootstrap admin user created username=%s", admin.username)

        await _seed_default_triggers(session)
        await session.commit()


async def _seed_default_triggers(session: AsyncSession) -> None:
    from netatlas.infrastructure.persistence.models import TriggerDefinitionModel

    defaults = [
        {
            "name": "High CPU",
            "description": "CPU percent above 90 for 5 minutes",
            "severity": "high",
            "kind": "metric_threshold",
            "expression": {"metric": "cpu_percent", "op": "gt", "threshold": 90, "for_minutes": 5},
        },
        {
            "name": "High Memory",
            "description": "Memory percent above 90 for 5 minutes (HOST-RESOURCES-MIB)",
            "severity": "high",
            "kind": "metric_threshold",
            "expression": {"metric": "memory_percent", "op": "gt", "threshold": 90, "for_minutes": 5},
        },
        {
            "name": "Interfaces down count",
            "description": "More than 0 interfaces with ifOperStatus=down",
            "severity": "average",
            "kind": "metric_threshold",
            "expression": {"metric": "interfaces_down", "op": "gt", "threshold": 0, "for_minutes": 2},
        },
        {
            "name": "Interface operationally down",
            "description": "Admin-up interface with oper-status down",
            "severity": "average",
            "kind": "interface_status",
            "expression": {},
        },
        {
            "name": "Auth failure burst",
            "description": "SIEM correlation: >=5 auth failures in 5 minutes",
            "severity": "high",
            "kind": "siem_correlation",
            "expression": {"category": "auth_failure", "count": 5, "for_minutes": 5},
        },
        {
            "name": "Syslog critical",
            "description": "Any syslog severity <= 2 (critical/alert/emergency)",
            "severity": "disaster",
            "kind": "syslog_match",
            "expression": {"min_severity": 2},
        },
        {
            "name": "Ideco firewall deny",
            "description": "Ideco UTM firewall deny/block (category=firewall)",
            "severity": "warning",
            "kind": "syslog_match",
            "expression": {"category": "firewall"},
            "notify_smtp": True,
            "notify_telegram": True,
            "notify_element": True,
        },
        {
            "name": "Ideco VPN event",
            "description": "VPN up/down or auth on Ideco edge",
            "severity": "average",
            "kind": "syslog_match",
            "expression": {"category": "vpn"},
        },
        {
            "name": "Eltex link down",
            "description": "Eltex MES/ESR interface link-down syslog",
            "severity": "high",
            "kind": "syslog_match",
            "expression": {"category": "link_down", "regex": r"(?i)(interface|gi|te|fa|link).*(down)|LINK-3-UPDOWN"},
        },
        {
            "name": "Eltex STP topology change",
            "description": "Spanning-tree topology change on Eltex",
            "severity": "warning",
            "kind": "syslog_match",
            "expression": {"category": "stp"},
            "notify_smtp": False,
        },
        {
            "name": "Config change audit",
            "description": "Possible configuration change in syslog",
            "severity": "average",
            "kind": "syslog_match",
            "expression": {"category": "config_change"},
        },
    ]
    for item in defaults:
        exists = (
            await session.execute(
                select(TriggerDefinitionModel).where(TriggerDefinitionModel.name == item["name"])
            )
        ).scalar_one_or_none()
        if exists:
            continue
        session.add(
            TriggerDefinitionModel(
                id=uuid4(),
                name=item["name"],
                description=item["description"],
                enabled=True,
                severity=item["severity"],
                kind=item["kind"],
                expression=item["expression"],
                notify_smtp=item.get("notify_smtp", True),
                notify_telegram=item.get("notify_telegram", True),
                notify_element=item.get("notify_element", True),
                status="ok",
            )
        )
        logger.info("Seeded default trigger name=%s", item["name"])
