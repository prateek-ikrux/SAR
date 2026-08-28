from __future__ import annotations

from fastapi import Response

from app.config import settings


def _common(path: str) -> dict:
    kwargs: dict = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": path,
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    return kwargs


def set_access_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    response.set_cookie(settings.access_cookie_name, token, max_age=max_age_seconds, **_common("/"))


def set_csrf_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    """Readable by JavaScript on purpose: the frontend echoes it back in a header."""
    kwargs = _common("/")
    kwargs["httponly"] = False
    response.set_cookie(settings.csrf_cookie_name, token, max_age=max_age_seconds, **kwargs)


def clear_auth_cookies(response: Response) -> None:
    """Drops the cookies in this browser.

    The token itself stays valid until it expires - there is no server-side
    record to revoke.
    """
    domain = settings.cookie_domain
    response.delete_cookie(settings.access_cookie_name, path="/", domain=domain)
    response.delete_cookie(settings.csrf_cookie_name, path="/", domain=domain)
