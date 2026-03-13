"""
Pydantic schemas for admin endpoints.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class PlatformStats(BaseModel):
    """Platform-wide statistics for the admin dashboard."""

    total_users: int = Field(..., description="Total number of registered users")
    active_users: int = Field(..., description="Number of active users")
    new_users_7d: int = Field(..., description="New users in the last 7 days")
    total_documents: int = Field(..., description="Total documents processed across all users")
    total_entities: int = Field(..., description="Total entity nodes in Neo4j")
    total_relationships: int = Field(..., description="Total relationship edges in Neo4j")
    total_communities: int = Field(..., description="Total community nodes in Neo4j")
    avg_docs_per_user: float = Field(..., description="Average documents per user (0 if no users)")


class UserAdminView(BaseModel):
    """User row for admin users list."""

    id: uuid.UUID
    username: str
    email: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    document_count: int = Field(..., description="Number of documents (graphs) for this user")

    class Config:
        from_attributes = True


class ServiceHealth(BaseModel):
    """Health status of a single service."""

    name: str = Field(..., description="Service name (e.g. PostgreSQL, Neo4j, Redis)")
    status: str = Field(..., description="One of: healthy, degraded, down")
    detail: Optional[str] = Field(None, description="Optional status detail or error message")


class StorageVolume(BaseModel):
    """Disk usage for a single mounted volume or path."""

    mount_path: str = Field(..., description="Filesystem path or mount point (e.g. /, /data)")
    total_bytes: int = Field(..., description="Total capacity in bytes")
    used_bytes: int = Field(..., description="Used space in bytes")
    free_bytes: int = Field(..., description="Free space in bytes")
    used_percent: float = Field(..., description="Used space percentage in [0,100]")
    status: str = Field(
        ...,
        description="One of: healthy, warning, critical – based on configured thresholds",
    )


class ServiceStorageStats(BaseModel):
    """Storage or memory usage for a backing service."""

    name: str = Field(..., description="Service name (e.g. PostgreSQL, Neo4j, Redis)")
    size_bytes: Optional[int] = Field(
        None,
        description="Total size in bytes for this service (DB/store/memory). None when unavailable.",
    )
    status: str = Field(
        "unknown",
        description="One of: healthy, warning, critical, unknown - interpreted by the backend.",
    )
    detail: Optional[str] = Field(
        None,
        description="Optional status detail or error message when computing size.",
    )


class InfraMetrics(BaseModel):
    """Infrastructure and storage metrics for admin dashboard."""

    volumes: List[StorageVolume] = Field(
        default_factory=list,
        description="Disk usage for relevant filesystem mount points.",
    )
    services: List[ServiceStorageStats] = Field(
        default_factory=list,
        description="Storage or memory usage for PostgreSQL, Neo4j, Redis, etc.",
    )


class SystemHealth(BaseModel):
    """System health and global Neo4j counts."""

    services: List[ServiceHealth] = Field(..., description="Health of each backing service")
    neo4j_node_count: int = Field(0, description="Total nodes in Neo4j")
    neo4j_edge_count: int = Field(0, description="Total edges in Neo4j")
    neo4j_community_count: int = Field(0, description="Total community nodes in Neo4j")
    infra: Optional[InfraMetrics] = Field(
        None,
        description="Optional infrastructure and storage metrics (disk, database sizes, Redis memory).",
    )
