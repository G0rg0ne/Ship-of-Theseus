"""
Redis-backed cache manager for the application.
Falls back to in-memory storage when REDIS_URL is not set.
"""
import asyncio
import json
import time
from typing import Any, Optional

from app.core.config import settings
from app.core.logger import logger

# In-memory fallback storage: key -> (value_str, expiry_ts or None)
_memory_store: dict[str, tuple[str, Optional[float]]] = {}
_memory_lock = asyncio.Lock()

# Redis client (lazy init)
_redis_client: Optional[Any] = None


def _serialize(value: Any) -> str:
    """Serialize a value to JSON string for storage."""
    return json.dumps(value, default=str)


def _deserialize(raw: Optional[str]) -> Any:
    """Deserialize a JSON string from storage."""
    if raw is None:
        return None
    return json.loads(raw)


async def _get_redis():
    """Get or create async Redis client."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not settings.REDIS_URL:
        return None
    try:
        from redis.asyncio import Redis
        _redis_client = Redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await _redis_client.ping()
        logger.success("Redis cache connected", url=settings.REDIS_URL.split("@")[-1])
        return _redis_client
    except Exception as e:
        logger.warning("Redis connection failed, using in-memory cache", error=str(e))
        return None


async def cache_get(key: str) -> Any:
    """
    Get a value from cache by key.
    Returns None if key is missing or expired.
    """
    redis = await _get_redis()
    if redis:
        try:
            raw = await redis.get(key)
            return _deserialize(raw)
        except Exception as e:
            logger.error("Redis get failed", key=key, error=str(e))
            return None

    async with _memory_lock:
        entry = _memory_store.get(key)
        if not entry:
            return None
        val_str, expiry = entry
        if expiry is not None and time.monotonic() > expiry:
            del _memory_store[key]
            return None
        return _deserialize(val_str)


async def cache_set(key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
    """
    Set a value in cache with optional TTL.
    """
    raw = _serialize(value)
    redis = await _get_redis()
    if redis:
        try:
            if ttl_seconds is not None:
                await redis.setex(key, ttl_seconds, raw)
            else:
                await redis.set(key, raw)
        except Exception as e:
            logger.error("Redis set failed", key=key, error=str(e))
        return

    async with _memory_lock:
        expiry = None
        if ttl_seconds is not None:
            expiry = time.monotonic() + ttl_seconds
        _memory_store[key] = (raw, expiry)


async def cache_delete(key: str) -> None:
    """Delete a key from cache."""
    redis = await _get_redis()
    if redis:
        try:
            await redis.delete(key)
        except Exception as e:
            logger.error("Redis delete failed", key=key, error=str(e))
        return

    async with _memory_lock:
        _memory_store.pop(key, None)


def cache_key_document(user_id: str) -> str:
    """Key for a user's current document."""
    return f"documents:{user_id}"


def cache_key_extraction_job(job_id: str) -> str:
    """Key for an entity extraction job's status/result."""
    return f"extraction:job:{job_id}"


# Default TTLs (seconds)
DOCUMENT_TTL = 24 * 60 * 60  # 24 hours
EXTRACTION_JOB_TTL = 60 * 60  # 1 hour
