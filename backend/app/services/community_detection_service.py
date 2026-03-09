"""
Community detection service.

Builds a merged, user-scoped knowledge graph from Neo4j and runs Louvain
community detection to identify clusters of related entities across all of
the user's processed documents. Supports flat detection (legacy) and
hierarchical partitioning: Leaf → Mid → Root. Results are written back to
Neo4j (each node gets a `community_id` property) and returned as a UserBrain summary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.logger import logger
from app.schemas.community import CommunityInfo, CommunityLevel, UserBrain


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


def _community_metadata(
    node_list: List[str],
    node_map: Dict[str, Dict[str, Any]],
) -> Tuple[List[str], List[str], List[str]]:
    """Return (top_entities, keywords, document_sources) for a list of node ids."""
    top_entities: List[str] = []
    for nid in node_list[:10]:
        label = node_map.get(nid, {}).get("label") or nid
        if label:
            top_entities.append(label)
    keywords: List[str] = []
    for nid in node_list:
        nd = node_map.get(nid, {})
        etype = (nd.get("entity_type") or "").lower()
        if etype in ("key_term", "keyterm"):
            lbl = nd.get("label", "")
            if lbl:
                keywords.append(lbl)
    keywords = keywords[:8]
    doc_sources: List[str] = list(
        {node_map.get(nid, {}).get("document_name", "") for nid in node_list}
        - {""}
    )
    return top_entities[:5], keywords, doc_sources


def _build_meta_graph(
    partition: List[List[str]],
    edges: List[Dict[str, Any]],
) -> Any:
    """
    Build a meta-graph where each node is a community (index).
    Edge (i, j) exists if any entity in community i is linked to any entity in community j.
    """
    import networkx as nx

    G = nx.Graph()
    for i in range(len(partition)):
        G.add_node(i)
    node_set_per_community = [set(c) for c in partition]
    for edge in edges:
        src, tgt = edge.get("source"), edge.get("target")
        if not src or not tgt:
            continue
        for i, node_set in enumerate(node_set_per_community):
            if src not in node_set:
                continue
            for j, other_set in enumerate(node_set_per_community):
                if i != j and tgt in other_set:
                    G.add_edge(i, j)
                    break
            break
    return G


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


def detect_hierarchical_communities(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Run three-level hierarchical community detection: Leaf → Mid → Root.

    Returns a list of community dicts, each with:
      community_id, level (leaf|mid|root), parent_community_id, node_ids,
      child_community_ids, top_entities, keywords, document_sources.
    Entity nodes are assigned to leaf communities; mid/root aggregate by meta-graph.
    """
    if not nodes:
        return []

    G, node_map = _build_networkx_graph(nodes, edges)
    # Leaf level: Louvain on entity graph
    leaf_raw = _run_louvain(G)
    leaf_sorted = sorted(leaf_raw, key=len, reverse=True)
    leaf_partition: List[List[str]] = [list(s) for s in leaf_sorted]

    hierarchical: List[Dict[str, Any]] = []
    leaf_id_by_index: Dict[int, str] = {}
    for idx, node_list in enumerate(leaf_partition):
        cid = f"leaf_{idx}"
        leaf_id_by_index[idx] = cid
        top_entities, keywords, doc_sources = _community_metadata(node_list, node_map)
        hierarchical.append({
            "community_id": cid,
            "level": CommunityLevel.leaf.value,
            "parent_community_id": None,  # set after mid is computed
            "node_ids": node_list,
            "child_community_ids": [],
            "top_entities": top_entities,
            "keywords": keywords,
            "document_sources": doc_sources,
        })

    if len(leaf_partition) == 0:
        return hierarchical

    # Mid level: meta-graph of leaf communities
    meta_leaf = _build_meta_graph(leaf_partition, edges)
    mid_raw = _run_louvain(meta_leaf)
    mid_sorted = sorted(mid_raw, key=len, reverse=True)
    mid_partition: List[List[int]] = [list(s) for s in mid_sorted]

    mid_id_by_index: Dict[int, str] = {}
    for idx, leaf_indices in enumerate(mid_partition):
        cid = f"mid_{idx}"
        mid_id_by_index[idx] = cid
        node_ids_mid: List[str] = []
        child_ids = [leaf_id_by_index[i] for i in leaf_indices]
        for i in leaf_indices:
            node_ids_mid.extend(leaf_partition[i])
        top_entities, keywords, doc_sources = _community_metadata(node_ids_mid, node_map)
        hierarchical.append({
            "community_id": cid,
            "level": CommunityLevel.mid.value,
            "parent_community_id": None,
            "node_ids": node_ids_mid,
            "child_community_ids": child_ids,
            "top_entities": top_entities,
            "keywords": keywords,
            "document_sources": doc_sources,
        })
        for i in leaf_indices:
            for h in hierarchical:
                if h["community_id"] == leaf_id_by_index[i]:
                    h["parent_community_id"] = cid
                    break

    if len(mid_partition) <= 1:
        # Single mid: treat as root
        for h in hierarchical:
            if h["level"] == CommunityLevel.mid.value:
                h["parent_community_id"] = "root_0"
        root_0_node_ids: List[str] = []
        for leaf_idx in mid_partition[0]:
            root_0_node_ids.extend(leaf_partition[leaf_idx])
        top_entities, keywords, doc_sources = _community_metadata(
            root_0_node_ids, node_map
        )
        hierarchical.append({
            "community_id": "root_0",
            "level": CommunityLevel.root.value,
            "parent_community_id": None,
            "node_ids": root_0_node_ids,
            "child_community_ids": [mid_id_by_index[0]],
            "top_entities": top_entities,
            "keywords": keywords,
            "document_sources": doc_sources,
        })
        return hierarchical

    # Root level: meta-graph of mid communities (edge if leaves in different mids are linked)
    meta_mid = _build_meta_graph_for_mids(leaf_partition, mid_partition, edges)
    root_raw = _run_louvain(meta_mid)
    root_sorted = sorted(root_raw, key=len, reverse=True)
    root_partition: List[List[int]] = [list(s) for s in root_sorted]

    root_id_by_index: Dict[int, str] = {}
    for idx, mid_indices in enumerate(root_partition):
        cid = f"root_{idx}"
        root_id_by_index[idx] = cid
        node_ids_root: List[str] = []
        child_ids = [mid_id_by_index[i] for i in mid_indices]
        for i in mid_indices:
            for li in mid_partition[i]:
                node_ids_root.extend(leaf_partition[li])
        node_ids_root = list(dict.fromkeys(node_ids_root))
        top_entities, keywords, doc_sources = _community_metadata(
            node_ids_root, node_map
        )
        hierarchical.append({
            "community_id": cid,
            "level": CommunityLevel.root.value,
            "parent_community_id": None,
            "node_ids": node_ids_root,
            "child_community_ids": child_ids,
            "top_entities": top_entities,
            "keywords": keywords,
            "document_sources": doc_sources,
        })
        for i in mid_indices:
            for h in hierarchical:
                if h["community_id"] == mid_id_by_index[i]:
                    h["parent_community_id"] = cid
                    break

    return hierarchical


def _build_meta_graph_for_mids(
    leaf_partition: List[List[str]],
    mid_partition: List[List[int]],
    edges: List[Dict[str, Any]],
) -> Any:
    """Build graph of mid indices: edge (i, j) if a leaf in mid i links to a leaf in mid j."""
    import networkx as nx

    G = nx.Graph()
    for i in range(len(mid_partition)):
        G.add_node(i)

    # Use sets for O(1) membership checks instead of lists
    leaf_sets = [set(leaf) for leaf in leaf_partition]

    for edge in edges:
        src, tgt = edge.get("source"), edge.get("target")
        if not src or not tgt:
            continue
        mid_src, mid_tgt = None, None
        for mi, leaf_indices in enumerate(mid_partition):
            for li in leaf_indices:
                if src in leaf_sets[li]:
                    mid_src = mi
                    break
            if mid_src is not None:
                break
        for mi, leaf_indices in enumerate(mid_partition):
            for li in leaf_indices:
                if tgt in leaf_sets[li]:
                    mid_tgt = mi
                    break
            if mid_tgt is not None:
                break
        if mid_src is not None and mid_tgt is not None and mid_src != mid_tgt:
            G.add_edge(mid_src, mid_tgt)
    return G


def build_user_brain(
    user_id: str,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    document_count: int,
    hierarchical: bool = True,
) -> Tuple[UserBrain, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Detect communities and assemble the UserBrain model.

    When hierarchical=True (default), runs three-level detection (Leaf → Mid → Root)
    and returns both flat leaf assignments for Neo4j and full hierarchy for summarization/embedding.

    Returns:
        (UserBrain, flat_communities_for_neo4j, hierarchical_communities).
        flat_communities_for_neo4j: list of {community_id, node_ids, ...} for leaf only.
        hierarchical_communities: list of all communities with level, parent_community_id, etc.
    """
    if hierarchical:
        hierarchical_raw = detect_hierarchical_communities(nodes, edges)
        flat_for_neo4j = [
            {
                "community_id": c["community_id"],
                "node_ids": c["node_ids"],
                "node_count": len(c["node_ids"]),
                "top_entities": c["top_entities"],
                "keywords": c["keywords"],
                "document_sources": c["document_sources"],
            }
            for c in hierarchical_raw
            if c["level"] == CommunityLevel.leaf.value
        ]
        community_infos = [
            CommunityInfo(
                community_id=c["community_id"],
                node_count=len(c["node_ids"]),
                top_entities=c["top_entities"],
                keywords=c["keywords"],
                document_sources=c["document_sources"],
            )
            for c in hierarchical_raw
            if c["level"] == CommunityLevel.leaf.value
        ]
    else:
        communities_raw = detect_communities(nodes, edges)
        flat_for_neo4j = communities_raw
        community_infos = [
            CommunityInfo(
                community_id=c["community_id"],
                node_count=c["node_count"],
                top_entities=c["top_entities"],
                keywords=c["keywords"],
                document_sources=c["document_sources"],
            )
            for c in communities_raw
        ]
        hierarchical_raw = []

    brain = UserBrain(
        user_id=user_id,
        document_count=document_count,
        total_nodes=len(nodes),
        total_edges=len(edges),
        community_count=len(community_infos),
        communities=community_infos,
        communities_by_level=None,  # Filled by pipeline after summarization/embedding
        last_updated=datetime.now(timezone.utc).isoformat(),
        status="ready",
    )

    logger.success(
        "Community detection complete",
        user_id=user_id,
        nodes=len(nodes),
        edges=len(edges),
        communities=len(community_infos),
        hierarchical=hierarchical,
    )
    return brain, flat_for_neo4j, hierarchical_raw
