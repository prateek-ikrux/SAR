from __future__ import annotations

import logging

from fastapi import APIRouter

from app.dependencies import AdminUser
from app.models import AppSettingsOut, UpdateSettingsRequest
from app.services import settings_service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=AppSettingsOut)
async def read_settings(admin: AdminUser) -> AppSettingsOut:
    """Admin only. Recruiters do not choose the search mode - they simply search,
    and the response tells them which mode ran."""
    return AppSettingsOut(**await settings_service.get_settings())


@router.put("", response_model=AppSettingsOut)
async def write_settings(payload: UpdateSettingsRequest, admin: AdminUser) -> AppSettingsOut:
    updated = await settings_service.update_settings(
        search_exact=payload.search_exact, actor_email=admin["email"]
    )
    return AppSettingsOut(**updated)
