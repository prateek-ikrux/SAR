from contextlib import asynccontextmanager

from fastapi import FastAPI
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient(settings.mongodb_uri)
    app.state.mongo_client = client

    db = client[settings.mongodb_db]
    await db[settings.allowed_emails_collection].create_index("email", unique=True)
    await db[settings.otp_collection].create_index("email")
    await db[settings.otp_collection].create_index("expires_at", expireAfterSeconds=0)

    try:
        yield
    finally:
        client.close()


def get_db(app: FastAPI) -> AsyncIOMotorDatabase:
    return app.state.mongo_client[settings.mongodb_db]


def get_collection(app: FastAPI) -> AsyncIOMotorCollection:
    return get_db(app)[settings.mongodb_collection]


def get_allowed_emails_collection(app: FastAPI) -> AsyncIOMotorCollection:
    return get_db(app)[settings.allowed_emails_collection]


def get_otp_collection(app: FastAPI) -> AsyncIOMotorCollection:
    return get_db(app)[settings.otp_collection]
