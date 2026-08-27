from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from app import db
from app.config import settings
from app.security import hash_secret, new_otp_code, utcnow, verify_secret
from app.services import mailer

log = logging.getLogger(__name__)


class OtpError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _normalise(email: str) -> str:
    return email.strip().lower()


async def request_code(*, email: str, ip: str | None, user_agent: str | None) -> None:
    """Mail a sign-in code, if the address belongs to an active account.

    Whether it does is never revealed: an unknown or deactivated address returns
    exactly as an accepted one does. Only genuine abuse (too many requests) and
    mail-delivery failures produce a different answer.
    """
    address = _normalise(email)
    now = utcnow()

    recent = await db.otp_codes().find_one({"email": address}, sort=[("created_at", -1)])
    if recent and recent["created_at"] > now - timedelta(seconds=settings.otp_resend_cooldown_seconds):
        wait = settings.otp_resend_cooldown_seconds - int((now - recent["created_at"]).total_seconds())
        raise OtpError(f"A code was just sent. Try again in {max(wait, 1)} seconds.", status_code=429)

    issued_last_hour = await db.otp_codes().count_documents(
        {"email": address, "created_at": {"$gt": now - timedelta(hours=1)}}
    )
    if issued_last_hour >= settings.otp_max_per_hour:
        raise OtpError("Too many sign-in codes requested. Try again later.", status_code=429)

    user = await db.users().find_one({"email": address})
    if not user or not user.get("active", True):
        # Record the attempt so the rate limits above cannot be sidestepped by
        # cycling through addresses, but send nothing.
        await db.otp_codes().insert_one(
            {
                "email": address,
                "code_hash": None,
                "created_at": now,
                "expires_at": now + timedelta(minutes=settings.otp_ttl_minutes),
                "attempts": 0,
                "consumed_at": None,
                "ip": ip,
                "user_agent": (user_agent or "")[:300] or None,
                "delivered": False,
            }
        )
        log.info("otp requested for unknown or inactive address", extra={"email": address, "ip": ip})
        return

    code = new_otp_code(settings.otp_length)

    # Any earlier live code is retired, so only the newest one works.
    await db.otp_codes().update_many(
        {"email": address, "consumed_at": None}, {"$set": {"consumed_at": now, "superseded": True}}
    )
    await db.otp_codes().insert_one(
        {
            "email": address,
            "user_id": user["_id"],
            "code_hash": hash_secret(code),
            "created_at": now,
            "expires_at": now + timedelta(minutes=settings.otp_ttl_minutes),
            "attempts": 0,
            "consumed_at": None,
            "ip": ip,
            "user_agent": (user_agent or "")[:300] or None,
            "delivered": True,
        }
    )

    if not settings.graph_configured and settings.otp_log_code_when_mail_unconfigured:
        log.warning(
            "MAIL NOT CONFIGURED - sign-in code for %s is %s (development only)",
            address,
            code,
            extra={"email": address},
        )
        return

    html_body, text_body = mailer.render_code_email(code=code, ttl_minutes=settings.otp_ttl_minutes)
    try:
        await mailer.send_mail(
            to=address,
            subject=f"{code} is your ikrux Candidate Search sign-in code",
            html_body=html_body,
            text_body=text_body,
        )
    except mailer.MailError as exc:
        # The code is already stored; invalidate it so a failed send cannot leave
        # a live credential behind that nobody received.
        await db.otp_codes().update_many(
            {"email": address, "consumed_at": None},
            {"$set": {"consumed_at": utcnow(), "send_failed": True}},
        )
        raise OtpError(exc.message, status_code=exc.status_code) from exc


async def verify_code(*, email: str, code: str) -> dict[str, Any]:
    """Consume a code and return the user it belongs to."""
    address = _normalise(email)
    now = utcnow()
    invalid = OtpError("That code is not valid. Request a new one.", status_code=401)

    record = await db.otp_codes().find_one(
        {"email": address, "consumed_at": None, "expires_at": {"$gt": now}},
        sort=[("created_at", -1)],
    )
    if not record or not record.get("code_hash"):
        raise invalid

    attempts = record.get("attempts", 0) + 1
    if attempts > settings.otp_max_attempts:
        await db.otp_codes().update_one(
            {"_id": record["_id"]}, {"$set": {"consumed_at": now, "exhausted": True}}
        )
        raise OtpError("Too many incorrect attempts. Request a new code.", status_code=429)

    if not verify_secret(code.strip(), record["code_hash"]):
        await db.otp_codes().update_one({"_id": record["_id"]}, {"$set": {"attempts": attempts}})
        log.info("otp verification failed", extra={"email": address, "attempt": attempts})
        raise invalid

    user = await db.users().find_one({"_id": record["user_id"]})
    if not user or not user.get("active", True):
        await db.otp_codes().update_one({"_id": record["_id"]}, {"$set": {"consumed_at": now}})
        raise OtpError("This account is no longer active.", status_code=403)

    await db.otp_codes().update_one(
        {"_id": record["_id"]}, {"$set": {"consumed_at": now, "attempts": attempts}}
    )
    await db.users().update_one({"_id": user["_id"]}, {"$set": {"last_login_at": now}})
    user["last_login_at"] = now
    return user
