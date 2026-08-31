from __future__ import annotations

import logging
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app import db
from app.config import settings
from app.security import create_access_token, utcnow
from app.services import rate_limit

log = logging.getLogger(__name__)


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# --------------------------------------------------------------------- rate limiting
def check_login_rate_limit(ip: str) -> None:
    """Per-IP ceiling on sign-in traffic.

    Tighter than the app-wide per-IP limit because sign-in is the one place an
    anonymous caller can make the server do expensive work - an Argon2 hash and
    an outbound mail send. The per-address limits in otp_service sit underneath
    this and are the ones that actually bound code guessing.
    """
    rate_limit.check(
        key=f"login:{ip}",
        limit=settings.login_rate_limit_per_minute,
        window_seconds=60,
        message="Too many sign-in attempts. Try again in a minute.",
    )


# --------------------------------------------------------------------- helpers
def to_object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise AuthError("Invalid identifier", status_code=400) from None


def serialize_user(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "email": doc["email"],
        "name": doc.get("name", ""),
        "role": doc.get("role", "recruiter"),
        "active": doc.get("active", True),
        "created_at": doc.get("created_at"),
        "last_login_at": doc.get("last_login_at"),
    }


async def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    return await db.users().find_one({"_id": to_object_id(user_id)})


async def create_user(*, email: str, name: str, role: str) -> dict[str, Any]:
    """Create an account. There is no credential to set - access is proven by
    receiving a one-time code at this address."""
    doc: dict[str, Any] = {
        "email": email.strip().lower(),
        "name": name.strip(),
        "role": role,
        "active": True,
        "created_at": utcnow(),
        "last_login_at": None,
    }
    result = await db.users().insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


# --------------------------------------------------------------------- tokens
def issue_access_token(user: dict[str, Any]) -> dict[str, Any]:
    """Mint the single access token this service uses.

    Nothing is written to the database: the token is self-contained and stays
    valid until it expires. Access is still withdrawn immediately when an account
    is deactivated or deleted, because every authenticated request re-reads the
    user - but an individual token cannot be revoked on its own.
    """
    token, expires_at = create_access_token(user_id=str(user["_id"]), role=user.get("role", "recruiter"))
    log.info(
        "access token issued",
        extra={"user_id": str(user["_id"]), "expires_at": expires_at.isoformat()},
    )
    return {"access_token": token, "expires_at": expires_at}
