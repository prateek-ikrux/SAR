from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

Role = Literal["admin", "recruiter"]

OtpCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=12)]


# --------------------------------------------------------------------------- auth
class RequestCodeRequest(BaseModel):
    email: EmailStr


class RequestCodeResponse(BaseModel):
    """Deliberately says the same thing whether or not the address has an account."""

    message: str
    expires_in_minutes: int
    resend_available_in_seconds: int


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: OtpCode


class UserOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    email: EmailStr
    name: str
    role: Role
    active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class LoginResponse(BaseModel):
    user: UserOut
    # Send this back as `Authorization: Bearer <access_token>`.
    access_token: str
    # When it expires. There is no refresh: signing in again is the only way to
    # extend, so the frontend returns the user to the sign-in screen at this
    # point rather than waiting for the next 401.
    expires_at: datetime


# --------------------------------------------------------------------------- users
class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    role: Role = "recruiter"


class UpdateUserRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    active: bool | None = None


# --------------------------------------------------------------------------- search
class SearchRequest(BaseModel):
    query: str = Field(
        min_length=1, max_length=4000, description="Natural language query, or an email / phone number"
    )
    page: int = Field(default=1, ge=1, le=100)
    page_size: int = Field(default=10, ge=1, le=50)
    collapse_duplicates: bool = True
    # No `exact` here on purpose. Search always runs ENN - see
    # search_service._run_vector_search - and no caller can change that.


class DuplicateRef(BaseModel):
    id: str
    file_name: str | None = None
    score: float | None = None


class SearchHit(BaseModel):
    id: str
    headline: str | None = None
    email: str | None = None
    phone: str | None = None
    file_name: str | None = None
    score: float
    snippet: str
    collapsed: bool = False
    duplicate_count: int = 1
    duplicates: list[DuplicateRef] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    strategy: Literal["vector", "identifier"]
    page: int
    page_size: int
    results: list[SearchHit]
    returned: int
    pool_size: int
    total_in_pool: int
    has_more: bool
    pool_exhausted: bool
    took_ms: int


# --------------------------------------------------------------------------- profiles
class ProfileOut(BaseModel):
    id: str
    headline: str | None = None
    email: str | None = None
    phone: str | None = None
    file_name: str | None = None
    document: str
    duplicate_count: int = 1
    duplicates: list[DuplicateRef] = Field(default_factory=list)


class ResumeLink(BaseModel):
    file_name: str
    url: str
    expires_in_seconds: int
