from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.dependencies import CurrentUser, client_ip
from app.models import LoginResponse, RequestCodeRequest, RequestCodeResponse, UserOut, VerifyCodeRequest
from app.services import auth_service, otp_service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request-code", response_model=RequestCodeResponse)
async def request_code(payload: RequestCodeRequest, request: Request) -> RequestCodeResponse:
    """Step 1 of sign-in: mail a one-time code.

    The reply is identical whether or not the address has an account, so this
    endpoint cannot be used to enumerate staff email addresses.
    """
    ip = client_ip(request)
    auth_service.check_login_rate_limit(ip)
    try:
        await otp_service.request_code(
            email=payload.email, ip=ip, user_agent=request.headers.get("user-agent")
        )
    except otp_service.OtpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return RequestCodeResponse(
        message="If that address has an account, a sign-in code is on its way.",
        expires_in_minutes=settings.otp_ttl_minutes,
        resend_available_in_seconds=settings.otp_resend_cooldown_seconds,
    )


@router.post("/verify-code", response_model=LoginResponse)
async def verify_code(payload: VerifyCodeRequest, request: Request) -> LoginResponse:
    """Step 2 of sign-in: exchange a valid code for a 24 hour access token."""
    ip = client_ip(request)
    auth_service.check_login_rate_limit(ip)
    try:
        user = await otp_service.verify_code(email=payload.email, code=payload.code)
    except otp_service.OtpError as exc:
        log.info("code verification rejected", extra={"email": payload.email, "ip": ip})
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    issued = auth_service.issue_access_token(user)

    log.info("sign-in succeeded", extra={"user_id": str(user["_id"])})
    return LoginResponse(
        user=UserOut(**auth_service.serialize_user(user)),
        access_token=issued["access_token"],
        expires_at=issued["expires_at"],
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut(**auth_service.serialize_user(user))
