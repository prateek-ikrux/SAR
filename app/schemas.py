from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Free-text search query")
    limit: int = Field(10, ge=1, le=100, description="Number of results to return")
    num_candidates: int = Field(
        100, ge=1, le=10000, description="Candidates considered during the ANN search"
    )


class SearchResult(BaseModel):
    id: str = Field(..., alias="_id")
    score: float
    profile: dict

    model_config = {"populate_by_name": True}


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[SearchResult]
