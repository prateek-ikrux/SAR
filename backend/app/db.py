from __future__ import annotations

import logging

from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from app.config import settings

log = logging.getLogger(__name__)

_client: AsyncMongoClient | None = None


async def connect() -> AsyncMongoClient:
    global _client
    if _client is None:
        _client = AsyncMongoClient(
            settings.mongodb_uri,
            appname=settings.app_name,
            serverSelectionTimeoutMS=10_000,
            tz_aware=True,
        )
        await _client.admin.command("ping")
        log.info(
            "mongodb connected", extra={"ats_db": settings.mongo_db_ats, "app_db": settings.mongo_db_app}
        )
    return _client


async def disconnect() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
        log.info("mongodb disconnected")


def client() -> AsyncMongoClient:
    if _client is None:
        raise RuntimeError("MongoDB client is not initialised")
    return _client


def app_db() -> AsyncDatabase:
    """This application's own database: users and sessions."""
    return client()[settings.mongo_db_app]


def ats_db() -> AsyncDatabase:
    """Existing candidate database. Read-only from this service."""
    return client()[settings.mongo_db_ats]


def users() -> AsyncCollection:
    return app_db()["users"]


def sessions() -> AsyncCollection:
    return app_db()["sessions"]


def otp_codes() -> AsyncCollection:
    return app_db()["otp_codes"]


def profiles() -> AsyncCollection:
    return ats_db()[settings.profiles_collection]
