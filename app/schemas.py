from pydantic import BaseModel, EmailStr, Field


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


class OTPRequest(BaseModel):
    email: EmailStr


class OTPVerify(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class MessageResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
