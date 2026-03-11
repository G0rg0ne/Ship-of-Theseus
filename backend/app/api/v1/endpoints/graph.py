"""
Graph persistence endpoints: save/retrieve document graphs to/from Neo4j.
After a document graph is saved, the full GraphRAG pipeline (community
detection → summarization → embedding) is automatically triggered in the
background to rebuild the user's merged knowledge brain.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.api.v1.deps import get_current_user
from app.core.cache import (
    cache_get,
    cache_key_pipeline_job,
    cache_key_extraction_job,
    cache_key_relationship_job,
    cache_set,
)
from app.core.logger import logger
from app.models.user import User
from app.schemas.community import CommunityLevel
from app.schemas.relationships import DocumentGraph
from app.services.brain_pipeline_service import NoUserGraphError, run_full_brain_pipeline_for_user
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



PIPELINE_JOB_TTL = 60 * 60  # 1 hour


async def _set_pipeline_status(
    pipeline_job_id: str,
    *,
    status: str,
    step: str,
    step_index: int,
    total_steps: int,
    message: str,
    user_id: str,
    community_progress: Optional[Dict[str, int]] = None,
    error: Optional[str] = None,
) -> None:
    """Persist a snapshot of the long-running pipeline status in cache."""
    payload: Dict[str, Any] = {
        "pipeline_job_id": pipeline_job_id,
        "status": status,
        "step": step,
        "step_index": step_index,
        "total_steps": total_steps,
        "message": message,
        "user_id": user_id,
    }
    if community_progress is not None:
        payload["community_progress"] = community_progress
    if error is not None:
        payload["error"] = error
    await cache_set(cache_key_pipeline_job(pipeline_job_id), payload, ttl_seconds=PIPELINE_JOB_TTL)


async def _background_full_pipeline(
    pipeline_job_id: str,
    *,
    neo4j_user_id: str,
    cache_user_id: str,
    neo4j: Neo4jService,
) -> None:
    """Run the full GraphRAG pipeline for a user in the background.

    Called as a FastAPI BackgroundTask after saving a document graph.
    """
    logger.info(
        "Background full graph pipeline started",
        user_id=neo4j_user_id,
        pipeline_job_id=pipeline_job_id,
    )
    total_steps = 3  # community_detection, summarizing, embedding

    async def _on_step(step: str, step_index: int, total: int, message: str) -> None:
        await _set_pipeline_status(
            pipeline_job_id,
            status="running",
            step=step,
            step_index=step_index,
            total_steps=total,
            message=message,
            user_id=cache_user_id,
        )

    try:
        last_sent_completed: int = -1
        debounce_every: int = 5
        last_level: Optional[CommunityLevel] = None

        async def _on_summarization_progress(
            level: CommunityLevel, completed: int, total: int
        ) -> None:
            nonlocal last_sent_completed, last_level
            if last_level is not None and level != last_level:
                last_sent_completed = -1
            last_level = level
            if completed != total and (completed - last_sent_completed) < debounce_every:
                return
            last_sent_completed = completed
            await _set_pipeline_status(
                pipeline_job_id,
                status="running",
                step="summarizing",
                step_index=2,
                total_steps=total_steps,
                message=f"Summarizing {level.value} communities… {completed}/{total}",
                user_id=cache_user_id,
                community_progress={"completed": completed, "total": total},
            )

        await run_full_brain_pipeline_for_user(
            neo4j_user_id,
            neo4j,
            on_step=_on_step,
            on_summarization_progress=_on_summarization_progress,
        )

        await _set_pipeline_status(
            pipeline_job_id,
            status="done",
            step="done",
            step_index=total_steps,
            total_steps=total_steps,
            message="Knowledge brain updated successfully.",
            user_id=cache_user_id,
        )
        logger.success(
            "Community brain saved, enriched and cached",
            user_id=neo4j_user_id,
            pipeline_job_id=pipeline_job_id,
        )
    except NoUserGraphError:
        logger.info(
            "No nodes found for community detection",
            user_id=neo4j_user_id,
            pipeline_job_id=pipeline_job_id,
        )
        await _set_pipeline_status(
            pipeline_job_id,
            status="failed",
            step="community_detection",
            step_index=1,
            total_steps=total_steps,
            message="No nodes found in Neo4j. Add documents to the knowledge base first.",
            user_id=cache_user_id,
            error="no_nodes",
        )
    except Exception as exc:
        await _set_pipeline_status(
            pipeline_job_id,
            status="failed",
            step="error",
            step_index=0,
            total_steps=total_steps,
            message="Graph pipeline failed.",
            user_id=cache_user_id,
            error=str(exc),
        )
        logger.exception(
            "Full graph pipeline background task failed",
            user_id=neo4j_user_id,
            pipeline_job_id=pipeline_job_id,
            error=str(exc),
        )


@router.post("/save/{job_id}")
async def save_graph_to_neo4j(
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """
    Save the extracted graph for the given extraction job to Neo4j,
    then trigger the full GraphRAG pipeline in the background.
    """
    from uuid import uuid4

    cache_user_id = current_user.email or current_user.username
    neo4j_user_id = str(current_user.id)
    document_graph = await _get_graph_from_cache(job_id, neo4j_user_id)
    if not neo4j:
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not configured or unavailable",
        )
    try:
        neo4j.save_document_graph(document_graph, user_id=neo4j_user_id)
        pipeline_job_id = str(uuid4())
        background_tasks.add_task(
            _background_full_pipeline,
            pipeline_job_id,
            neo4j_user_id=neo4j_user_id,
            cache_user_id=cache_user_id,
            neo4j=neo4j,
        )
        return {
            "ok": True,
            "message": "Graph saved to knowledge base; background pipeline started.",
            "document_name": document_graph.filename,
            "pipeline_job_id": pipeline_job_id,
        }
    except Exception as e:
        logger.exception("Failed to save graph to Neo4j", job_id=job_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save graph: {str(e)}")


@router.get("/list")
async def list_neo4j_documents(
    current_user: User = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """List all document names and stats (node_count, edge_count) stored in Neo4j."""
    if not neo4j:
        raise HTTPException(status_code=503, detail="Neo4j is not configured or unavailable")
    try:
        neo4j_user_id = str(current_user.id)
        items = neo4j.list_documents(user_id=neo4j_user_id)
        return {"documents": items}
    except Exception as e:
        from app.core.logger import logger
        logger.exception("Failed to list Neo4j documents", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_name}", response_model=DocumentGraph)
async def get_graph_from_neo4j(
    document_name: str,
    current_user: User = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """Retrieve a document graph from Neo4j by document name."""
    if not neo4j:
        raise HTTPException(status_code=503, detail="Neo4j is not configured or unavailable")
    neo4j_user_id = str(current_user.id)
    graph = neo4j.get_document_graph(document_name, user_id=neo4j_user_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"No graph found for document: {document_name}")
    return graph


@router.delete("/{document_name}")
async def delete_graph_from_neo4j(
    document_name: str,
    current_user: User = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """Delete a document graph from Neo4j."""
    if not neo4j:
        raise HTTPException(status_code=503, detail="Neo4j is not configured or unavailable")
    try:
        neo4j_user_id = str(current_user.id)
        neo4j.delete_document_graph(document_name, user_id=neo4j_user_id)
        return {"ok": True, "message": f"Graph for '{document_name}' deleted"}
    except Exception as e:
        from app.core.logger import logger
        logger.exception("Failed to delete graph from Neo4j", document_name=document_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def neo4j_health(
    current_user: User = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """Check Neo4j connectivity."""
    if not neo4j:
        return {"status": "unavailable", "message": "Neo4j not configured"}
    ok = neo4j.health_check()
    return {"status": "ok" if ok else "unhealthy"}


@router.get("/pipeline/status/{pipeline_job_id}")
async def get_pipeline_status(
    pipeline_job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Return the status of a long-running graph pipeline job."""
    user_id = current_user.email or current_user.username
    job = await cache_get(cache_key_pipeline_job(pipeline_job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Pipeline job not found")
    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this pipeline job")
    return job
