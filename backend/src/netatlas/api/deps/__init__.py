"""API dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.config import Settings, get_settings
from netatlas.infrastructure.persistence.models import RoleModel, UserModel, UserRoleModel
from netatlas.infrastructure.persistence.session import get_session
from netatlas.infrastructure.security.auth import decode_token
from netatlas.infrastructure.security.rbac import ROLE_PERMISSIONS
from netatlas.infrastructure.security.vault import AesGcmSecretVault


@dataclass(slots=True)
class CurrentUser:
    id: UUID
    username: str
    roles: list[str]
    permissions: set[str]


async def get_db(session: Annotated[AsyncSession, Depends(get_session)]) -> AsyncSession:
    return session


def get_vault(settings: Annotated[Settings, Depends(get_settings)]) -> AesGcmSecretVault:
    return AesGcmSecretVault(settings.master_key_b64.get_secret_value())


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(
        token,
        public_key_pem=settings.jwt_public_key_pem.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    user_id = UUID(payload["sub"])
    user = await session.get(UserModel, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    roles = list(payload.get("roles") or [])
    permissions = set(payload.get("permissions") or [])
    request.state.user_id = user_id
    return CurrentUser(id=user.id, username=user.username, roles=roles, permissions=permissions)


def require_permission(code: str):
    async def _checker(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if code not in user.permissions and "admin" not in user.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission {code}")
        return user

    return _checker


async def load_user_roles(session: AsyncSession, user_id: UUID) -> tuple[list[str], set[str]]:
    rows = (
        await session.execute(
            select(RoleModel.name)
            .join(UserRoleModel, UserRoleModel.role_id == RoleModel.id)
            .where(UserRoleModel.user_id == user_id)
        )
    ).scalars().all()
    roles = list(rows)
    permissions: set[str] = set()
    for role in roles:
        permissions |= set(ROLE_PERMISSIONS.get(role, frozenset()))
    return roles, permissions


def device_to_dict(device: Any) -> dict[str, Any]:
    return {
        "id": str(device.id),
        "hostname": device.hostname,
        "vendor": device.vendor,
        "model": device.model,
        "serial": device.serial,
        "firmware": device.firmware,
        "os_version": device.os_version,
        "management_ip": device.management_ip,
        "management_mac": device.management_mac,
        "platform": device.platform.value if hasattr(device.platform, "value") else device.platform,
        "status": device.status.value if hasattr(device.status, "value") else device.status,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
    }
