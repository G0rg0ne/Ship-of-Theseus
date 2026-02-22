"""
Create database tables at startup.
"""
from app.core.logger import logger
from app.db.database import Base, engine
from app.models import User  # noqa: F401 - register model with Base.metadata


async def create_tables() -> None:
    """Create all tables defined on Base.metadata (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn))
    logger.info("Database tables created or already present")
