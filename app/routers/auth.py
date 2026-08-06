import hmac
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from app.auth import create_access_token, generate_otp, hash_otp
from app.config import settings
from app.db import get_allowed_emails_collection, get_otp_collection
from app.graph_mailer import send_mail
from app.schemas import MessageResponse, OTPRequest, OTPVerify, TokenResponse

router = APIRouter(prefix="/auth")
logger = logging.getLogger(__name__)

GENERIC_OTP_MESSAGE = "If this email is registered, an OTP has been sent."


async def send_otp_email(to_email: str, otp: str) -> None:
    await send_mail(
        to_email,
        "Your login code",
        f"Your one-time code is {otp}. It expires in {settings.otp_ttl_minutes} minutes.",
    )


@router.post("/request-otp", response_model=MessageResponse)
async def request_otp(payload: OTPRequest, request: Request) -> MessageResponse:
    email = payload.email.lower()

    allowed = await get_allowed_emails_collection(request.app).find_one({"email": email})
    if allowed:
        otp_collection = get_otp_collection(request.app)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        existing = await otp_collection.find_one({"email": email})
        cooldown = timedelta(seconds=settings.otp_resend_cooldown_seconds)
        if not existing or existing["created_at"] <= now - cooldown:
            otp = generate_otp()
            await otp_collection.replace_one(
                {"email": email},
                {
                    "email": email,
                    "otp_hash": hash_otp(email, otp),
                    "expires_at": now + timedelta(minutes=settings.otp_ttl_minutes),
                    "attempts": 0,
                    "consumed": False,
                    "created_at": now,
                },
                upsert=True,
            )
            try:
                await send_otp_email(email, otp)
            except Exception:
                logger.exception("Failed to send OTP email to %s", email)

    return MessageResponse(message=GENERIC_OTP_MESSAGE)


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(payload: OTPVerify, request: Request) -> TokenResponse:
    email = payload.email.lower()
    otp_collection = get_otp_collection(request.app)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    doc = await otp_collection.find_one({"email": email})
    invalid = HTTPException(status_code=401, detail="Invalid or expired OTP")

    if (
        not doc
        or doc["consumed"]
        or doc["expires_at"] <= now
        or doc["attempts"] >= settings.otp_max_attempts
    ):
        raise invalid

    if not hmac.compare_digest(hash_otp(email, payload.otp), doc["otp_hash"]):
        await otp_collection.update_one({"email": email}, {"$inc": {"attempts": 1}})
        raise invalid

    consumed = await otp_collection.find_one_and_update(
        {"email": email, "consumed": False},
        {"$set": {"consumed": True}},
    )
    if consumed is None:
        raise invalid

    token = create_access_token(email)
    return TokenResponse(access_token=token, expires_in=settings.jwt_expiry_minutes * 60)
