"""
Shared GraphRAG brain pipeline orchestration.

This module centralizes the full pipeline used by both:
- POST /api/community/detect
- Background task launched from POST /api/graph/save/{job_id}

Stages:
1. Community detection (hierarchical Leaf → Mid → Root) and leaf community assignment.
2. LLM summarization for each community at every level.
3. Embedding for entities and community summaries.
4. Persistence of community nodes, enriched Brain node, and cache warming.
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Dict, List, Tuple

from app.core.cache import cache_key_community_brain, cache_set
from app.core.config import settings
from app.core.logger import logger
from app.schemas.community import CommunityLevel, HierarchicalCommunity, UserBrain
from app.services.community_detection_service import build_user_brain
from app.services.embedding_service import EmbeddingService, entity_to_embed_text
from app.services.neo4j_service import Neo4jService
from app.services.summarization_service import SummarizationService


BRAIN_CACHE_TTL = 86400  # 24 hours


class NoUserGraphError(Exception):
    """Raised when a user has no merged graph in Neo4j."""


async def detect_communities_and_assign(
    user_id: str,
    neo4j: Neo4jService,
) -> Tuple[UserBrain, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """
    Run hierarchical community detection and write leaf community assignments.

    Returns:
        brain: Initial UserBrain (without communities_by_level filled).
        hierarchical_raw: Full hierarchical community list (all levels).
        nodes: All entity nodes for the user.
        edges: All relationships for the user.
        node_map: node_id -> node dict lookup.
    """
    loop = asyncio.get_running_loop()

    nodes, edges = await loop.run_in_executor(None, neo4j.get_user_graph, user_id)
    if not nodes:
        logger.info("No nodes found in Neo4j for user", user_id=user_id)
        raise NoUserGraphError("No nodes found in Neo4j for this user")

    doc_count = await loop.run_in_executor(None, neo4j.get_user_document_count, user_id)

    brain, flat_for_neo4j, hierarchical_raw = await loop.run_in_executor(
        None,
        build_user_brain,
        user_id,
        nodes,
        edges,
        doc_count,
        True,
    )

    # Write community_id onto every entity node (leaf-level only)
    await loop.run_in_executor(
        None,
        neo4j.save_community_assignments,
        user_id,
        flat_for_neo4j,
    )

    node_map: Dict[str, Dict[str, Any]] = {
        n.get("id") or n.get("label", ""): n
        for n in nodes
        if n.get("id") or n.get("label")
    }

    return brain, hierarchical_raw, nodes, edges, node_map


def summarize_hierarchy(
    hierarchical_raw: List[Dict[str, Any]],
    node_map: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> None:
    """
    Summarize all communities at leaf, mid, and root levels.

    Mutates hierarchical_raw in-place, adding a "summary" field to each community.
    """
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


def embed_and_persist_brain(
    user_id: str,
    neo4j: Neo4jService,
    brain: UserBrain,
    hierarchical_raw: List[Dict[str, Any]],
    nodes: List[Dict[str, Any]],
) -> Tuple[UserBrain, Dict[str, Any]]:
    """
    Embed entities and community summaries, persist community nodes and Brain node.

    Returns:
        brain: Updated UserBrain with communities_by_level populated.
        brain_dict: Dict form of brain (with nested communities_by_level) suitable for caching.
    """
    embedding_svc = EmbeddingService(api_key=settings.OPENAI_API_KEY)

    def _entity_fingerprint(node: Dict[str, Any]) -> str:
        """Stable fingerprint for an entity's Identity Card."""
        text = entity_to_embed_text(node) or ""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    # Group entity nodes by document so embeddings are written to the correct
    # document-scoped nodes (id is only guaranteed unique per document).
    nodes_by_document: Dict[str, List[Dict[str, Any]]] = {}
    for n in nodes:
        doc_name = n.get("document_name")
        if not doc_name:
            continue
        nodes_by_document.setdefault(doc_name, []).append(n)

    # Only embed entities whose fingerprint changed compared to what is stored in Neo4j.
    for document_name, doc_nodes in nodes_by_document.items():
        nodes_to_embed: List[Dict[str, Any]] = []
        fingerprints_by_id: Dict[str, str] = {}
        for node in doc_nodes:
            node_id = node.get("id") or node.get("label")
            if not node_id:
                continue
            new_fp = _entity_fingerprint(node)
            old_fp = node.get("embedding_fingerprint")
            if old_fp != new_fp:
                nodes_to_embed.append(node)
                fingerprints_by_id[node_id] = new_fp
        if not nodes_to_embed:
            continue
        entity_embeddings = embedding_svc.embed_entities(nodes_to_embed)
        neo4j.save_entity_embeddings(
            user_id,
            document_name,
            entity_embeddings,
            fingerprints_by_id,
        )

    # Community summaries: compute text fingerprint and only re-embed changed summaries.
    # Load existing embeddings + fingerprints from Neo4j so we can reuse unchanged ones.
    existing_communities = neo4j.get_community_embeddings_and_fingerprints(user_id)

    summary_texts: List[str] = []
    communities_to_embed: List[Dict[str, Any]] = []
    for c in hierarchical_raw:
        summary = c.get("summary") or ""
        community_id = c.get("community_id") or ""
        stored = existing_communities.get(community_id, {}) if community_id else {}
        old_fp = stored.get("summary_fingerprint")
        new_fp = hashlib.sha256(summary.encode("utf-8")).hexdigest()

        # If fingerprint unchanged and we have a stored embedding, reuse it and skip re-embedding.
        if old_fp == new_fp and stored.get("embedding") is not None:
            c["summary_fingerprint"] = old_fp
            c["embedding"] = stored.get("embedding")
            continue

        communities_to_embed.append(c)
        summary_texts.append(summary)
        c["summary_fingerprint"] = new_fp

    if communities_to_embed:
        summary_vectors = embedding_svc.embed_texts(summary_texts)
        for community, vec in zip(communities_to_embed, summary_vectors):
            community["embedding"] = vec

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
    brain_dict: Dict[str, Any] = brain.model_dump()
    brain_dict["communities_by_level"] = [h.model_dump() for h in communities_by_level]

    # Persist the brain permanently in Neo4j as a Brain node
    neo4j.save_brain_node(user_id, brain_dict)

    logger.success(
        "Community brain saved and enriched",
        user_id=user_id,
        communities=brain.community_count,
    )

    return brain, brain_dict


async def warm_brain_cache(user_id: str, brain_dict: Dict[str, Any]) -> None:
    """Warm the Redis cache for the user's brain."""
    await cache_set(
        cache_key_community_brain(user_id),
        brain_dict,
        ttl_seconds=BRAIN_CACHE_TTL,
    )


async def run_full_brain_pipeline_for_user(
    user_id: str,
    neo4j: Neo4jService,
) -> UserBrain:
    """
    High-level helper: run the full GraphRAG pipeline for a user.

    Used by POST /api/community/detect to execute the pipeline synchronously.
    """
    brain, hierarchical_raw, nodes, edges, node_map = await detect_communities_and_assign(
        user_id, neo4j
    )

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        summarize_hierarchy,
        hierarchical_raw,
        node_map,
        edges,
    )
    brain, brain_dict = await loop.run_in_executor(
        None,
        embed_and_persist_brain,
        user_id,
        neo4j,
        brain,
        hierarchical_raw,
        nodes,
    )
    await warm_brain_cache(user_id, brain_dict)
    return brain

