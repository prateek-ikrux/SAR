from pydantic import BaseModel, EmailStr, Field, model_validator


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Free-text search query")
    limit: int = Field(10, ge=1, le=100, description="Number of results to return")
    num_candidates: int = Field(
        100, ge=1, le=10000, description="Candidates considered during the ANN search"
    )
    exact: bool = Field(
        True, description="Whether to perform an exact search instead of ANN"
    )

    @model_validator(mode="after")
    def check_num_candidates(self) -> "SearchRequest":
        if not self.exact and self.num_candidates < self.limit:
            raise ValueError("num_candidates must be greater than or equal to limit")
        return self


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
