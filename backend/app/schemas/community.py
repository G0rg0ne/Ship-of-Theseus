"""
Pydantic schemas for community detection and user brain.
"""
from typing import List

from pydantic import BaseModel


class CommunityInfo(BaseModel):
    """Represents a detected knowledge community (cluster of related entities)."""

    community_id: str
    node_count: int
    top_entities: List[str]
    keywords: List[str]
    document_sources: List[str]


class UserBrain(BaseModel):
    """The merged knowledge representation for a user, built from all their documents."""

    user_id: str
    document_count: int
    total_nodes: int
    total_edges: int
    community_count: int
    communities: List[CommunityInfo]
    last_updated: str
    status: str = "ready"
