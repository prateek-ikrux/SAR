from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque
from datetime import timedelta
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app import db
from app.config import settings
from app.security import create_access_token, create_refresh_token, utcnow

log = logging.getLogger(__name__)


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# --------------------------------------------------------------------- rate limiting
_login_attempts: dict[str, deque] = defaultdict(deque)


def check_login_rate_limit(ip: str) -> None:
    """Per-IP ceiling on sign-in traffic, on top of the per-address limits in otp_service."""
    window_start = time.monotonic() - 60
    bucket = _login_attempts[ip]
    while bucket and bucket[0] < window_start:
        bucket.popleft()
    if len(bucket) >= settings.login_rate_limit_per_minute:
        raise AuthError("Too many sign-in attempts. Try again in a minute.", status_code=429)
    bucket.append(time.monotonic())


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


# --------------------------------------------------------------------- sessions
async def start_session(*, user: dict[str, Any], ip: str | None, user_agent: str | None) -> dict[str, Any]:
    now = utcnow()
    absolute_expires_at = now + timedelta(hours=settings.refresh_token_ttl_hours)
    session_oid = ObjectId()
    session_id = str(session_oid)

    refresh_token, refresh_jti, refresh_expires_at = create_refresh_token(
        user_id=str(user["_id"]), session_id=session_id, absolute_expires_at=absolute_expires_at
    )
    access_token, access_expires_at = create_access_token(
        user_id=str(user["_id"]), role=user.get("role", "recruiter"), session_id=session_id
    )

    await db.sessions().insert_one(
        {
            "_id": session_oid,
            "user_id": user["_id"],
            "family_id": uuid.uuid4().hex,
            "refresh_jti": refresh_jti,
            "created_at": now,
            "last_used_at": now,
            "absolute_expires_at": absolute_expires_at,
            "revoked_at": None,
            "revoked_reason": None,
            "ip": ip,
            "user_agent": (user_agent or "")[:300] or None,
        }
    )

    return {
        "session_id": session_id,
        "access_token": access_token,
        "access_expires_at": access_expires_at,
        "refresh_token": refresh_token,
        "refresh_expires_at": refresh_expires_at,
        "absolute_expires_at": absolute_expires_at,
    }


async def rotate_session(*, payload: dict[str, Any]) -> dict[str, Any]:
    """Consume a refresh token and issue a fresh pair.

    Presenting a refresh token that has already been rotated away is treated as
    theft: the whole session family is revoked immediately.
    """
    session_id = payload.get("sid")
    jti = payload.get("jti")
    if not session_id or not jti:
        raise AuthError("Invalid refresh token")

    session = await db.sessions().find_one({"_id": to_object_id(session_id)})
    if not session:
        raise AuthError("Session not found. Please sign in again.")

    now = utcnow()
    if session.get("revoked_at"):
        raise AuthError("Session has been revoked. Please sign in again.")
    if session["absolute_expires_at"] <= now:
        await revoke_session(session["_id"], reason="expired")
        raise AuthError("Session expired. Please sign in again.")

    if session["refresh_jti"] != jti:
        await db.sessions().update_many(
            {"family_id": session["family_id"], "revoked_at": None},
            {"$set": {"revoked_at": now, "revoked_reason": "refresh_reuse_detected"}},
        )
        log.warning(
            "refresh token reuse detected",
            extra={"session_id": session_id, "user_id": str(session["user_id"])},
        )
        raise AuthError("Session invalidated for security reasons. Please sign in again.")

    user = await db.users().find_one({"_id": session["user_id"]})
    if not user or not user.get("active", True):
        await revoke_session(session["_id"], reason="user_inactive")
        raise AuthError("This account is no longer active.", status_code=403)

    refresh_token, new_jti, refresh_expires_at = create_refresh_token(
        user_id=str(user["_id"]),
        session_id=session_id,
        absolute_expires_at=session["absolute_expires_at"],
    )
    access_token, access_expires_at = create_access_token(
        user_id=str(user["_id"]), role=user.get("role", "recruiter"), session_id=session_id
    )
    await db.sessions().update_one(
        {"_id": session["_id"]}, {"$set": {"refresh_jti": new_jti, "last_used_at": now}}
    )

    return {
        "user": user,
        "session_id": session_id,
        "access_token": access_token,
        "access_expires_at": access_expires_at,
        "refresh_token": refresh_token,
        "refresh_expires_at": refresh_expires_at,
        "absolute_expires_at": session["absolute_expires_at"],
    }


async def revoke_session(session_id: ObjectId | str, *, reason: str) -> None:
    oid = session_id if isinstance(session_id, ObjectId) else to_object_id(session_id)
    await db.sessions().update_one(
        {"_id": oid, "revoked_at": None}, {"$set": {"revoked_at": utcnow(), "revoked_reason": reason}}
    )


async def revoke_all_sessions(user_id: ObjectId, *, reason: str, keep_session_id: str | None = None) -> int:
    query: dict[str, Any] = {"user_id": user_id, "revoked_at": None}
    if keep_session_id:
        query["_id"] = {"$ne": to_object_id(keep_session_id)}
    result = await db.sessions().update_many(
        query, {"$set": {"revoked_at": utcnow(), "revoked_reason": reason}}
    )
    return result.modified_count


async def active_session(session_id: str) -> dict[str, Any] | None:
    return await db.sessions().find_one(
        {"_id": to_object_id(session_id), "revoked_at": None, "absolute_expires_at": {"$gt": utcnow()}}
    )
