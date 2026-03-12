"""
Pydantic schemas for authentication.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """User registration request schema."""
    username: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=255)


class UserLogin(BaseModel):
    """User login request schema."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token response schema."""
    access_token: str
    token_type: str
    expires_in: int


class UserResponse(BaseModel):
    """User information response schema."""
    id: uuid.UUID
    username: str
    email: str
    is_active: bool
    is_admin: bool = False
    email_verified: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Generic message response (e.g. after registration or verification)."""
    message: str


class ResendVerificationRequest(BaseModel):
    """Request body for resending the verification email."""
    email: EmailStr
