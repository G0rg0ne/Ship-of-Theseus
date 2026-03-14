"""
GraphRAG query endpoint.

POST /api/query — Run the 4-stage pipeline (router → retrieval → pruning → synthesis)
and return the answer with source attribution. Conversation history is persisted per session.
Set body.stream=true for SSE streaming of synthesis tokens.
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.v1.deps import get_current_user
from app.core.logger import logger
from app.models.user import User
from app.schemas.query import QueryRequest, QueryResponse, SearchMode
from app.services.embedding_service import EmbeddingService
from app.services.neo4j_service import Neo4jService
from app.services.query_service import run_query_pipeline, run_query_pipeline_stream

router = APIRouter()


def get_neo4j_service(request: Request) -> Optional[Neo4jService]:
    """Dependency: Neo4j service from app.state (None if not configured)."""
    return getattr(request.app.state, "neo4j_service", None)


async def _stream_events(user_id: str, question: str, mode: str, session_id: Optional[str], neo4j: Neo4jService):
    """Async generator that yields SSE-formatted lines from the pipeline stream."""
    embedding_service = EmbeddingService()
    async for event in run_query_pipeline_stream(
        user_id=user_id,
        question=question,
        mode=mode,
        session_id=session_id,
        neo4j_service=neo4j,
        embedding_service=embedding_service,
    ):
        if event.get("type") == "chunk":
            yield f"data: {json.dumps({'content': event.get('content', '')})}\n\n"
        elif event.get("type") == "done":
            yield f"data: {json.dumps({'done': True, **{k: v for k, v in event.items() if k != 'type'}})}\n\n"


@router.post("")
async def query_brain(
    body: QueryRequest,
    current_user: User = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """
    Run a GraphRAG query against the current user's knowledge graph.

    Uses intent routing (global/local/hybrid), vector search on communities and entities,
    context pruning, and LLM synthesis with conversation history. Returns the answer
    and cited sources (communities and entities). Set stream=true for token streaming.
    """
    if not neo4j:
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not configured or unavailable",
        )
    user_id = str(current_user.id)
    mode = body.mode.value if isinstance(body.mode, SearchMode) else (body.mode or "auto")
    question = body.question.strip()

    if body.stream:
        return StreamingResponse(
            _stream_events(user_id, question, mode, body.session_id, neo4j),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        embedding_service = EmbeddingService()
        result = await run_query_pipeline(
            user_id=user_id,
            question=question,
            mode=mode,
            session_id=body.session_id,
            neo4j_service=neo4j,
            embedding_service=embedding_service,
        )
        return result
    except Exception as e:
        logger.exception("Query pipeline failed")
        raise HTTPException(status_code=500, detail="Query failed; please try again.") from e
