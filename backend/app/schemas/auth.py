"""
Pydantic schemas for authentication.
"""
from pydantic import BaseModel, EmailStr


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
    username: str
    email: str
