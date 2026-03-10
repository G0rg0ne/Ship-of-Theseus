"""
Admin service: platform stats, user list with document counts, system health.
"""
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import _get_redis
from app.models.user import User
from app.schemas.admin import (
    PlatformStats,
    ServiceHealth,
    SystemHealth,
    UserAdminView,
)
from app.services.neo4j_service import Neo4jService


async def get_platform_stats(
    db: AsyncSession,
    neo4j: Optional[Neo4jService],
) -> PlatformStats:
    """Aggregate platform-wide statistics from PostgreSQL and Neo4j."""
    # User counts from PostgreSQL
    total_result = await db.execute(select(func.count(User.id)))
    total_users = total_result.scalar() or 0

    active_result = await db.execute(select(func.count(User.id)).where(User.is_active.is_(True)))
    active_users = active_result.scalar() or 0

    since_7d = datetime.utcnow() - timedelta(days=7)
    new_result = await db.execute(
        select(func.count(User.id)).where(User.created_at >= since_7d)
    )
    new_users_7d = new_result.scalar() or 0

    # Neo4j global counts
    total_documents = total_entities = total_relationships = total_communities = 0
    if neo4j:
        try:
            total_entities, total_relationships, total_communities, total_documents = (
                neo4j.get_global_counts()
            )
        except Exception:
            pass

    avg_docs = (total_documents / total_users) if total_users else 0.0

    return PlatformStats(
        total_users=total_users,
        active_users=active_users,
        new_users_7d=new_users_7d,
        total_documents=total_documents,
        total_entities=total_entities,
        total_relationships=total_relationships,
        total_communities=total_communities,
        avg_docs_per_user=round(avg_docs, 2),
    )


async def get_admin_count(db: AsyncSession) -> int:
    """Return the number of active admin users."""
    result = await db.execute(
        select(func.count(User.id)).where(
            User.is_admin.is_(True),
            User.is_active.is_(True),
        )
    )
    return result.scalar() or 0


async def get_all_users(
    db: AsyncSession,
    neo4j: Optional[Neo4jService],
    page: int = 1,
    limit: int = 20,
) -> List[UserAdminView]:
    """List users with document counts, paginated."""
    offset = (page - 1) * limit
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    users = result.scalars().all()

    out: List[UserAdminView] = []
    for user in users:
        doc_count = 0
        if neo4j:
            try:
                doc_count = neo4j.get_user_document_count(str(user.id))
            except Exception:
                pass
        out.append(
            UserAdminView(
                id=user.id,
                username=user.username,
                email=user.email,
                is_active=user.is_active,
                is_admin=getattr(user, "is_admin", False),
                created_at=user.created_at,
                document_count=doc_count,
            )
        )
    return out


async def get_system_health(
    db: AsyncSession,
    neo4j: Optional[Neo4jService],
) -> SystemHealth:
    """Check health of PostgreSQL, Neo4j, Redis and return global Neo4j counts."""
    from sqlalchemy import text

    services: List[ServiceHealth] = []

    # PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        services.append(ServiceHealth(name="PostgreSQL", status="healthy"))
    except Exception as e:
        services.append(
            ServiceHealth(name="PostgreSQL", status="down", detail=str(e))
        )

    # Neo4j
    if neo4j:
        try:
            if neo4j.health_check():
                services.append(ServiceHealth(name="Neo4j", status="healthy"))
            else:
                services.append(ServiceHealth(name="Neo4j", status="down", detail="Health check failed"))
        except Exception as e:
            services.append(ServiceHealth(name="Neo4j", status="down", detail=str(e)))
    else:
        services.append(ServiceHealth(name="Neo4j", status="down", detail="Not configured"))

    # Redis
    try:
        redis = await _get_redis()
        if redis is None:
            services.append(
                ServiceHealth(name="Redis", status="degraded", detail="Not configured; using in-memory")
            )
        else:
            await redis.ping()
            services.append(ServiceHealth(name="Redis", status="healthy"))
    except Exception as e:
        services.append(ServiceHealth(name="Redis", status="down", detail=str(e)))

    # Global Neo4j counts for dashboard
    neo4j_node_count = neo4j_edge_count = neo4j_community_count = 0
    if neo4j:
        try:
            neo4j_node_count, neo4j_edge_count, neo4j_community_count, _ = (
                neo4j.get_global_counts()
            )
        except Exception:
            pass

    return SystemHealth(
        services=services,
        neo4j_node_count=neo4j_node_count,
        neo4j_edge_count=neo4j_edge_count,
        neo4j_community_count=neo4j_community_count,
    )
