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


class SystemHealth(BaseModel):
    """System health and global Neo4j counts."""

    services: List[ServiceHealth] = Field(..., description="Health of each backing service")
    neo4j_node_count: int = Field(0, description="Total nodes in Neo4j")
    neo4j_edge_count: int = Field(0, description="Total edges in Neo4j")
    neo4j_community_count: int = Field(0, description="Total community nodes in Neo4j")
