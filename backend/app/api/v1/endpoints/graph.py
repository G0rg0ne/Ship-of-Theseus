"""
Graph persistence endpoints: save/retrieve document graphs to/from Neo4j.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.deps import get_current_user
from app.schemas.relationships import DocumentGraph
from app.core.cache import cache_get, cache_key_extraction_job, cache_key_relationship_job
from app.services.neo4j_service import Neo4jService

router = APIRouter()


def get_neo4j_service(request: Request) -> Optional[Neo4jService]:
    """Dependency: Neo4j service from app.state (None if not configured)."""
    return getattr(request.app.state, "neo4j_service", None)

RELATIONSHIP_JOB_ID_SUFFIX = "_rel"


def _relationship_job_id_for_entity_job(entity_job_id: str) -> str:
    """Return the relationship job id used when relationship extraction is auto-triggered."""
    return entity_job_id + RELATIONSHIP_JOB_ID_SUFFIX


async def _get_graph_from_cache(job_id: str, user_id: str) -> DocumentGraph:
    """Retrieve DocumentGraph from Redis by entity job_id. Raises HTTPException if not found or not completed."""
    entity_key = cache_key_extraction_job(job_id)
    entity_job = await cache_get(entity_key)
    if not entity_job:
        raise HTTPException(status_code=404, detail="Extraction job not found or expired")
    if entity_job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this job")
    if entity_job.get("status") != "completed":
        raise HTTPException(
            status_code=400,
            detail="Entity extraction not yet completed; wait for extraction to finish before saving to knowledge base.",
        )
    rel_job_id = _relationship_job_id_for_entity_job(job_id)
    rel_key = cache_key_relationship_job(rel_job_id)
    rel_job = await cache_get(rel_key)
    if not rel_job:
        raise HTTPException(
            status_code=400,
            detail="Relationship extraction not yet started or job expired.",
        )
    if rel_job.get("status") in ("running", "pending"):
        raise HTTPException(
            status_code=400,
            detail="Relationship extraction still in progress; wait for the graph to be ready.",
        )
    if rel_job.get("status") == "failed":
        raise HTTPException(
            status_code=500,
            detail=rel_job.get("error", "Relationship extraction failed"),
        )
    result = rel_job.get("result")
    if not result:
        raise HTTPException(status_code=404, detail="Graph result not available")
    return DocumentGraph(**result)


@router.post("/save/{job_id}")
async def save_graph_to_neo4j(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """
    Save the extracted graph for the given extraction job to Neo4j.
    Uses the entity extraction job_id; the graph is taken from the relationship extraction result.
    """
    from app.core.logger import logger
    user_id = current_user.get("email") or current_user.get("username", "default")
    document_graph = await _get_graph_from_cache(job_id, user_id)
    if not neo4j:
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not configured or unavailable",
        )
    try:
        neo4j.save_document_graph(document_graph)
        return {"ok": True, "message": "Graph saved to knowledge base", "document_name": document_graph.filename}
    except Exception as e:
        logger.exception("Failed to save graph to Neo4j", job_id=job_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save graph: {str(e)}")


@router.get("/list")
async def list_neo4j_documents(
    current_user: dict = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """List all document names and stats (node_count, edge_count) stored in Neo4j."""
    if not neo4j:
        raise HTTPException(status_code=503, detail="Neo4j is not configured or unavailable")
    try:
        items = neo4j.list_documents()
        return {"documents": items}
    except Exception as e:
        from app.core.logger import logger
        logger.exception("Failed to list Neo4j documents", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_name}", response_model=DocumentGraph)
async def get_graph_from_neo4j(
    document_name: str,
    current_user: dict = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """Retrieve a document graph from Neo4j by document name."""
    if not neo4j:
        raise HTTPException(status_code=503, detail="Neo4j is not configured or unavailable")
    graph = neo4j.get_document_graph(document_name)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"No graph found for document: {document_name}")
    return graph


@router.delete("/{document_name}")
async def delete_graph_from_neo4j(
    document_name: str,
    current_user: dict = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """Delete a document graph from Neo4j."""
    if not neo4j:
        raise HTTPException(status_code=503, detail="Neo4j is not configured or unavailable")
    try:
        neo4j.delete_document_graph(document_name)
        return {"ok": True, "message": f"Graph for '{document_name}' deleted"}
    except Exception as e:
        from app.core.logger import logger
        logger.exception("Failed to delete graph from Neo4j", document_name=document_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def neo4j_health(
    current_user: dict = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """Check Neo4j connectivity."""
    if not neo4j:
        return {"status": "unavailable", "message": "Neo4j not configured"}
    ok = neo4j.health_check()
    return {"status": "ok" if ok else "unhealthy"}
