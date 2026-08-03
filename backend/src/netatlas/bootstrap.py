"""Composition root: schema bootstrap and admin seeding."""

from __future__ import annotations

import logging
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.config import get_settings
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
            "name": "Firewall deny noise",
            "description": "Ideco/firewall deny messages",
            "severity": "warning",
            "kind": "syslog_match",
            "expression": {"category": "firewall"},
            "notify_smtp": False,
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
                status="ok",
            )
        )
        logger.info("Seeded default trigger name=%s", item["name"])
