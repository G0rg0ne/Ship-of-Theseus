from __future__ import annotations

import os
import shutil
from typing import Iterable, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.core.cache import _get_redis
from app.core.config import settings
from app.core.logger import logger
from app.schemas.admin import InfraMetrics, ServiceStorageStats, StorageVolume
from app.services.neo4j_service import Neo4jService


def _parse_mount_paths(raw: Optional[str]) -> List[str]:
    """Parse a comma-separated list of mount paths into a normalized list."""
    if not raw:
        # Sensible defaults inside the backend container
        return ["/"]
    paths: List[str] = []
    for part in raw.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        paths.append(stripped)
    return paths or ["/"]


def _classify_usage(
    used_percent: float,
    warn_percent: float,
    crit_percent: float,
) -> str:
    """Return healthy/warning/critical based on percentage thresholds."""
    if used_percent >= crit_percent:
        return "critical"
    if used_percent >= warn_percent:
        return "warning"
    return "healthy"


def get_disk_volumes(
    mount_paths: Iterable[str] | None = None,
    warn_percent: Optional[float] = None,
    crit_percent: Optional[float] = None,
) -> List[StorageVolume]:
    """
    Compute disk usage for the given mount points.

    Uses shutil.disk_usage so it works inside Docker containers as well.
    """
    paths = list(mount_paths) if mount_paths is not None else _parse_mount_paths(
        getattr(settings, "DISK_MOUNT_PATHS", None)  # type: ignore[attr-defined]
    )
    default_warn = getattr(settings, "DISK_WARN_PERCENT", 80)  # type: ignore[attr-defined]
    default_crit = getattr(settings, "DISK_CRIT_PERCENT", 90)  # type: ignore[attr-defined]

    # Safely parse warn threshold, falling back to defaults on error.
    if warn_percent is not None:
        try:
            warn = float(warn_percent)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Invalid warn_percent for disk volumes; falling back to DISK_WARN_PERCENT",
                value=warn_percent,
                default=default_warn,
                error=str(exc),
            )
            try:
                warn = float(default_warn)
            except (TypeError, ValueError):
                warn = 80.0
    else:
        try:
            warn = float(default_warn)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Invalid DISK_WARN_PERCENT setting; falling back to built-in default",
                value=default_warn,
                error=str(exc),
            )
            warn = 80.0

    # Safely parse critical threshold, falling back to defaults on error.
    if crit_percent is not None:
        try:
            crit = float(crit_percent)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Invalid crit_percent for disk volumes; falling back to DISK_CRIT_PERCENT",
                value=crit_percent,
                default=default_crit,
                error=str(exc),
            )
            try:
                crit = float(default_crit)
            except (TypeError, ValueError):
                crit = 90.0
    else:
        try:
            crit = float(default_crit)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Invalid DISK_CRIT_PERCENT setting; falling back to built-in default",
                value=default_crit,
                error=str(exc),
            )
            crit = 90.0

    volumes: List[StorageVolume] = []
    for path in paths:
        try:
            # Resolve symlinks so monitoring remains stable if paths move.
            resolved = os.path.realpath(path)
            usage = shutil.disk_usage(resolved)
            total = int(usage.total)
            used = int(usage.used)
            free = int(usage.free)
            used_percent = (used / total * 100) if total else 0.0
            status = _classify_usage(used_percent, warn, crit)
            volumes.append(
                StorageVolume(
                    mount_path=resolved,
                    total_bytes=total,
                    used_bytes=used,
                    free_bytes=free,
                    used_percent=round(used_percent, 2),
                    status=status,
                )
            )
        except Exception as exc:
            logger.warning(
                "Failed to compute disk usage for path",
                path=path,
                error=str(exc),
            )
    return volumes


async def get_postgres_size(db: AsyncSession) -> Tuple[Optional[int], Optional[str]]:
    """
    Return the size of the current PostgreSQL database in bytes.

    Returns (size_bytes, error_detail).
    """
    try:
        result = await db.execute(text("SELECT pg_database_size(current_database())"))
        size = result.scalar()
        if size is None:
            return None, "pg_database_size returned NULL"
        return int(size), None
    except Exception as exc:
        logger.warning("Failed to compute PostgreSQL database size: {}", exc)
        return None, str(exc)


def get_neo4j_store_size(neo4j: Optional[Neo4jService]) -> Tuple[Optional[int], Optional[str]]:
    """
    Best-effort estimate of Neo4j store size in bytes.

    First tries to sum the size of files under NEO4J_DATA_PATH (if configured);
    if that is not set or not accessible, falls back to Neo4j's internal store
    size helper when available. Returns (None, reason) when neither works.
    """
    fs_error: Optional[str] = None
    try:
        data_path = getattr(settings, "NEO4J_DATA_PATH", None)
        if data_path:
            resolved = os.path.realpath(data_path)
            if os.path.isdir(resolved):
                try:
                    total = 0
                    for root, _dirs, files in os.walk(resolved):
                        for name in files:
                            fp = os.path.join(root, name)
                            try:
                                total += os.path.getsize(fp)
                            except OSError:
                                continue
                    return total, None
                except Exception as exc:
                    fs_error = f"Filesystem size scan failed: {exc}"
            else:
                fs_error = f"NEO4J_DATA_PATH does not exist or is not a directory: {resolved}"

        # No usable filesystem path; fall back to Neo4j helper if available.
        if neo4j is None:
            return None, fs_error or "Neo4j data path not configured and Neo4j service not available"

        try:
            size = neo4j.get_store_size_bytes()
            if size is None:
                return None, fs_error or "Neo4j store size unavailable"
            return int(size), None
        except AttributeError:
            return None, fs_error or "Neo4j store size helper not available on this build"
    except Exception as exc:
        if fs_error:
            error_detail = f"{fs_error}; Neo4j error: {exc}"
        else:
            error_detail = f"Neo4j store size computation failed: {exc}"
        logger.warning(error_detail)
        return None, error_detail


async def get_redis_memory_usage() -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """
    Return (used_memory_bytes, used_memory_peak_bytes, error_detail) for Redis.

    When Redis is not configured, returns (None, None, "Not configured; using in-memory").
    """
    try:
        redis = await _get_redis()
        if redis is None:
            return None, None, "Not configured; using in-memory"
        info = await redis.info("memory")
        used = info.get("used_memory")
        peak = info.get("used_memory_peak")
        used_bytes = int(used) if used is not None else None
        peak_bytes = int(peak) if peak is not None else None
        return used_bytes, peak_bytes, None
    except Exception as exc:
        logger.warning("Failed to read Redis memory usage: {}", exc)
        return None, None, str(exc)


async def get_infra_metrics(
    db: AsyncSession,
    neo4j: Optional[Neo4jService],
) -> InfraMetrics:
    """
    Gather disk, PostgreSQL, Neo4j and Redis storage/memory metrics.

    Designed to be resilient: failures for one metric should not prevent others
    from being returned.
    """
    try:
        volumes = get_disk_volumes()
    except Exception as exc:
        logger.warning("Failed to collect disk volume metrics: {}", exc)
        volumes = []

    postgres_size_bytes, pg_error = await get_postgres_size(db)
    neo4j_size_bytes, neo4j_error = await run_in_threadpool(get_neo4j_store_size, neo4j)
    redis_used_bytes, redis_peak_bytes, redis_error = await get_redis_memory_usage()

    services: List[ServiceStorageStats] = []

    # PostgreSQL
    if postgres_size_bytes is not None:
        services.append(
            ServiceStorageStats(
                name="PostgreSQL",
                size_bytes=postgres_size_bytes,
                status="healthy",
                detail=None,
            )
        )
    else:
        services.append(
            ServiceStorageStats(
                name="PostgreSQL",
                size_bytes=None,
                status="unknown",
                detail=pg_error or "Unable to compute database size",
            )
        )

    # Neo4j
    if neo4j_size_bytes is not None:
        services.append(
            ServiceStorageStats(
                name="Neo4j",
                size_bytes=neo4j_size_bytes,
                status="healthy",
                detail=None,
            )
        )
    else:
        services.append(
            ServiceStorageStats(
                name="Neo4j",
                size_bytes=None,
                status="unknown",
                detail=neo4j_error or "Store size not available",
            )
        )

    # Redis
    if redis_used_bytes is not None:
        services.append(
            ServiceStorageStats(
                name="Redis",
                size_bytes=redis_used_bytes,
                status="healthy",
                detail=(
                    f"Peak used memory: {redis_peak_bytes} bytes"
                    if redis_peak_bytes is not None
                    else None
                ),
            )
        )
    else:
        services.append(
            ServiceStorageStats(
                name="Redis",
                size_bytes=None,
                status="unknown",
                detail=redis_error or "Unable to compute Redis memory usage",
            )
        )

    return InfraMetrics(volumes=volumes, services=services)

