from contextlib import asynccontextmanager

from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient(settings.mongodb_uri)
    app.state.mongo_client = client
    try:
        yield
    finally:
        client.close()


def get_collection(app: FastAPI) -> AsyncIOMotorCollection:
    db = app.state.mongo_client[settings.mongodb_db]
    return db[settings.mongodb_collection]
