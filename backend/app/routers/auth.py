from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from app import db
from app.config import settings
from app.dependencies import CurrentUser, bearer_token, client_ip
from app.models import (
    LoginResponse,
    RefreshRequest,
    RequestCodeRequest,
    RequestCodeResponse,
    SessionOut,
    UserOut,
    VerifyCodeRequest,
)
from app.security import ACCESS, REFRESH, decode_token, new_csrf_token, utcnow
from app.services import auth_service, otp_service
from app.services.cookies import clear_auth_cookies, set_access_cookie, set_csrf_cookie, set_refresh_cookie

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _seconds_until(moment) -> int:
    return max(int((moment - utcnow()).total_seconds()), 0)


def _issue(
    response: Response,
    tokens: dict[str, Any],
    user: dict[str, Any],
    *,
    keep_csrf: str | None = None,
) -> LoginResponse:
    """Hand the session to the client over whichever transport is configured.

    ``keep_csrf`` carries the existing CSRF token through a refresh. Rotating it
    would buy nothing - it is not a bearer credential, it only proves the request
    came from our own JavaScript - while breaking any request that was already in
    flight when a background refresh happened.
    """
    csrf = keep_csrf or new_csrf_token()
    if settings.uses_cookies:
        session_seconds = _seconds_until(tokens["absolute_expires_at"])
        set_access_cookie(response, tokens["access_token"], _seconds_until(tokens["access_expires_at"]))
        set_refresh_cookie(response, tokens["refresh_token"], _seconds_until(tokens["refresh_expires_at"]))
        set_csrf_cookie(response, csrf, session_seconds)

    return LoginResponse(
        user=UserOut(**auth_service.serialize_user(user)),
        csrf_token=csrf,
        access_token_expires_at=tokens["access_expires_at"],
        session_expires_at=tokens["absolute_expires_at"],
        access_token=tokens["access_token"] if settings.uses_bearer else None,
        refresh_token=tokens["refresh_token"] if settings.uses_bearer else None,
        token_type="Bearer" if settings.uses_bearer else None,
    )


def _incoming_refresh_token(request: Request, body: RefreshRequest | None) -> str | None:
    if settings.uses_bearer and body and body.refresh_token:
        return body.refresh_token
    if settings.uses_cookies:
        return request.cookies.get(settings.refresh_cookie_name)
    return None


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
    """Step 2 of sign-in: exchange a valid code for a session."""
    ip = client_ip(request)
    try:
        auth_service.check_login_rate_limit(ip)
        user = await otp_service.verify_code(email=payload.email, code=payload.code)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except otp_service.OtpError as exc:
        log.info("code verification rejected", extra={"email": payload.email, "ip": ip})
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    tokens = await auth_service.start_session(user=user, ip=ip, user_agent=request.headers.get("user-agent"))
    log.info("sign-in succeeded", extra={"user_id": str(user["_id"]), "session_id": tokens["session_id"]})
    return _issue(response, tokens, user)


@router.post("/refresh", response_model=LoginResponse)
async def refresh(request: Request, response: Response, body: RefreshRequest | None = None) -> LoginResponse:
    token = _incoming_refresh_token(request, body)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    payload = decode_token(token, expected_type=REFRESH)
    if not payload:
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is invalid")

    try:
        result = await auth_service.rotate_session(payload=payload)
    except auth_service.AuthError as exc:
        clear_auth_cookies(response)
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return _issue(response, result, result["user"], keep_csrf=request.cookies.get(settings.csrf_cookie_name))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, body: RefreshRequest | None = None) -> Response:
    token = _incoming_refresh_token(request, body)
    payload = decode_token(token, expected_type=REFRESH) if token else None
    if payload and payload.get("sid"):
        await auth_service.revoke_session(payload["sid"], reason="logout")
    elif settings.uses_bearer:
        # Bearer clients may only still hold the access token; its `sid` is
        # enough to revoke the session, so logout works either way.
        access = bearer_token(request)
        access_payload = decode_token(access, expected_type=ACCESS) if access else None
        if access_payload and access_payload.get("sid"):
            await auth_service.revoke_session(access_payload["sid"], reason="logout")
    clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user: CurrentUser, response: Response) -> Response:
    revoked = await auth_service.revoke_all_sessions(user["_id"], reason="logout_all")
    clear_auth_cookies(response)
    log.info("all sessions revoked", extra={"user_id": str(user["_id"]), "revoked": revoked})
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut(**auth_service.serialize_user(user))


@router.get("/sessions", response_model=list[SessionOut])
async def my_sessions(user: CurrentUser) -> list[SessionOut]:
    docs = (
        await db.sessions()
        .find({"user_id": user["_id"], "revoked_at": None, "absolute_expires_at": {"$gt": utcnow()}})
        .sort("created_at", -1)
        .to_list(length=50)
    )

    return [
        SessionOut(
            id=str(doc["_id"]),
            created_at=doc["created_at"],
            last_used_at=doc["last_used_at"],
            absolute_expires_at=doc["absolute_expires_at"],
            ip=doc.get("ip"),
            user_agent=doc.get("user_agent"),
            current=str(doc["_id"]) == user.get("_session_id"),
        )
        for doc in docs
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_one_session(session_id: str, user: CurrentUser, response: Response) -> Response:
    session = await db.sessions().find_one({"_id": auth_service.to_object_id(session_id)})
    if not session or session["user_id"] != user["_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    await auth_service.revoke_session(session["_id"], reason="revoked_by_user")
    if session_id == user.get("_session_id"):
        clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
