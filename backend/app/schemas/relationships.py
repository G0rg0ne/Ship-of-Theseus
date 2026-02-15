"""Schemas for relationship extraction and graph-ready output."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Relationship(BaseModel):
    """A single extracted relationship triplet (Entity A, Relation, Entity B)."""

    source: str = Field(description="Source entity name (must match an extracted entity)")
    relation_type: str = Field(
        description="Type of relationship (e.g., works_for, located_in, founded_by)"
    )
    target: str = Field(description="Target entity name (must match an extracted entity)")
    confidence: Optional[float] = Field(None, description="LLM confidence score")
    context: Optional[str] = Field(None, description="Text snippet supporting the relationship")


class ExtractedRelationships(BaseModel):
    """Relationships extracted from a single text chunk."""

    chunk_id: int = Field(description="Index of the chunk")
    relationships: List[Relationship] = Field(default_factory=list)


class GraphNode(BaseModel):
    """A node in the document graph (entity)."""

    id: str = Field(description="Unique identifier for the node")
    label: str = Field(description="Entity name / display label")
    type: str = Field(
        description="Entity type (e.g., person, organization, location, key_term)"
    )
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata from entity extraction",
    )


class GraphEdge(BaseModel):
    """An edge in the document graph (relationship)."""

    source: str = Field(description="Source node ID")
    target: str = Field(description="Target node ID")
    relation_type: str = Field(description="Type of relationship")
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="confidence, context, etc.",
    )


class DocumentGraph(BaseModel):
    """Graph-ready output: nodes (entities) and edges (relationships)."""

    filename: str
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    extracted_at: str
    entity_count: int = 0
    relationship_count: int = 0


class RelationshipJobStatus(BaseModel):
    """Status of a relationship extraction job (for progress tracking)."""

    job_id: str
    status: str  # pending | running | completed | failed
    entity_job_id: str = Field(description="Reference to the entity extraction job")
    total_chunks: int = 0
    completed_chunks: int = 0
    filename: Optional[str] = None
    created_at: Optional[str] = None
    error: Optional[str] = None
