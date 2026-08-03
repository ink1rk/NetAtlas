"""Password hashing and JWT helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from netatlas.domain.errors import AuthenticationError


_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(
    *,
    user_id: UUID,
    username: str,
    roles: list[str],
    permissions: list[str],
    private_key_pem: str,
    algorithm: str,
    ttl_seconds: int,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "username": username,
        "roles": roles,
        "permissions": permissions,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, private_key_pem, algorithm=algorithm)


def create_refresh_token(
    *,
    user_id: UUID,
    private_key_pem: str,
    algorithm: str,
    ttl_seconds: int,
) -> tuple[str, str]:
    now = datetime.now(UTC)
    jti = str(uuid4())
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "jti": jti,
    }
    token = jwt.encode(payload, private_key_pem, algorithm=algorithm)
    return token, jti


def decode_token(token: str, *, public_key_pem: str, algorithm: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, public_key_pem, algorithms=[algorithm])
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired token") from exc
