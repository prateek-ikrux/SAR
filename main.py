from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import lifespan
from app.routers.auth import router as auth_router
from app.routers.search import router as search_router

app = FastAPI(title="Profile Vector Search", lifespan=lifespan)

origins = (
    ["*"]
    if settings.cors_allow_origins == "*"
    else [origin.strip() for origin in settings.cors_allow_origins.split(",")]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(search_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
