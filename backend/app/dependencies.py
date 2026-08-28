from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status

from app.config import settings
from app.security import ACCESS, decode_token
from app.services import auth_service


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return None


def access_token(request: Request) -> str | None:
    """Pull the access token from whichever transport this deployment uses.

    The header is checked first so that a browser holding a stale cookie cannot
    shadow an explicit Authorization header.
    """
    if settings.uses_bearer:
        token = bearer_token(request)
        if token:
            return token
    if settings.uses_cookies:
        return request.cookies.get(settings.access_cookie_name)
    return None


async def current_user(request: Request) -> dict[str, Any]:
    token = access_token(request)
    if not token:
        raise _unauthorized("Not authenticated")

    payload = decode_token(token, expected_type=ACCESS)
    if not payload:
        raise _unauthorized("Your session has expired. Please sign in again.")

    # The token is self-contained, but the account behind it is still read on
    # every request. That is what makes deactivating or deleting a user take
    # effect immediately, and it keeps `role` authoritative in the database
    # rather than frozen into a token issued up to 24 hours ago.
    user = await auth_service.get_user_by_id(payload["sub"])
    if not user:
        raise _unauthorized("This account no longer exists.")
    if not user.get("active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is not active")

    return user


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]


def require_role(*roles: str):
    async def _guard(user: CurrentUser) -> dict[str, Any]:
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return _guard


AdminUser = Annotated[dict[str, Any], Depends(require_role("admin"))]


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
