"""
Graph persistence endpoints: save/retrieve document graphs to/from Neo4j.
After a document graph is saved, the full GraphRAG pipeline (community
detection → summarization → embedding) is automatically triggered in the
background to rebuild the user's merged knowledge brain.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.api.v1.deps import get_current_user
from app.core.cache import (
    cache_get,
    cache_key_community_brain,
    cache_key_extraction_job,
    cache_key_pipeline_job,
    cache_key_relationship_job,
    cache_set,
)
from app.core.config import settings
from app.models.user import User
from app.schemas.community import CommunityLevel, HierarchicalCommunity, UserBrain
from app.schemas.relationships import DocumentGraph
from app.services.embedding_service import EmbeddingService
from app.services.neo4j_service import Neo4jService
from app.services.summarization_service import SummarizationService

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



BRAIN_CACHE_TTL = 86400  # 24 hours
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
    if error is not None:
        payload["error"] = error
    await cache_set(cache_key_pipeline_job(pipeline_job_id), payload, ttl_seconds=PIPELINE_JOB_TTL)


async def _background_full_pipeline(pipeline_job_id: str, user_id: str, neo4j: Neo4jService) -> None:
    """Run the full GraphRAG pipeline for user_id in the background.

    Called as a FastAPI BackgroundTask after saving a document graph.
    """
    from app.core.logger import logger
    from app.services.community_detection_service import build_user_brain

    logger.info(
        "Background full graph pipeline started",
        user_id=user_id,
        pipeline_job_id=pipeline_job_id,
    )
    total_steps = 3  # community_detection, summarizing, embedding
    try:
        # Step 1: community detection
        await _set_pipeline_status(
            pipeline_job_id,
            status="running",
            step="community_detection",
            step_index=1,
            total_steps=total_steps,
            message="Detecting communities…",
            user_id=user_id,
        )

        nodes, edges = neo4j.get_user_graph(user_id)
        if not nodes:
            logger.info(
                "No nodes found for community detection",
                user_id=user_id,
                pipeline_job_id=pipeline_job_id,
            )
            await _set_pipeline_status(
                pipeline_job_id,
                status="failed",
                step="community_detection",
                step_index=1,
                total_steps=total_steps,
                message="No nodes found in Neo4j. Add documents to the knowledge base first.",
                user_id=user_id,
                error="no_nodes",
            )
            return

        doc_count = neo4j.get_user_document_count(user_id)

        brain, flat_for_neo4j, hierarchical_raw = build_user_brain(
            user_id, nodes, edges, doc_count, hierarchical=True
        )

        # Write community_id onto every entity node (leaf-level only)
        neo4j.save_community_assignments(user_id, flat_for_neo4j)

        node_map = {
            n.get("id") or n.get("label", ""): n
            for n in nodes
            if n.get("id") or n.get("label")
        }

        # Step 2: summarization (leaf → mid → root)
        await _set_pipeline_status(
            pipeline_job_id,
            status="running",
            step="summarizing",
            step_index=2,
            total_steps=total_steps,
            message="Summarizing communities…",
            user_id=user_id,
        )

        summarization = SummarizationService(api_key=settings.OPENAI_API_KEY)
        summaries_by_cid: Dict[str, str] = {}
        for level in (CommunityLevel.leaf, CommunityLevel.mid, CommunityLevel.root):
            summarization.summarize_level(
                hierarchical_raw,
                level,
                node_map,
                edges,
                summaries_by_cid,
            )

        # Step 3: embeddings (entities + community summaries)
        await _set_pipeline_status(
            pipeline_job_id,
            status="running",
            step="embedding",
            step_index=3,
            total_steps=total_steps,
            message="Embedding entities and community summaries…",
            user_id=user_id,
        )

        embedding_svc = EmbeddingService(api_key=settings.OPENAI_API_KEY)
        entity_embeddings = embedding_svc.embed_entities(nodes)
        neo4j.save_entity_embeddings(user_id, entity_embeddings)

        summary_texts = [c.get("summary") or "" for c in hierarchical_raw]
        summary_vectors = embedding_svc.embed_texts(summary_texts)
        for c, vec in zip(hierarchical_raw, summary_vectors):
            c["embedding"] = vec
        neo4j.save_community_nodes(user_id, hierarchical_raw)

        # Build enriched brain with communities_by_level
        communities_by_level: List[HierarchicalCommunity] = [
            HierarchicalCommunity(
                community_id=c["community_id"],
                level=CommunityLevel(c["level"]),
                parent_community_id=c.get("parent_community_id"),
                node_count=len(c.get("node_ids") or []),
                top_entities=c.get("top_entities", []),
                keywords=c.get("keywords", []),
                document_sources=c.get("document_sources", []),
                summary=c.get("summary"),
                embedding=c.get("embedding"),
            )
            for c in hierarchical_raw
        ]
        brain.communities_by_level = communities_by_level
        brain_dict = brain.model_dump()
        brain_dict["communities_by_level"] = [
            h.model_dump() for h in communities_by_level
        ]

        # Persist the brain permanently in Neo4j as a Brain node
        neo4j.save_brain_node(user_id, brain_dict)

        # Also warm the Redis cache so the next read is instant
        await cache_set(
            cache_key_community_brain(user_id),
            brain_dict,
            ttl_seconds=BRAIN_CACHE_TTL,
        )

        await _set_pipeline_status(
            pipeline_job_id,
            status="done",
            step="done",
            step_index=total_steps,
            total_steps=total_steps,
            message="Knowledge brain updated successfully.",
            user_id=user_id,
        )
        logger.success(
            "Community brain saved, enriched and cached",
            user_id=user_id,
            pipeline_job_id=pipeline_job_id,
            communities=brain.community_count,
        )
    except Exception as exc:
        await _set_pipeline_status(
            pipeline_job_id,
            status="failed",
            step="error",
            step_index=0,
            total_steps=total_steps,
            message="Graph pipeline failed.",
            user_id=user_id,
            error=str(exc),
        )
        logger.exception(
            "Full graph pipeline background task failed",
            user_id=user_id,
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
    from app.core.logger import logger
    from uuid import uuid4

    user_id = current_user.email or current_user.username
    document_graph = await _get_graph_from_cache(job_id, user_id)
    if not neo4j:
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not configured or unavailable",
        )
    try:
        neo4j.save_document_graph(document_graph, user_id=user_id)
        pipeline_job_id = str(uuid4())
        background_tasks.add_task(
            _background_full_pipeline,
            pipeline_job_id,
            user_id,
            neo4j,
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
        items = neo4j.list_documents()
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
    graph = neo4j.get_document_graph(document_name)
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
        neo4j.delete_document_graph(document_name)
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
