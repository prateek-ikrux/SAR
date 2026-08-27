from __future__ import annotations

from fastapi import APIRouter

from app import db
from app.config import settings
from app.services import mailer, storage

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@router.get("/ready")
async def ready() -> dict:
    checks: dict[str, object] = {}

    try:
        await db.client().admin.command("ping")
        checks["mongodb"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["mongodb"] = f"error: {exc}"

    if settings.minio_configured:
        checks["object_storage"] = "ok" if await storage.healthy() else "unreachable"
    else:
        checks["object_storage"] = "not_configured"

    if settings.graph_configured:
        checks["mail"] = "ok" if await mailer.healthy() else "unreachable"
    else:
        checks["mail"] = "not_configured"

    # Mail is part of readiness now: without it nobody can obtain a sign-in code.
    ready_state = checks["mongodb"] == "ok" and checks["mail"] == "ok"
    return {"ready": ready_state, "checks": checks}
