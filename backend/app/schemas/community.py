"""
Pydantic schemas for community detection and user brain.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class CommunityLevel(str, Enum):
    """Hierarchy level of a community (Leaf = low, Mid = high, Root = top)."""
    leaf = "leaf"
    mid = "mid"
    root = "root"


class CommunityInfo(BaseModel):
    """Represents a detected knowledge community (cluster of related entities)."""

    community_id: str
    node_count: int
    top_entities: List[str]
    keywords: List[str]
    document_sources: List[str]


class HierarchicalCommunity(BaseModel):
    """Community at a specific level with LLM summary and optional embedding."""

    community_id: str
    level: CommunityLevel
    parent_community_id: Optional[str] = None
    node_count: int
    top_entities: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    document_sources: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    embedding: Optional[List[float]] = None


class UserBrain(BaseModel):
    """The merged knowledge representation for a user, built from all their documents."""

    user_id: str
    document_count: int
    total_nodes: int
    total_edges: int
    community_count: int
    communities: List[CommunityInfo] = Field(default_factory=list)
    communities_by_level: Optional[List[HierarchicalCommunity]] = None
    last_updated: str
    status: str = "ready"
