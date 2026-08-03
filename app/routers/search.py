from fastapi import APIRouter, Request

from app.config import settings
from app.db import get_collection
from app.schemas import SearchRequest, SearchResponse, SearchResult

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search(payload: SearchRequest, request: Request) -> SearchResponse:
    collection = get_collection(request.app)

    pipeline = [
        {
            "$vectorSearch": {
                "index": settings.vector_index_name,
                "path": settings.vector_path,
                "query": payload.query,
                "numCandidates": payload.num_candidates,
                "limit": payload.limit,
            }
        },
        {"$set": {"score": {"$meta": "vectorSearchScore"}}},
    ]

    results = []
    async for doc in collection.aggregate(pipeline):
        doc_id = str(doc.pop("_id"))
        score = doc.pop("score")
        results.append(SearchResult(_id=doc_id, score=score, profile=doc))

    return SearchResponse(query=payload.query, count=len(results), results=results)
