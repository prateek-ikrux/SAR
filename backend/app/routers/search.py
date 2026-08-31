from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pymongo.errors import OperationFailure

from app.dependencies import SearchUser
from app.models import SearchRequest, SearchResponse
from app.services import search_service

log = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def run_search(payload: SearchRequest, user: SearchUser) -> SearchResponse:
    try:
        result = await search_service.search(
            query=payload.query,
            page=payload.page,
            page_size=payload.page_size,
            collapse_duplicates=payload.collapse_duplicates,
        )
    except OperationFailure as exc:
        log.exception("vector search failed", extra={"query": payload.query})
        reason = (exc.details or {}).get("errmsg") or str(exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Search backend rejected the query: {reason}",
        ) from exc

    log.info(
        "search served",
        extra={
            "user_id": str(user["_id"]),
            "strategy": result["strategy"],
            "page": result["page"],
            "returned": result["returned"],
            "took_ms": result["took_ms"],
        },
    )
    return SearchResponse(**result)
