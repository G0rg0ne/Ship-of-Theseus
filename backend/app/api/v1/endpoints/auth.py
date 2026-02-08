"""
Authentication endpoints.
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.auth import UserLogin, TokenResponse, UserResponse
from app.core.security import verify_password, create_access_token
from app.core.config import settings
from app.services.user_service import get_user_password_hash, get_user_data
from app.api.v1.deps import get_current_user

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(user: UserLogin):
    """Authenticate user and return JWT token."""
    # Only allow the single user from environment variables
    if user.username != settings.USERNAME:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    if not verify_password(user.password, get_user_password_hash()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": settings.USERNAME}, expires_delta=access_token_expires
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user information."""
    return UserResponse(
        username=current_user["username"],
        email=current_user["email"]
    )


@router.get("/verify")
async def verify_token(current_user: dict = Depends(get_current_user)):
    """Verify if token is valid."""
    return {"valid": True, "username": current_user["username"]}
