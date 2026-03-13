"""
Admin endpoints: platform stats, user list, system health, toggle admin.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_admin_user
from app.core.logger import logger
from app.db.database import get_db
from app.models.user import User
from app.schemas.admin import PlatformStats, SystemHealth, UserAdminView
from app.services.admin_service import (
    get_all_users as svc_get_all_users,
    get_platform_stats as svc_get_platform_stats,
    get_system_health as svc_get_system_health,
    get_admin_count,
)
from app.services.neo4j_service import Neo4jService
from app.services.user_service import get_user_by_id

router = APIRouter()


def get_neo4j_service(request: Request) -> Neo4jService | None:
    """Neo4j service from app.state."""
    return getattr(request.app.state, "neo4j_service", None)


@router.get("/stats", response_model=PlatformStats)
async def get_stats(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    neo4j: Neo4jService | None = Depends(get_neo4j_service),
):
    """Return platform-wide statistics (admin only)."""
    return await svc_get_platform_stats(db, neo4j)


@router.get("/users", response_model=list[UserAdminView])
async def list_users(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    neo4j: Neo4jService | None = Depends(get_neo4j_service),
    page: int = 1,
    limit: int = 20,
):
    """List users with document counts, paginated (admin only)."""
    if page < 1 or limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="page must be >= 1, limit between 1 and 100",
        )
    return await svc_get_all_users(db, neo4j, page=page, limit=limit)


@router.get("/system", response_model=SystemHealth)
async def get_system(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    neo4j: Neo4jService | None = Depends(get_neo4j_service),
):
    """Return system health for all backing services (admin only)."""
    return await svc_get_system_health(db, neo4j)


@router.patch("/users/{user_id}/toggle-admin", response_model=UserAdminView)
async def toggle_user_admin(
    user_id: uuid.UUID,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    neo4j: Neo4jService | None = Depends(get_neo4j_service),
):
    """Promote or demote a user's admin status (admin only)."""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # Prevent removing the last remaining admin
    if user.is_admin:
        admin_count = await get_admin_count(db)
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last admin user",
            )
    user.is_admin = not user.is_admin
    await db.flush()
    await db.refresh(user)
    logger.info(
        "Admin status toggled",
        target_user_id=str(user_id),
        new_is_admin=user.is_admin,
        by_username=current_user.username,
    )
    doc_count = 0
    if neo4j:
        try:
            doc_count = neo4j.get_user_document_count(str(user.id))
        except Exception:
            pass
    return UserAdminView(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at,
        document_count=doc_count,
    )


@router.patch("/users/{user_id}/toggle-active", response_model=UserAdminView)
async def toggle_user_active(
    user_id: uuid.UUID,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    neo4j: Neo4jService | None = Depends(get_neo4j_service),
):
    """
    Activate or deactivate a user account (admin only).

    - Prevents an admin from changing their own active status
    - Prevents deactivating the last active admin user
    """
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own active status",
        )

    new_is_active = not user.is_active

    # If we are about to deactivate an admin, ensure they are not the last active admin.
    if user.is_admin and user.is_active and not new_is_active:
        admin_count = await get_admin_count(db)
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active admin user",
            )

    user.is_active = new_is_active
    await db.flush()
    await db.refresh(user)

    logger.info(
        "User active status toggled",
        target_user_id=str(user_id),
        new_is_active=user.is_active,
        by_username=current_user.username,
    )

    doc_count = 0
    if neo4j:
        try:
            doc_count = neo4j.get_user_document_count(str(user.id))
        except Exception:
            pass

    return UserAdminView(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at,
        document_count=doc_count,
    )
