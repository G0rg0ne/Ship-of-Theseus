"""
User service for registration and authentication (PostgreSQL-backed).
"""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, hash_token, verify_password
from app.models.user import User
from app.schemas.auth import UserCreate


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Return user by id or None."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """Return user by username or None."""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Return user by email or None."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, user_create: UserCreate) -> User:
    """Create a new user; hash password and persist. Returns the created User."""
    hashed = get_password_hash(user_create.password)
    user = User(
        username=user_create.username,
        email=user_create.email,
        hashed_password=hashed,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> User | None:
    """Return User if username exists and password matches; else None."""
    user = await get_user_by_username(db, username)
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


def set_verification_token(
    user: User,
    token_hash: str,
    expires_at: datetime,
) -> None:
    """Set email verification token and expiry on a user (in-place)."""
    user.verification_token = token_hash
    user.verification_token_expires = expires_at


async def verify_email_token(db: AsyncSession, plain_token: str) -> User | None:
    """
    Find user by verification token (hash match), check expiry, set email_verified=True
    and clear token. Returns the User or None if invalid/expired.
    """
    token_hash = hash_token(plain_token)
    result = await db.execute(
        select(User).where(
            User.verification_token == token_hash,
            User.verification_token_expires.isnot(None),
            User.verification_token_expires > datetime.utcnow(),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        return None
    user.email_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    return user
