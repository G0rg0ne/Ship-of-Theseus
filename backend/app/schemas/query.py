"""
Pydantic schemas for GraphRAG query pipeline (request, response, sources).
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SearchMode(str, Enum):
    """Query routing: auto (router decides), global, local, or hybrid."""

    auto = "auto"
    global_ = "global"
    local = "local"
    hybrid = "hybrid"


class SourceAttribution(BaseModel):
    """A single cited source (community or entity) in the answer."""

    type: str  # "community" | "entity"
    id: str
    level: Optional[str] = None  # for community: "root" | "mid" | "leaf"
    excerpt: Optional[str] = None
    label: Optional[str] = None  # for entity: display name


class QueryRequest(BaseModel):
    """Request body for POST /api/query."""

    question: str = Field(..., min_length=1, description="User question")
    mode: SearchMode = Field(default=SearchMode.auto, description="Search depth mode")
    session_id: Optional[str] = Field(default=None, description="Conversation session UUID; generated if omitted")
    stream: bool = Field(default=False, description="If true, response is SSE stream of tokens then metadata")


class QueryResponse(BaseModel):
    """Response from POST /api/query."""

    answer: str = Field(..., description="Synthesized answer from graph context")
    mode_used: str = Field(..., description="Actual mode used: global, local, or hybrid")
    session_id: str = Field(..., description="Conversation session ID (echo or generated)")
    sources: List[SourceAttribution] = Field(default_factory=list, description="Cited communities/entities")


class ChatMessage(BaseModel):
    """A single message in conversation history (for Redis serialization)."""

    role: str  # "human" | "ai"
    content: str
