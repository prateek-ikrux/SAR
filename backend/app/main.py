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
from app.logging_config import configure_logging, request_id_ctx
from app.routers import auth, health, profiles, search, users
from app.services import mailer

log = logging.getLogger(__name__)

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


def warn_on_cors_misconfiguration() -> None:
    """Catch the missing-origin trap at boot rather than in the browser.

    The web app is a separate deployment on its own origin, so without
    CORS_ORIGINS the browser blocks every call and the app looks simply broken.
    """
    if not settings.cors_origin_list:
        log.warning(
            "CORS_ORIGINS is empty. Any browser calling this API from another origin will be "
            "blocked before the request is even sent. Set it to the web app's origin."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    await db.connect()
    await ensure_indexes()
    warn_on_cors_misconfiguration()
    log.info(
        "application started",
        extra={
            "environment": settings.environment,
            "vector_index": settings.vector_index_name,
            "vector_path": settings.vector_path,
            "mail_configured": settings.graph_configured,
            "cors_origins": settings.cors_origin_list,
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
        # The session is a bearer header the web app sets itself, never a cookie
        # the browser attaches on its own. Nothing needs credentialed CORS, so
        # not allowing it keeps that door shut.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


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
    print('this request is being gone through the request context')
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
