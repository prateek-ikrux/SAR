from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response, status
from pymongo.errors import DuplicateKeyError

from app import db
from app.dependencies import AdminUser
from app.models import CreateUserRequest, UpdateUserRequest, UserOut
from app.services import auth_service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users(admin: AdminUser) -> list[UserOut]:
    docs = await db.users().find({}).sort("created_at", -1).to_list(length=500)
    return [UserOut(**auth_service.serialize_user(doc)) for doc in docs]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(payload: CreateUserRequest, admin: AdminUser) -> UserOut:
    try:
        user = await auth_service.create_user(email=payload.email, name=payload.name, role=payload.role)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A user with that email already exists"
        ) from exc

    log.info(
        "user created",
        extra={"actor_id": str(admin["_id"]), "user_id": str(user["_id"]), "role": payload.role},
    )
    return UserOut(**auth_service.serialize_user(user))


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(user_id: str, payload: UpdateUserRequest, admin: AdminUser) -> UserOut:
    try:
        oid = auth_service.to_object_id(user_id)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    target = await db.users().find_one({"_id": oid})
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    updates: dict = {}
    if payload.name is not None:
        updates["name"] = payload.name.strip()
    if payload.role is not None:
        updates["role"] = payload.role
    if payload.active is not None:
        updates["active"] = payload.active

    if not updates:
        return UserOut(**auth_service.serialize_user(target))

    # Never let an admin lock everyone out by demoting or disabling the last admin.
    demoting = updates.get("role") not in (None, "admin") and target.get("role") == "admin"
    deactivating = updates.get("active") is False and target.get("role") == "admin"
    if demoting or deactivating:
        remaining = await db.users().count_documents({"role": "admin", "active": True, "_id": {"$ne": oid}})
        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This is the last active admin. Promote another admin first.",
            )

    # Role and active changes take effect on this user's very next request:
    # every authenticated request re-reads the account rather than trusting the
    # role baked into their token.
    await db.users().update_one({"_id": oid}, {"$set": updates})

    updated = await db.users().find_one({"_id": oid})
    log.info(
        "user updated", extra={"actor_id": str(admin["_id"]), "user_id": user_id, "fields": list(updates)}
    )
    return UserOut(**auth_service.serialize_user(updated))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str, admin: AdminUser, response: Response) -> Response:
    try:
        oid = auth_service.to_object_id(user_id)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    if oid == admin["_id"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot delete your own account")

    target = await db.users().find_one({"_id": oid})
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if target.get("role") == "admin":
        remaining = await db.users().count_documents({"role": "admin", "active": True, "_id": {"$ne": oid}})
        if remaining == 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This is the last active admin")

    await db.users().delete_one({"_id": oid})
    log.info("user deleted", extra={"actor_id": str(admin["_id"]), "user_id": user_id})

    response.status_code = status.HTTP_204_NO_CONTENT
    return response
