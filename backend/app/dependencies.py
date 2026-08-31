from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status

from app.config import settings
from app.security import ACCESS, decode_token
from app.services import auth_service, rate_limit


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def client_ip(request: Request) -> str:
    """The caller's address, as far as it can be trusted.

    X-Forwarded-For is written by the client and only becomes meaningful once a
    proxy you control has appended to it - so it is ignored unless
    TRUST_PROXY_HEADERS says a proxy is definitely in front. Believing it
    unconditionally would let any caller mint a fresh rate-limit bucket per
    request simply by changing a header.

    When it is trusted, the *rightmost* entry is used, not the leftmost: each hop
    appends the address it saw, so the last entry is the one written by our own
    proxy. The left end is whatever the client made up.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
            if hops:
                return hops[-1]
    return request.client.host if request.client else "unknown"


def ip_rate_limit(request: Request) -> None:
    """A coarse ceiling on every endpoint in the app.

    Registered as a global dependency in main.py, so it covers the health probes
    and the sign-in endpoints too - everything a caller can reach without a
    token. The per-user limits below are the ones that matter for an
    authenticated session; this is the outer wall.
    """
    rate_limit.check(
        key=f"ip:{client_ip(request)}",
        limit=settings.rate_limit_per_ip_per_minute,
        window_seconds=60,
        message="Too many requests. Slow down and try again shortly.",
    )


def access_token(request: Request) -> str | None:
    """The bearer token from the Authorization header, if there is one.

    A header is the only transport: the web app keeps its token in localStorage
    and sets this explicitly. Nothing is read from cookies, so no request is
    ever authenticated by an ambient credential - which is what makes CSRF
    protection unnecessary here.
    """
    header = request.headers.get("authorization") or ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return None


async def current_user(request: Request) -> dict[str, Any]:
    token = access_token(request)
    if not token:
        raise _unauthorized("Not authenticated")

    payload = decode_token(token, expected_type=ACCESS)
    if not payload or payload is None:
        raise _unauthorized("Your session has expired. Please sign in again.")

    # Throttle before the database read, not after: a caller hammering the API
    # with a valid token should not cost a query per rejected request.
    #
    # The key is the account, not the address, because that is the threat this
    # limit exists for. A token cannot be revoked before it expires, so if one
    # leaks, capping what it can do per minute is the only brake available - and
    # a per-IP limit would not provide it, since the holder can change address.
    rate_limit.check(
        key=f"user:{payload['sub']}",
        limit=settings.rate_limit_per_user_per_minute,
        window_seconds=60,
        message="Too many requests on this account. Try again shortly.",
    )

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


def rate_limited(bucket: str, limit: int):
    """An authenticated dependency with its own tighter per-account ceiling.

    Layers on top of CurrentUser rather than replacing it, so an endpoint using
    this still gets the full token check and account re-read. FastAPI caches
    dependencies within a request, so `current_user` runs exactly once even
    though it is reached through two paths.
    """

    async def _guard(user: CurrentUser) -> dict[str, Any]:
        rate_limit.check(
            key=f"{bucket}:{user['_id']}",
            limit=limit,
            window_seconds=60,
            message="Too many searches. Give the last one a moment to finish.",
        )
        return user

    return _guard


SearchUser = Annotated[
    dict[str, Any], Depends(rate_limited("search", settings.search_rate_limit_per_minute))
]


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
