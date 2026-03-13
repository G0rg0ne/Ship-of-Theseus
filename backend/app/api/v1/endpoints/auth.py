"""
Authentication endpoints.
"""
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.logger import logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    generate_verification_token,
    hash_token,
)
from app.db.database import get_db
from app.schemas.auth import (
    MessageResponse,
    ResendVerificationRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.services.email_service import send_verification_email
from app.services.user_service import (
    authenticate_user,
    create_user,
    get_user_by_email,
    get_user_by_username,
    set_verification_token,
    verify_email_token,
)
from app.models.user import User

router = APIRouter()

REFRESH_TOKEN_COOKIE = "refresh_token"
COOKIE_PATH = "/api/auth"
# 7 days in seconds
REFRESH_COOKIE_MAX_AGE = 7 * 24 * 3600
VERIFICATION_TOKEN_EXPIRE_HOURS = 24


def _set_refresh_cookie(response: JSONResponse, token: str) -> None:
    """Set httpOnly refresh token cookie on the response."""
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        path=COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=not settings.DEBUG,
    )


def _clear_refresh_cookie(response: JSONResponse) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(key=REFRESH_TOKEN_COOKIE, path=COOKIE_PATH)


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register(
    background_tasks: BackgroundTasks,
    user_create: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Create a new user account and send verification email."""
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
    raw_token = generate_verification_token()
    token_hash = hash_token(raw_token)
    expires_at = datetime.utcnow() + timedelta(hours=VERIFICATION_TOKEN_EXPIRE_HOURS)
    set_verification_token(user, token_hash, expires_at)
    await db.commit()
    await db.refresh(user)

    email_sent = False
    try:
        logger.info(
            "Sending verification email",
            username=user.username,
            email=user.email,
            smtp_host=settings.SMTP_HOST,
            smtp_port=settings.SMTP_PORT,
        )
        background_tasks.add_task(send_verification_email, user.email, raw_token)
        email_sent = True
    except Exception as e:
        # Log message and exception so the real error is visible (console format may not show extra kwargs).
        logger.warning(
            "Verification email send failed; user created: %s",
            str(e),
            username=user.username,
            email=user.email,
        )
        logger.exception("Verification email exception details")

    if email_sent:
        logger.success("User registered; verification email sent", username=user.username)
        return MessageResponse(message="Check your email to verify your account.")

    logger.success("User registered without verification email", username=user.username)
    return MessageResponse(
        message="Account created, but we could not send a verification email. "
        "Please contact support or try registering again later."
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    user: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Authenticate user; return access token in body and set refresh token in httpOnly cookie."""
    logger.info("Login attempt", username=user.username)
    authenticated = await authenticate_user(db, user.username, user.password)
    if authenticated is None:
        logger.warning("Login failed - invalid credentials", username=user.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if not authenticated.email_verified:
        logger.warning("Login failed - email not verified", username=user.username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before signing in.",
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": authenticated.username},
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(data={"sub": authenticated.username})
    response = JSONResponse(
        content={
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
    )
    _set_refresh_cookie(response, refresh_token)
    logger.success(
        "Login successful",
        username=user.username,
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    return response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Issue new access token and rotate refresh token from httpOnly cookie."""
    cookie_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not cookie_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )
    payload = decode_refresh_token(cookie_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    user = await get_user_by_username(db, username)
    if user is None or not user.is_active or not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires,
    )
    new_refresh_token = create_refresh_token(data={"sub": user.username})
    response = JSONResponse(
        content={
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
    )
    _set_refresh_cookie(response, new_refresh_token)
    return response


@router.post("/logout")
async def logout() -> JSONResponse:
    """Clear the refresh token cookie."""
    response = JSONResponse(content={"message": "Signed out"})
    _clear_refresh_cookie(response)
    return response


@router.get("/verify-email", response_model=MessageResponse)
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Verify email using the token from the verification link."""
    user = await verify_email_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link.",
        )
    await db.commit()
    logger.success("Email verified", username=user.username)
    return MessageResponse(message="Email verified. You can sign in now.")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    background_tasks: BackgroundTasks,
    body: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Resend the verification email for the given address."""
    user = await get_user_by_email(db, body.email)
    if user is None or user.email_verified:
        return MessageResponse(message="If an account exists for this email, a verification link was sent.")
    raw_token = generate_verification_token()
    token_hash = hash_token(raw_token)
    expires_at = datetime.utcnow() + timedelta(hours=VERIFICATION_TOKEN_EXPIRE_HOURS)
    set_verification_token(user, token_hash, expires_at)
    await db.commit()
    try:
        background_tasks.add_task(send_verification_email, user.email, raw_token)
    except Exception as e:
        logger.warning("Resend verification email failed", email=body.email, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not send verification email. Try again later.",
        )
    logger.info("Verification email resent", email=body.email)
    return MessageResponse(message="Verification email sent. Check your inbox.")


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Get current authenticated user information."""
    logger.info("User info request", username=current_user.username)
    return UserResponse.model_validate(current_user)


@router.get("/verify")
async def verify_token(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Verify if access token is valid."""
    logger.debug("Token verification request", username=current_user.username)
    return {"valid": True, "username": current_user.username}
