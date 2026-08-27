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
REFRESH = "refresh"


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


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(*, user_id: str, role: str, session_id: str) -> tuple[str, datetime]:
    now = utcnow()
    expires_at = now + timedelta(minutes=settings.access_token_ttl_minutes)
    token = _encode(
        {
            "sub": user_id,
            "sid": session_id,
            "role": role,
            "typ": ACCESS,
            "jti": uuid.uuid4().hex,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
    )
    return token, expires_at


def create_refresh_token(
    *, user_id: str, session_id: str, absolute_expires_at: datetime
) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at). Never outlives the session's absolute expiry."""
    now = utcnow()
    expires_at = min(now + timedelta(hours=settings.refresh_token_ttl_hours), absolute_expires_at)
    jti = uuid.uuid4().hex
    token = _encode(
        {
            "sub": user_id,
            "sid": session_id,
            "typ": REFRESH,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
    )
    return token, jti, expires_at


def decode_token(token: str, *, expected_type: str) -> dict[str, Any] | None:
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
