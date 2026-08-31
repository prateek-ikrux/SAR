from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import settings

_hasher = PasswordHasher()

ACCESS = "access"


def hash_secret(secret: str) -> str:
    """Argon2id hash. Used for one-time codes - there are no passwords here."""
    return _hasher.hash(secret)


def verify_secret(secret: str, secret_hash: str) -> bool:
    try:
        _hasher.verify(secret_hash, secret)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def new_otp_code(length: int) -> str:
    """A numeric code, uniformly random, never starting with a leading zero run
    that would make it look shorter when a mail client trims it."""
    first = secrets.choice("123456789")
    rest = "".join(secrets.choice("0123456789") for _ in range(length - 1))
    return first + rest


def utcnow() -> datetime:
    return datetime.now(UTC)


def create_access_token(*, user_id: str, role: str) -> tuple[str, datetime]:
    """The only token this service issues. Stateless: once signed it is valid
    until it expires."""
    now = utcnow()
    expires_at = now + timedelta(hours=settings.access_token_ttl_hours)
    token = jwt.encode(
        {
            "sub": user_id,
            "role": role,
            "typ": ACCESS,
            "jti": uuid.uuid4().hex,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at


def decode_token(token: str, *, expected_type: str = ACCESS) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != expected_type:
        return None
    return payload
