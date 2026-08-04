"""Auth routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from netatlas.api.deps import CurrentUser, get_current_user, get_db, load_user_roles
from netatlas.config import Settings, get_settings
from netatlas.domain.errors import AuthenticationError
from netatlas.infrastructure.persistence.models import RefreshTokenModel, UserModel
from netatlas.infrastructure.persistence.repositories import SqlAlchemyAuditLogger
from netatlas.infrastructure.security.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/login", response_model=TokenPair)
async def login(
    body: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPair:
    user = (
        await session.execute(select(UserModel).where(UserModel.username == body.username))
    ).scalar_one_or_none()
    if user is None or not verify_password(user.password_hash, body.password) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    roles, permissions = await load_user_roles(session, user.id)
    access = create_access_token(
        user_id=user.id,
        username=user.username,
        roles=roles,
        permissions=sorted(permissions),
        private_key_pem=settings.jwt_private_key_pem.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        ttl_seconds=settings.access_token_ttl_seconds,
    )
    refresh, jti = create_refresh_token(
        user_id=user.id,
        private_key_pem=settings.jwt_private_key_pem.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        ttl_seconds=settings.refresh_token_ttl_seconds,
    )
    session.add(
        RefreshTokenModel(
            id=uuid4(),
            user_id=user.id,
            jti=jti,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds),
        )
    )
    user.last_login_at = datetime.now(UTC)
    await SqlAlchemyAuditLogger(session).log(
        actor_user_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=str(user.id),
        source_ip=request.client.host if request.client else None,
    )
    await session.commit()
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_ttl_seconds,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPair:
    try:
        payload = decode_token(
            body.refresh_token,
            public_key_pem=settings.jwt_public_key_pem.get_secret_value(),
            algorithm=settings.jwt_algorithm,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc) or "Invalid refresh token") from exc
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    jti = payload["jti"]
    stored = (
        await session.execute(select(RefreshTokenModel).where(RefreshTokenModel.jti == jti))
    ).scalar_one_or_none()
    if stored is None or stored.revoked_at is not None or stored.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Refresh token revoked or expired")
    stored.revoked_at = datetime.now(UTC)
    user_id = UUID(payload["sub"])
    user = await session.get(UserModel, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive")
    roles, permissions = await load_user_roles(session, user.id)
    access = create_access_token(
        user_id=user.id,
        username=user.username,
        roles=roles,
        permissions=sorted(permissions),
        private_key_pem=settings.jwt_private_key_pem.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        ttl_seconds=settings.access_token_ttl_seconds,
    )
    refresh_token, new_jti = create_refresh_token(
        user_id=user.id,
        private_key_pem=settings.jwt_private_key_pem.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        ttl_seconds=settings.refresh_token_ttl_seconds,
    )
    session.add(
        RefreshTokenModel(
            id=uuid4(),
            user_id=user.id,
            jti=new_jti,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds),
        )
    )
    await session.commit()
    return TokenPair(
        access_token=access,
        refresh_token=refresh_token,
        expires_in=settings.access_token_ttl_seconds,
    )


@router.post("/logout")
async def logout(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str]:
    try:
        payload = decode_token(
            body.refresh_token,
            public_key_pem=settings.jwt_public_key_pem.get_secret_value(),
            algorithm=settings.jwt_algorithm,
        )
    except AuthenticationError:
        return {"status": "ok"}
    jti = payload.get("jti")
    stored = (
        await session.execute(select(RefreshTokenModel).where(RefreshTokenModel.jti == jti))
    ).scalar_one_or_none()
    if stored:
        stored.revoked_at = datetime.now(UTC)
        await session.commit()
    return {"status": "ok"}


@router.get("/me")
async def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "username": user.username,
        "roles": user.roles,
        "permissions": sorted(user.permissions),
    }
