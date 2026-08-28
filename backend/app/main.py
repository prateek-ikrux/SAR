from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import ASCENDING, DESCENDING

from app import db
from app.config import settings
from app.dependencies import bearer_token
from app.logging_config import configure_logging, request_id_ctx
from app.routers import auth, health, profiles, search, users
from app.services import mailer

log = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
# Sign-in happens before any session exists, so there is no CSRF token to send yet.
CSRF_EXEMPT_PATHS = {
    f"{settings.api_prefix}/auth/request-code",
    f"{settings.api_prefix}/auth/verify-code",
}


async def ensure_indexes() -> None:
    """Create this application's own indexes. Never touches the ats database."""
    await db.users().create_index([("email", ASCENDING)], unique=True, name="uniq_email")
    await db.otp_codes().create_index([("email", ASCENDING), ("created_at", DESCENDING)], name="by_email")
    # Spent and expired codes are swept an hour later, which is long enough for
    # the per-hour request limit to still see them.
    await db.otp_codes().create_index(
        [("expires_at", ASCENDING)], expireAfterSeconds=3_600, name="ttl_expired_codes"
    )
    log.info("application indexes ensured", extra={"database": settings.mongo_db_app})


def warn_on_auth_misconfiguration() -> None:
    """Catch the cross-site cookie trap at boot rather than in the browser."""
    if settings.uses_cookies and settings.cors_origin_list and settings.cookie_samesite != "none":
        log.warning(
            "CORS origins are configured but cookies are SameSite=%s. That is correct for a "
            "same-site deployment (one origin, or sibling subdomains of ikrux.com). If the "
            "frontend is served from a different registrable domain the browser will drop these "
            "cookies silently - set AUTH_TRANSPORT=bearer, or COOKIE_SAMESITE=none with "
            "COOKIE_SECURE=true.",
            settings.cookie_samesite,
            extra={"cors_origins": settings.cors_origin_list},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    await db.connect()
    await ensure_indexes()
    warn_on_auth_misconfiguration()
    log.info(
        "application started",
        extra={
            "environment": settings.environment,
            "vector_index": settings.vector_index_name,
            "vector_path": settings.vector_path,
            "default_mode": "enn" if settings.search_default_exact else "ann",
            "auth_transport": settings.auth_transport,
            "mail_configured": settings.graph_configured,
            "cookie_samesite": settings.cookie_samesite if settings.uses_cookies else None,
        },
    )
    yield
    await mailer.close()
    await db.disconnect()


app = FastAPI(
    title=settings.app_name,
    description="Vector search and retrieval over the ikrux candidate resume corpus.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=f"{settings.api_prefix}/docs",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    redoc_url=None,
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", settings.csrf_header_name],
    )


# Starlette runs the last-registered middleware outermost, so CSRF is declared
# first and request_context second: every response, CSRF rejections included,
# gets an x-request-id and a log line.
@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    """Double-submit CSRF check on top of SameSite cookies.

    Only cookies are ambient credentials, so this applies only to requests the
    browser authenticates with one. A request carrying an Authorization header
    was made deliberately by JavaScript that already cleared a CORS preflight,
    and needs no CSRF token.
    """
    if (
        settings.csrf_enabled
        and settings.uses_cookies
        and request.method not in SAFE_METHODS
        and request.url.path not in CSRF_EXEMPT_PATHS
        and not bearer_token(request)
    ):
        if settings.access_cookie_name in request.cookies:
            cookie_token = request.cookies.get(settings.csrf_cookie_name)
            header_token = request.headers.get(settings.csrf_header_name)
            if not cookie_token or not header_token or cookie_token != header_token:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": f"Missing or invalid {settings.csrf_header_name} header"},
                )
    return await call_next(request)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    token = request_id_ctx.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_ctx.reset(token)
    duration_ms = round((time.perf_counter() - started) * 1000)
    response.headers["x-request-id"] = request_id
    response.headers["x-response-time-ms"] = str(duration_ms)
    log.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "request_id": request_id,
        },
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # errors() can carry the raw request body in `input`, and for a non-JSON body
    # that is bytes, which json.dumps refuses. jsonable_encoder handles it, so a
    # malformed request gets a clean 422 instead of a 500.
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=jsonable_encoder(
            {"detail": "Request validation failed", "errors": exc.errors()},
            custom_encoder={bytes: lambda value: value.decode("utf-8", errors="replace")},
        ),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error", extra={"path": request.url.path})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(search.router, prefix=settings.api_prefix)
app.include_router(profiles.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)
