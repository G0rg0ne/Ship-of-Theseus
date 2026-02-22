"""
Authentication endpoints.
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.logger import logger
from app.core.security import create_access_token
from app.db.database import get_db
from app.schemas.auth import UserCreate, UserLogin, TokenResponse, UserResponse
from app.services.user_service import (
    authenticate_user,
    create_user,
    get_user_by_username,
    get_user_by_email,
)
from app.models.user import User

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_create: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new user account."""
    logger.info("Registration attempt", username=user_create.username)
    if await get_user_by_username(db, user_create.username):
        logger.warning("Registration failed - username taken", username=user_create.username)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    if await get_user_by_email(db, user_create.email):
        logger.warning("Registration failed - email taken", email=user_create.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    user = await create_user(db, user_create)
    logger.success("User registered", username=user.username)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    user: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return JWT token."""
    logger.info("Login attempt", username=user.username)
    authenticated = await authenticate_user(db, user.username, user.password)
    if authenticated is None:
        logger.warning("Login failed - invalid credentials", username=user.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": authenticated.username},
        expires_delta=access_token_expires,
    )
    logger.success(
        "Login successful",
        username=user.username,
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user information."""
    logger.info("User info request", username=current_user.username)
    return UserResponse.model_validate(current_user)


@router.get("/verify")
async def verify_token(current_user: User = Depends(get_current_user)):
    """Verify if token is valid."""
    logger.debug("Token verification request", username=current_user.username)
    return {"valid": True, "username": current_user.username}
