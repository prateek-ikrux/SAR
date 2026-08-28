from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.config import settings
from app.dependencies import CurrentUser, client_ip
from app.models import LoginResponse, RequestCodeRequest, RequestCodeResponse, UserOut, VerifyCodeRequest
from app.security import new_csrf_token, utcnow
from app.services import auth_service, otp_service
from app.services.cookies import clear_auth_cookies, set_access_cookie, set_csrf_cookie

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _seconds_until(moment) -> int:
    return max(int((moment - utcnow()).total_seconds()), 0)


@router.post("/request-code", response_model=RequestCodeResponse)
async def request_code(payload: RequestCodeRequest, request: Request) -> RequestCodeResponse:
    """Step 1 of sign-in: mail a one-time code.

    The reply is identical whether or not the address has an account, so this
    endpoint cannot be used to enumerate staff email addresses.
    """
    ip = client_ip(request)
    try:
        auth_service.check_login_rate_limit(ip)
        await otp_service.request_code(
            email=payload.email, ip=ip, user_agent=request.headers.get("user-agent")
        )
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except otp_service.OtpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return RequestCodeResponse(
        message="If that address has an account, a sign-in code is on its way.",
        expires_in_minutes=settings.otp_ttl_minutes,
        resend_available_in_seconds=settings.otp_resend_cooldown_seconds,
    )


@router.post("/verify-code", response_model=LoginResponse)
async def verify_code(payload: VerifyCodeRequest, request: Request, response: Response) -> LoginResponse:
    """Step 2 of sign-in: exchange a valid code for a 24 hour access token."""
    ip = client_ip(request)
    try:
        auth_service.check_login_rate_limit(ip)
        user = await otp_service.verify_code(email=payload.email, code=payload.code)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except otp_service.OtpError as exc:
        log.info("code verification rejected", extra={"email": payload.email, "ip": ip})
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    issued = auth_service.issue_access_token(user)
    lifetime = _seconds_until(issued["expires_at"])
    csrf = new_csrf_token()

    if settings.uses_cookies:
        set_access_cookie(response, issued["access_token"], lifetime)
        set_csrf_cookie(response, csrf, lifetime)

    log.info("sign-in succeeded", extra={"user_id": str(user["_id"])})
    return LoginResponse(
        user=UserOut(**auth_service.serialize_user(user)),
        csrf_token=csrf,
        expires_at=issued["expires_at"],
        access_token=issued["access_token"] if settings.uses_bearer else None,
        token_type="Bearer" if settings.uses_bearer else None,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    """Clears the cookies in this browser.

    There is no server-side session, so the token itself remains valid until it
    expires. A bearer client logs out by discarding its own copy.
    """
    clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut(**auth_service.serialize_user(user))
