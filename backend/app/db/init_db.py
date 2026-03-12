"""
Create database tables at startup.
"""
from sqlalchemy import text

from app.core.logger import logger
from app.db.database import Base, engine
from app.models import User  # noqa: F401 - register model with Base.metadata


async def create_tables() -> None:
    """Create all tables defined on Base.metadata (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn))
        # Add is_admin column to existing databases (PostgreSQL: IF NOT EXISTS for ADD COLUMN)
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token VARCHAR(255)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token_expires TIMESTAMP"
            )
        )
    logger.info("Database tables created or already present")
