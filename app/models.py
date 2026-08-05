from datetime import datetime

from pydantic import BaseModel, EmailStr


class AllowedEmailDocument(BaseModel):
    email: EmailStr
    added_at: datetime


class OTPDocument(BaseModel):
    email: EmailStr
    otp_hash: str
    expires_at: datetime
    attempts: int = 0
    consumed: bool = False
    created_at: datetime
