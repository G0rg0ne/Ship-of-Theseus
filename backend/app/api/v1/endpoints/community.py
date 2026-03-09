"""
Community detection endpoints.

GET  /api/community/brain   – Return the current user's knowledge brain.
POST /api/community/detect  – Manually trigger community detection (full GraphRAG
                               pipeline: hierarchical → summarization → embedding → save).

Read priority for GET /brain:
  1. Redis cache  (fastest)
  2. Neo4j Brain node  (permanent, survives cache expiry)
  3. Recompute from entity nodes  (fallback if no brain stored yet)
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.deps import get_current_user
from app.core.cache import cache_delete, cache_get, cache_key_community_brain, cache_set
from app.core.config import settings
from app.core.logger import logger
from app.models.user import User
from app.schemas.community import CommunityLevel, HierarchicalCommunity, UserBrain
from app.services.embedding_service import EmbeddingService
from app.services.neo4j_service import Neo4jService
from app.services.summarization_service import SummarizationService

router = APIRouter()

BRAIN_CACHE_TTL = 86400  # 24 hours


def get_neo4j_service(request: Request) -> Optional[Neo4jService]:
    """Dependency: Neo4j service from app.state (None if not configured)."""
    return getattr(request.app.state, "neo4j_service", None)


@router.get("/brain", response_model=UserBrain)
async def get_user_brain(
    current_user: User = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """
    Return the current user's knowledge brain (community detection results).

    Checks Redis first (fast path), then loads the permanent Brain node from
    Neo4j, and finally falls back to a live recompute if neither exists yet.
    """
    user_id = current_user.email or current_user.username

    if not neo4j:
        raise HTTPException(status_code=503, detail="Neo4j is not configured or unavailable")

    # 1. Fast path: Redis cache (only trust it if Neo4j still has the Brain node, so we don't
    #    return a deleted brain after Redis restarts from a persisted snapshot)
    cached = await cache_get(cache_key_community_brain(user_id))
    if cached:
        brain_data = neo4j.get_brain_node(user_id)
        if brain_data is None:
            await cache_delete(cache_key_community_brain(user_id))
        else:
            return UserBrain(**cached)

    # 2. Permanent path: Brain node in Neo4j
    brain_data = neo4j.get_brain_node(user_id)
    if brain_data:
        # Re-warm the cache so subsequent reads hit Redis
        await cache_set(cache_key_community_brain(user_id), brain_data, ttl_seconds=BRAIN_CACHE_TTL)
        return UserBrain(**brain_data)

    # 3. Fallback: recompute from entity nodes
    nodes, edges = neo4j.get_user_graph(user_id)
    if not nodes:
        raise HTTPException(
            status_code=404,
            detail="No knowledge brain found. Add documents to the knowledge base first.",
        )

    doc_count = neo4j.get_user_document_count(user_id)
    from app.services.community_detection_service import build_user_brain
    brain, flat_for_neo4j, _ = build_user_brain(
        user_id, nodes, edges, doc_count, hierarchical=True
    )
    neo4j.save_community_assignments(user_id, flat_for_neo4j)
    neo4j.save_brain_node(user_id, brain.model_dump())
    await cache_set(cache_key_community_brain(user_id), brain.model_dump(), ttl_seconds=BRAIN_CACHE_TTL)
    return brain



@router.post("/detect", response_model=UserBrain)
async def trigger_community_detection(
    current_user: User = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """
    Manually trigger the full GraphRAG pipeline for the current user.

    Runs hierarchical community detection (Leaf → Mid → Root), LLM summarization
    for every community at every level, entity and summary embedding with
    text-embedding-3-small, then persists assignments, community nodes, and
    embeddings to Neo4j. Returns the enriched brain with communities_by_level.
    """
    user_id = current_user.email or current_user.username

    if not neo4j:
        raise HTTPException(status_code=503, detail="Neo4j is not configured or unavailable")

    logger.info("Full GraphRAG pipeline triggered", user_id=user_id)
    nodes, edges = neo4j.get_user_graph(user_id)
    if not nodes:
        raise HTTPException(
            status_code=404,
            detail="No nodes found in Neo4j. Add documents to the knowledge base first.",
        )

    doc_count = neo4j.get_user_document_count(user_id)
    from app.services.community_detection_service import build_user_brain

    brain, flat_for_neo4j, hierarchical_raw = build_user_brain(
        user_id, nodes, edges, doc_count, hierarchical=True
    )

    # Write community_id onto every entity node (leaf-level only)
    neo4j.save_community_assignments(user_id, flat_for_neo4j)

    node_map = {n.get("id") or n.get("label", ""): n for n in nodes if n.get("id") or n.get("label")}

    # Summarization: leaf → mid → root (each level may use child summaries)
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

    # Embedding: entities (Identity Card) then community summaries
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
    brain_dict["communities_by_level"] = [h.model_dump() for h in communities_by_level]

    neo4j.save_brain_node(user_id, brain_dict)
    await cache_set(cache_key_community_brain(user_id), brain_dict, ttl_seconds=BRAIN_CACHE_TTL)
    return brain


@router.delete("/brain")
async def delete_user_brain(
    current_user: User = Depends(get_current_user),
    neo4j: Optional[Neo4jService] = Depends(get_neo4j_service),
):
    """
    Permanently delete the current user's brain and all their document graphs from Neo4j,
    and clear the brain cache in Redis. Use for "start from scratch".
    """
    user_id = current_user.email or current_user.username

    if not neo4j:
        raise HTTPException(status_code=503, detail="Neo4j is not configured or unavailable")

    try:
        neo4j.delete_user_data(user_id)
        await cache_delete(cache_key_community_brain(user_id))
        return {"ok": True, "message": "Brain and all user data deleted"}
    except Exception as e:
        logger.exception("Failed to delete user brain", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
