from fastapi import FastAPI

from app.db import lifespan
from app.routers.search import router as search_router

app = FastAPI(title="Profile Vector Search", lifespan=lifespan)
app.include_router(search_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
