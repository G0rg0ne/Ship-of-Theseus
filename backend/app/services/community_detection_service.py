"""
Community detection service.

Builds a merged, user-scoped knowledge graph from Neo4j and runs Louvain
community detection to identify clusters of related entities across all of
the user's processed documents.  Results are written back to Neo4j (each
node gets a `community_id` property) and returned as a UserBrain summary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.logger import logger
from app.schemas.community import CommunityInfo, UserBrain


def _build_networkx_graph(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]):
    """Build an undirected networkx Graph from node/edge dicts.

    Returns the graph and a node_id → node_dict lookup.
    """
    import networkx as nx  # noqa: PLC0415 – lazy import so the module loads even without networkx

    G: nx.Graph = nx.Graph()
    node_map: Dict[str, Dict[str, Any]] = {}

    for node in nodes:
        nid = node.get("id") or node.get("label", "")
        if not nid:
            continue
        node_map[nid] = node
        G.add_node(nid)

    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src and tgt and src in node_map and tgt in node_map:
            G.add_edge(src, tgt, relation_type=edge.get("relation_type", ""))

    return G, node_map


def _run_louvain(G) -> List[set]:
    """Run Louvain community detection, falling back to greedy modularity, then connected components."""
    import networkx as nx
    from networkx.algorithms import community as nx_community

    if G.number_of_nodes() == 0:
        return []

    try:
        return list(nx_community.louvain_communities(G, seed=42))
    except Exception as louvain_err:
        logger.warning("Louvain failed, trying greedy modularity", error=str(louvain_err))

    try:
        return list(nx_community.greedy_modularity_communities(G))
    except Exception as greedy_err:
        logger.warning("Greedy modularity failed, using connected components", error=str(greedy_err))

    return list(nx.connected_components(G))


def detect_communities(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Run community detection on a set of nodes and edges.

    Returns a list of community dicts:
        {community_id, node_ids, node_count, top_entities, keywords, document_sources}

    Communities are sorted largest-first.
    """
    if not nodes:
        return []

    G, node_map = _build_networkx_graph(nodes, edges)
    raw_communities = _run_louvain(G)

    result: List[Dict[str, Any]] = []
    for idx, community_nodes in enumerate(sorted(raw_communities, key=len, reverse=True)):
        community_id = f"community_{idx}"

        node_list = list(community_nodes)

        # Collect labels for the first 10 nodes (used as "top entities")
        top_entities: List[str] = []
        for nid in node_list[:10]:
            label = node_map.get(nid, {}).get("label") or nid
            if label:
                top_entities.append(label)

        # Key terms make good "keywords"
        keywords: List[str] = []
        for nid in node_list:
            nd = node_map.get(nid, {})
            etype = (nd.get("entity_type") or "").lower()
            if etype in ("key_term", "keyterm"):
                lbl = nd.get("label", "")
                if lbl:
                    keywords.append(lbl)
        keywords = keywords[:8]

        # Document sources for this community
        doc_sources: List[str] = list(
            {node_map.get(nid, {}).get("document_name", "") for nid in node_list}
            - {""}
        )

        result.append(
            {
                "community_id": community_id,
                "node_ids": node_list,
                "node_count": len(node_list),
                "top_entities": top_entities[:5],
                "keywords": keywords,
                "document_sources": doc_sources,
            }
        )

    return result


def build_user_brain(
    user_id: str,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    document_count: int,
) -> Tuple[UserBrain, List[Dict[str, Any]]]:
    """
    Detect communities and assemble the UserBrain model.

    Returns (UserBrain, communities_with_node_ids) – the second element is
    used by the caller to write community assignments back to Neo4j.
    """
    communities_raw = detect_communities(nodes, edges)

    community_infos: List[CommunityInfo] = [
        CommunityInfo(
            community_id=c["community_id"],
            node_count=c["node_count"],
            top_entities=c["top_entities"],
            keywords=c["keywords"],
            document_sources=c["document_sources"],
        )
        for c in communities_raw
    ]

    brain = UserBrain(
        user_id=user_id,
        document_count=document_count,
        total_nodes=len(nodes),
        total_edges=len(edges),
        community_count=len(community_infos),
        communities=community_infos,
        last_updated=datetime.now(timezone.utc).isoformat(),
        status="ready",
    )

    logger.success(
        "Community detection complete",
        user_id=user_id,
        nodes=len(nodes),
        edges=len(edges),
        communities=len(community_infos),
    )
    return brain, communities_raw
