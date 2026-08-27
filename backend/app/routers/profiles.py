from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.dependencies import CurrentUser
from app.models import ProfileOut, ResumeLink
from app.services import auth_service, search_service, storage

log = logging.getLogger(__name__)
router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("/{profile_id}", response_model=ProfileOut)
async def get_profile(profile_id: str, user: CurrentUser) -> ProfileOut:
    try:
        profile = await search_service.get_profile(profile_id)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return ProfileOut(**profile)


@router.get("/{profile_id}/resume")
async def get_resume(
    profile_id: str,
    user: CurrentUser,
    redirect: bool = Query(
        default=False, description="Redirect straight to the file instead of returning JSON"
    ),
):
    try:
        profile = await search_service.get_profile(profile_id)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    file_name = profile.get("file_name")
    if not file_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This profile has no source file recorded"
        )

    try:
        url = await storage.presigned_resume_url(file_name)
    except storage.StorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    log.info("resume link issued", extra={"user_id": str(user["_id"]), "file_name": file_name})

    if redirect:
        return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return ResumeLink(file_name=file_name, url=url, expires_in_seconds=settings.minio_presign_expiry_seconds)
