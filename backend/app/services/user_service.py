"""
User service for registration and authentication (PostgreSQL-backed).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import UserCreate


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
