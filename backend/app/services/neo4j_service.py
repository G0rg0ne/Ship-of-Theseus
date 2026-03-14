"""
Neo4j service for persisting and querying document knowledge graphs.
Each document's graph is isolated by document_name on nodes and relationships.
Nodes also carry a user_id property for cross-document, per-user queries used
by the community detection layer.
"""
import json
from typing import Any, Dict, List, Optional, Tuple

import neo4j
from neo4j import GraphDatabase, Driver

from app.core.config import settings
from app.core.logger import logger
from app.schemas.relationships import DocumentGraph, GraphEdge, GraphNode
from app.services.embedding_service import EmbeddingService


def _type_to_label(entity_type: str) -> str:
    """Map schema entity type to Neo4j label (PascalCase)."""
    t = entity_type.strip().lower().replace(" ", "_").title().replace("_", "")
    return t or "Entity"


def _serialize_value(v: Any) -> Any:
    """Convert values for Neo4j storage (primitives or JSON string for complex types)."""
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    return str(v)


# Max candidates to request from vector index when over-fetching for user filtering.
# Post-filtering by user_id can return fewer than top_k; over-fetching mitigates sparse results.
_VECTOR_SEARCH_FETCH_MAX = 500


class Neo4jService:
    """Service for persisting DocumentGraph to Neo4j and querying by document_name."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ):
        self._uri = uri or settings.NEO4J_URI
        self._user = user or settings.NEO4J_USER
        self._password = password or settings.NEO4J_PASSWORD
        self._database = database or settings.NEO4J_DATABASE
        self._driver: Optional[Driver] = None
        self._vector_dim_cache: Optional[int] = None

    def _get_driver(self) -> Driver:
        """Lazy-init and return the Neo4j driver."""
        if self._driver is None:
            kwargs: Dict[str, Any] = {}
            if hasattr(neo4j, "NotificationClassification"):
                kwargs["notifications_disabled_classifications"] = [
                    neo4j.NotificationClassification.UNRECOGNIZED,
                ]
            self._driver = GraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
                **kwargs,
            )
            logger.info(
                "Neo4j driver initialized",
                uri=self._uri.split("@")[-1] if "@" in self._uri else self._uri,
            )
        return self._driver

    def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j driver closed")

    def health_check(self) -> bool:
        """Verify connectivity to Neo4j. Returns True if healthy."""
        try:
            driver = self._get_driver()
            driver.verify_connectivity()
            return True
        except Exception as e:
            logger.warning("Neo4j health check failed", error=str(e))
            return False

    def _ensure_indexes(self, session: Any) -> None:
        """Create indexes per label for document_name and (document_name, id) if they do not exist.
        Also creates a composite index on :Entity (user_id, document_name, id) for neighborhood lookups."""
        session.run(
            "CREATE INDEX entity_scope_idx IF NOT EXISTS FOR (n:Entity) ON (n.user_id, n.document_name, n.id)"
        )
        for label in ("Person", "Organization", "Location", "KeyTerm"):
            session.run(
                f"CREATE INDEX document_name_{label}_idx IF NOT EXISTS FOR (n:{label}) ON (n.document_name)"
            )
            session.run(
                f"CREATE INDEX node_id_doc_{label}_idx IF NOT EXISTS FOR (n:{label}) ON (n.document_name, n.id)"
            )

    def save_document_graph(
        self,
        document_graph: DocumentGraph,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Persist a document graph to Neo4j.
        Replaces any existing graph for the same document_name.
        Optionally tags each node with user_id for per-user graph queries.
        Returns True on success.
        """
        doc_name = document_graph.filename
        driver = self._get_driver()

        with driver.session(database=self._database) as session:
            self._ensure_indexes(session)
            session.run(
                "MATCH (n {document_name: $doc_name}) DETACH DELETE n",
                doc_name=doc_name,
            )
            if not document_graph.nodes:
                logger.info("No nodes to save", document_name=doc_name)
                return True

            for node in document_graph.nodes:
                label = _type_to_label(node.type)
                props: Dict[str, Any] = {
                    "id": node.id,
                    "label": node.label,
                    "entity_type": node.type,  # stored explicitly so round-trip is lossless
                    "document_name": doc_name,
                    "extracted_at": document_graph.extracted_at,
                    "user_id": user_id or "",
                }
                for k, v in (node.properties or {}).items():
                    if v is not None:
                        props[k] = _serialize_value(v)
                # :Entity label enables vector index for embedding-based search
                session.run(f"CREATE (n:{label}:Entity $props)", props=props)

            for edge in document_graph.edges:
                rel_props: Dict[str, Any] = {
                    "type": edge.relation_type,
                    "document_name": doc_name,
                }
                for k, v in (edge.properties or {}).items():
                    if v is not None:
                        rel_props[k] = _serialize_value(v)
                session.run(
                    """
                    MATCH (a {id: $source_id, document_name: $doc_name})
                    MATCH (b {id: $target_id, document_name: $doc_name})
                    CREATE (a)-[r:RELATES $props]->(b)
                    """,
                    source_id=edge.source,
                    target_id=edge.target,
                    doc_name=doc_name,
                    props=rel_props,
                )

        logger.success(
            "Document graph saved to Neo4j",
            document_name=doc_name,
            nodes=len(document_graph.nodes),
            edges=len(document_graph.edges),
        )
        return True

    def get_document_graph(
        self, document_name: str, *, user_id: Optional[str] = None
    ) -> Optional[DocumentGraph]:
        """
        Load a document graph from Neo4j by document_name.
        Returns None if no nodes exist for that document.
        """
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            if user_id:
                result = session.run(
                    """
                    MATCH (n {document_name: $doc_name, user_id: $user_id})
                    OPTIONAL MATCH (n)-[r:RELATES {document_name: $doc_name}]->(m {document_name: $doc_name, user_id: $user_id})
                    RETURN n, r, m
                    """,
                    doc_name=document_name,
                    user_id=user_id,
                )
            else:
                result = session.run(
                    """
                    MATCH (n {document_name: $doc_name})
                    OPTIONAL MATCH (n)-[r:RELATES]->(m)
                    RETURN n, r, m
                    """,
                    doc_name=document_name,
                )
            nodes_by_id: Dict[str, GraphNode] = {}
            edges_seen: set = set()
            edges_list: List[GraphEdge] = []
            extracted_at = ""

            for record in result:
                node_n = record.get("n")
                rel = record.get("r")
                node_m = record.get("m")
                if node_n:
                    n_props = dict(node_n)
                    node_id = n_props.pop("id", None)
                    label = n_props.pop("label", "")
                    n_props.pop("document_name", None)
                    extracted_at = n_props.pop("extracted_at", "") or extracted_at
                    # Prefer stored entity_type property; fall back to Neo4j label
                    stored_type = n_props.pop("entity_type", None)
                    if node_id and node_id not in nodes_by_id:
                        if stored_type:
                            entity_type = stored_type
                        else:
                            entity_type = "other"
                            for lab in node_n.labels:
                                entity_type = lab.lower()
                                break
                        nodes_by_id[node_id] = GraphNode(
                            id=node_id,
                            label=label,
                            type=entity_type,
                            properties=n_props,
                        )
                if rel and node_n and node_m:
                    a_id = dict(node_n).get("id")
                    b_id = dict(node_m).get("id")
                    if a_id and b_id:
                        rel_type = dict(rel).get("type", "")
                        edge_key = (a_id, b_id, rel_type)
                        if edge_key not in edges_seen:
                            edges_seen.add(edge_key)
                            rel_props = {k: v for k, v in dict(rel).items() if k not in ("type", "document_name")}
                            edges_list.append(
                                GraphEdge(
                                    source=a_id,
                                    target=b_id,
                                    relation_type=rel_type,
                                    properties=rel_props,
                                )
                            )

            if not nodes_by_id:
                return None
            return DocumentGraph(
                filename=document_name,
                nodes=list(nodes_by_id.values()),
                edges=edges_list,
                extracted_at=extracted_at,
                entity_count=len(nodes_by_id),
                relationship_count=len(edges_list),
            )

    def list_documents(self, *, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return list of document metadata (document_name, node_count, edge_count).

        When user_id is provided, results are scoped to that user's documents.
        """
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            if user_id:
                result = session.run(
                    """
                    MATCH (n)
                    WHERE n.user_id = $user_id AND n.document_name IS NOT NULL
                    WITH DISTINCT n.document_name AS doc_name
                    OPTIONAL MATCH (a {document_name: doc_name, user_id: $user_id})
                    WITH doc_name, count(a) AS node_count
                    OPTIONAL MATCH (x {document_name: doc_name, user_id: $user_id})-[r:RELATES {document_name: doc_name}]->()
                    WITH doc_name, node_count, count(r) AS edge_count
                    RETURN doc_name, node_count, edge_count
                    """,
                    user_id=user_id,
                )
            else:
                result = session.run(
                    """
                    MATCH (n)
                    WHERE n.document_name IS NOT NULL
                    WITH DISTINCT n.document_name AS doc_name
                    OPTIONAL MATCH (a {document_name: doc_name})
                    WITH doc_name, count(a) AS node_count
                    OPTIONAL MATCH (x {document_name: doc_name})-[r:RELATES]->()
                    WITH doc_name, node_count, count(r) AS edge_count
                    RETURN doc_name, node_count, edge_count
                    """
                )
            out: List[Dict[str, Any]] = []
            for record in result:
                out.append({
                    "document_name": record["doc_name"],
                    "node_count": record["node_count"],
                    "edge_count": record["edge_count"],
                })
            return out

    def get_global_counts(
        self,
    ) -> Tuple[int, int, int, int]:
        """
        Return (entity_count, edge_count, community_count, document_count) for admin stats.
        """
        driver = self._get_driver()
        entity_count = edge_count = community_count = document_count = 0
        with driver.session(database=self._database) as session:
            r = session.run("MATCH (n:Entity) RETURN count(n) AS c")
            rec = r.single()
            if rec:
                entity_count = int(rec["c"]) if rec["c"] is not None else 0
            r = session.run("MATCH ()-[r:RELATES]->() RETURN count(r) AS c")
            rec = r.single()
            if rec:
                edge_count = int(rec["c"]) if rec["c"] is not None else 0
            r = session.run("MATCH (c:Community) RETURN count(c) AS c")
            rec = r.single()
            if rec:
                community_count = int(rec["c"]) if rec["c"] is not None else 0
            # Count distinct (user_id, document_name) pairs so that documents
            # with the same name belonging to different users are not collapsed.
            r = session.run(
                """
                MATCH (n)
                WHERE n.user_id IS NOT NULL AND n.document_name IS NOT NULL
                RETURN count(DISTINCT [n.user_id, n.document_name]) AS c
                """
            )
            rec = r.single()
            if rec:
                document_count = int(rec["c"]) if rec["c"] is not None else 0
        return entity_count, edge_count, community_count, document_count

    def get_store_size_bytes(self) -> Optional[int]:
        """
        Best-effort estimate of Neo4j store size in bytes.

        Uses `dbms.queryJmx` when available. Returns None if the procedure is
        unavailable or if the returned attributes cannot be interpreted.
        """
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            candidates = [
                "org.neo4j:instance=kernel#0,name=Store file sizes",
                "org.neo4j:instance=kernel#0,name=StoreFileSizes",
                "org.neo4j:instance=kernel#0,name=Store sizes",
            ]
            last_error: Optional[Exception] = None
            for mbean in candidates:
                try:
                    result = session.run(
                        "CALL dbms.queryJmx($mbean) YIELD attributes RETURN attributes LIMIT 1",
                        mbean=mbean,
                    )
                    rec = result.single()
                    if not rec:
                        continue
                    attrs = rec.get("attributes")
                    if not isinstance(attrs, dict):
                        continue
                    total = 0
                    found_any = False
                    for v in attrs.values():
                        if isinstance(v, (int, float)):
                            total += int(v)
                            found_any = True
                        elif isinstance(v, str):
                            # Some installations return numbers as strings.
                            try:
                                total += int(float(v))
                                found_any = True
                            except Exception:
                                continue
                    if found_any:
                        return total
                except Exception as exc:
                    last_error = exc
                    continue
            if last_error:
                logger.debug("Neo4j store size JMX query failed: {}", last_error)
        return None

    def delete_document_graph(
        self, document_name: str, *, user_id: Optional[str] = None
    ) -> bool:
        """Delete all nodes and relationships for the given document.

        When user_id is provided, deletion is scoped to that user's document.
        """
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            if user_id:
                session.run(
                    "MATCH (n {document_name: $doc_name, user_id: $user_id}) DETACH DELETE n",
                    doc_name=document_name,
                    user_id=user_id,
                )
                logger.info(
                    "User-scoped document graph deleted from Neo4j",
                    document_name=document_name,
                    user_id=user_id,
                )
            else:
                session.run(
                    "MATCH (n {document_name: $doc_name}) DETACH DELETE n",
                    doc_name=document_name,
                )
                logger.info("Document graph deleted from Neo4j", document_name=document_name)
        return True

    # ------------------------------------------------------------------
    # Per-user graph access (used by community detection)
    # ------------------------------------------------------------------

    def get_user_graph(self, user_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Return (nodes, edges) for all documents belonging to user_id.

        Each node dict contains all Neo4j properties.
        Each edge dict has: source (node id), target (node id), relation_type,
        document_name.
        """
        driver = self._get_driver()
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []

        with driver.session(database=self._database) as session:
            node_result = session.run(
                "MATCH (n) WHERE n.user_id = $user_id RETURN n",
                user_id=user_id,
            )
            for record in node_result:
                nodes.append(dict(record["n"]))

            edge_result = session.run(
                """
                MATCH (a)-[r:RELATES]->(b)
                WHERE a.user_id = $user_id AND b.user_id = $user_id
                RETURN a.id AS source, b.id AS target,
                       r.type AS relation_type, r.document_name AS document_name
                """,
                user_id=user_id,
            )
            for record in edge_result:
                edges.append(
                    {
                        "source": record["source"],
                        "target": record["target"],
                        "relation_type": record["relation_type"] or "",
                        "document_name": record["document_name"] or "",
                    }
                )

        logger.info(
            "Loaded user graph from Neo4j",
            user_id=user_id,
            nodes=len(nodes),
            edges=len(edges),
        )
        return nodes, edges

    def get_user_document_count(self, user_id: str) -> int:
        """Return the number of distinct documents belonging to user_id."""
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            result = session.run(
                """
                MATCH (n)
                WHERE n.user_id = $user_id AND n.document_name IS NOT NULL
                RETURN count(DISTINCT n.document_name) AS cnt
                """,
                user_id=user_id,
            )
            record = result.single()
            return int(record["cnt"]) if record else 0

    def get_document_counts_for_user_ids(
        self,
        user_ids: List[str],
    ) -> Dict[str, int]:
        """
        Return a mapping of user_id -> distinct document count for the given users.

        This is the bulk equivalent of get_user_document_count and is intended for
        admin views to avoid N+1 Neo4j queries when listing many users.
        """
        if not user_ids:
            return {}

        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            result = session.run(
                """
                MATCH (n)
                WHERE n.user_id IN $user_ids AND n.document_name IS NOT NULL
                RETURN n.user_id AS user_id, count(DISTINCT n.document_name) AS cnt
                """,
                user_ids=user_ids,
            )

            counts: Dict[str, int] = {}
            for record in result:
                uid = record.get("user_id")
                if uid is None:
                    continue
                cnt = record.get("cnt")
                try:
                    counts[str(uid)] = int(cnt) if cnt is not None else 0
                except (TypeError, ValueError):
                    continue

        logger.info(
            "Loaded per-user document counts from Neo4j",
            user_count=len(user_ids),
            result_count=len(counts),
        )
        return counts

    def save_community_assignments(
        self,
        user_id: str,
        communities: List[Dict[str, Any]],
    ) -> None:
        """
        Write community_id back to each node in Neo4j.

        communities is a list of dicts with {community_id, node_ids, ...}.
        Only nodes belonging to user_id are updated (safety guard).
        """
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            rows: List[Dict[str, Any]] = []
            for community in communities:
                cid = community.get("community_id")
                if not cid:
                    continue
                for node_id in community.get("node_ids", []) or []:
                    if not node_id:
                        continue
                    rows.append({"node_id": node_id, "community_id": cid})

            if rows:
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (n {user_id: $user_id, id: row.node_id})
                    SET n.community_id = row.community_id
                    """,
                    user_id=user_id,
                    rows=rows,
                )
        logger.success(
            "Community assignments saved to Neo4j",
            user_id=user_id,
            communities=len(communities),
        )

    # ------------------------------------------------------------------
    # Brain node – permanent per-user knowledge brain
    # ------------------------------------------------------------------

    def _ensure_brain_index(self, session: Any) -> None:
        """Create a uniqueness constraint / index on Brain.user_id if it doesn't exist."""
        session.run(
            "CREATE INDEX brain_user_id_idx IF NOT EXISTS FOR (b:Brain) ON (b.user_id)"
        )

    # ------------------------------------------------------------------
    # Vector indexes and embedding storage (GraphRAG)
    # ------------------------------------------------------------------
    def _get_vector_dimensions(self) -> int:
        """
        Determine the embedding vector dimension for the active EMBEDDING_MODEL.

        Prefers a static model→dimension map and falls back to probing the
        EmbeddingService when the model is unknown.
        """
        if self._vector_dim_cache is not None:
            return self._vector_dim_cache

        model_name = getattr(settings, "EMBEDDING_MODEL", "text-embedding-3-small")

        # Known OpenAI embedding dimensions; extend this map as needed.
        model_dims: Dict[str, int] = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }

        dim = model_dims.get(model_name)

        if dim is None:
            try:
                embedding_service = EmbeddingService()
                dim = embedding_service.get_embedding_dimension()
                logger.info(
                    "Derived embedding dimension from EmbeddingService",
                    model=model_name,
                    dimensions=dim,
                )
            except Exception as e:
                logger.error(
                    "Failed to determine embedding dimension from EmbeddingService; falling back to default",
                    model=model_name,
                    error=str(e),
                )
                # Last-resort default to preserve previous behavior.
                dim = 1536

        self._vector_dim_cache = dim
        return dim

    def ensure_vector_indexes(self, session: Any) -> None:
        """Create vector indexes for Entity.embedding and Community.embedding if they do not exist."""
        dim = self._get_vector_dimensions()
        try:
            session.run(
                """
                CREATE VECTOR INDEX entity_embedding_idx IF NOT EXISTS
                FOR (n:Entity) ON (n.embedding)
                OPTIONS {indexConfig: {
                    `vector.dimensions`: $dim,
                    `vector.similarity_function`: 'cosine'
                }}
                """,
                dim=dim,
            )
        except Exception as e:
            logger.warning("Entity vector index creation skipped or failed", error=str(e))
        try:
            session.run(
                """
                CREATE VECTOR INDEX community_summary_embedding_idx IF NOT EXISTS
                FOR (c:Community) ON (c.embedding)
                OPTIONS {indexConfig: {
                    `vector.dimensions`: $dim,
                    `vector.similarity_function`: 'cosine'
                }}
                """,
                dim=dim,
            )
        except Exception as e:
            logger.warning(
                "Community vector index creation skipped or failed", error=str(e)
            )

    def get_community_embeddings_and_fingerprints(
        self,
        user_id: str,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Return a mapping of community_id -> {embedding, summary_fingerprint} for a user.

        Used by the brain pipeline to avoid re-embedding unchanged community summaries.
        """
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            result = session.run(
                """
                MATCH (c:Community {derived_user_id: $user_id})
                RETURN c.community_id AS community_id,
                       c.embedding AS embedding,
                       c.summary_fingerprint AS summary_fingerprint
                """,
                user_id=user_id,
            )
            out: Dict[str, Dict[str, Any]] = {}
            for record in result:
                cid = record.get("community_id")
                if not cid:
                    continue
                out[cid] = {
                    "embedding": record.get("embedding"),
                    "summary_fingerprint": record.get("summary_fingerprint"),
                }
            return out

    def vector_search_entities(
        self,
        user_id: str,
        query_vector: List[float],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search on :Entity nodes. Returns up to top_k entities for the user.

        Over-fetches from the index (capped by _VECTOR_SEARCH_FETCH_MAX) then filters by
        user_id and limits to top_k, so multi-tenant DBs still return up to top_k results.
        Uses entity_embedding_idx. Each result: user_id, document_name, id, label, entity_type, score
        (composite key avoids collisions across documents).
        """
        if not query_vector or top_k <= 0:
            return []
        fetch_k = min(_VECTOR_SEARCH_FETCH_MAX, top_k * 2)
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            result = session.run(
                """
                CALL db.index.vector.queryNodes('entity_embedding_idx', $fetch_k, $query_vector)
                YIELD node, score
                WHERE node.user_id = $user_id
                RETURN node.user_id AS user_id, node.document_name AS document_name, node.id AS id,
                       node.label AS label, node.entity_type AS entity_type, score
                LIMIT $top_k
                """,
                query_vector=query_vector,
                fetch_k=fetch_k,
                top_k=top_k,
                user_id=user_id,
            )
            return [
                {
                    "user_id": record["user_id"] or "",
                    "document_name": record["document_name"] or "",
                    "id": record["id"],
                    "label": record["label"] or "",
                    "entity_type": record["entity_type"] or "",
                    "score": float(record["score"]) if record.get("score") is not None else 0.0,
                }
                for record in result
            ]

    def vector_search_communities(
        self,
        user_id: str,
        query_vector: List[float],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search on :Community nodes (root and mid level only).

        Over-fetches from the index (candidate_k = top_k * overfetch factor, capped) then
        filters by derived_user_id and level; trims to top_k so multi-tenant DBs return
        up to top_k results. Uses community_summary_embedding_idx.
        Each result: community_id, summary, level, keywords_json, score.
        """
        if not query_vector or top_k <= 0:
            return []
        # Over-fetch so that after filtering by derived_user_id and level we still have up to top_k
        candidate_k = min(_VECTOR_SEARCH_FETCH_MAX, top_k * 5)
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            result = session.run(
                """
                CALL db.index.vector.queryNodes('community_summary_embedding_idx', $candidate_k, $query_vector)
                YIELD node, score
                WHERE node.derived_user_id = $user_id AND node.level IN ['root', 'mid']
                RETURN node.community_id AS community_id, node.summary AS summary,
                       node.level AS level, node.keywords_json AS keywords_json, score
                LIMIT $top_k
                """,
                query_vector=query_vector,
                candidate_k=candidate_k,
                top_k=top_k,
                user_id=user_id,
            )
            return [
                {
                    "community_id": record["community_id"] or "",
                    "summary": record["summary"] or "",
                    "level": record["level"] or "",
                    "keywords_json": record["keywords_json"] or "[]",
                    "score": float(record["score"]) if record.get("score") is not None else 0.0,
                }
                for record in result
            ]

    def get_entity_neighborhood(
        self,
        entity_keys: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """
        For the given entity composite keys (user_id, document_name, id), return 1-hop RELATES
        triplets: (source_label, relation_type, target_label, target_entity_type).
        Scoped by full tuple to avoid collisions across documents.
        """
        if not entity_keys:
            return []
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            result = session.run(
                """
                UNWIND $entity_keys AS ek
                MATCH (e:Entity)-[r:RELATES]->(t:Entity)
                WHERE e.user_id = ek.user_id AND e.document_name = ek.document_name AND e.id = ek.id
                  AND t.user_id = e.user_id AND t.document_name = e.document_name
                RETURN e.label AS source_label, r.type AS relation_type, t.label AS target_label, t.entity_type AS target_entity_type
                """,
                entity_keys=entity_keys,
            )
            return [
                {
                    "source_label": record["source_label"] or "",
                    "relation_type": record["relation_type"] or "",
                    "target_label": record["target_label"] or "",
                    "target_entity_type": record["target_entity_type"] or "",
                }
                for record in result
            ]

    def save_community_nodes(
        self,
        user_id: str,
        communities: List[Dict[str, Any]],
    ) -> None:
        """
        MERGE :Community nodes derived from a user's graph.

        Each community has community_id, level, parent_community_id, derived_user_id,
        summary, and optionally embedding (list of floats).
        """
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            self.ensure_vector_indexes(session)
            rows: List[Dict[str, Any]] = []
            for c in communities:
                cid = c.get("community_id") or ""
                if not cid:
                    continue
                level = c.get("level") or "leaf"
                parent = c.get("parent_community_id")
                summary = c.get("summary") or ""
                summary_fingerprint = c.get("summary_fingerprint")
                embedding = c.get("embedding")
                node_count = c.get("node_count", len(c.get("node_ids", [])))
                top_entities = c.get("top_entities", [])
                keywords = c.get("keywords", [])
                doc_sources = c.get("document_sources", [])
                props: Dict[str, Any] = {
                    "derived_user_id": user_id,
                    "community_id": cid,
                    "level": level,
                    "parent_community_id": parent or "",
                    "summary": summary,
                    "node_count": node_count,
                    "top_entities_json": json.dumps(top_entities, default=str),
                    "keywords_json": json.dumps(keywords, default=str),
                    "document_sources_json": json.dumps(doc_sources, default=str),
                }
                if summary_fingerprint is not None:
                    props["summary_fingerprint"] = summary_fingerprint
                if embedding is not None:
                    props["embedding"] = embedding
                rows.append({"community_id": cid, "derived_user_id": user_id, "props": props})

            if rows:
                session.run(
                    """
                    UNWIND $rows AS row
                    MERGE (c:Community {community_id: row.community_id, derived_user_id: row.derived_user_id})
                    SET c += row.props
                    """,
                    rows=rows,
                )
        logger.success(
            "Community nodes saved to Neo4j",
            user_id=user_id,
            communities=len(communities),
        )

    def save_entity_embeddings(
        self,
        user_id: str,
        document_name: str,
        embeddings_map: Dict[str, List[float]],
        fingerprint_map: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Set embedding property on entity nodes for a single document.

        Adds :Entity label if missing.
        embeddings_map: node_id -> list of floats (vector) scoped to document_name.
        """
        if not embeddings_map:
            return
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            self.ensure_vector_indexes(session)
            rows: List[Dict[str, Any]] = []
            for node_id, embedding in embeddings_map.items():
                if not node_id:
                    continue
                row: Dict[str, Any] = {"node_id": node_id, "embedding": embedding}
                if fingerprint_map is not None:
                    row["fingerprint"] = fingerprint_map.get(node_id)
                rows.append(row)

            if fingerprint_map is not None:
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (n)
                    WHERE n.user_id = $user_id
                      AND n.document_name = $document_name
                      AND n.id = row.node_id
                    SET n:Entity,
                        n.embedding = row.embedding,
                        n.embedding_fingerprint = row.fingerprint
                    """,
                    user_id=user_id,
                    document_name=document_name,
                    rows=rows,
                )
            else:
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (n)
                    WHERE n.user_id = $user_id
                      AND n.document_name = $document_name
                      AND n.id = row.node_id
                    SET n:Entity,
                        n.embedding = row.embedding
                    """,
                    user_id=user_id,
                    document_name=document_name,
                    rows=rows,
                )
        logger.success(
            "Entity embeddings saved to Neo4j",
            user_id=user_id,
            count=len(embeddings_map),
        )

    def save_brain_node(self, user_id: str, brain_dict: Dict[str, Any]) -> None:
        """
        MERGE a :Brain node for the user in Neo4j, storing the full brain summary.

        The communities list and communities_by_level are serialized to JSON so they
        survive Neo4j's property type constraints. Call this after every community
        detection run so the brain is permanently persisted and survives Redis TTL
        expiry or cache flushes.
        """
        driver = self._get_driver()
        communities_raw = brain_dict.get("communities", [])
        communities_by_level = brain_dict.get("communities_by_level")
        props: Dict[str, Any] = {
            "user_id": user_id,
            "document_count": brain_dict.get("document_count", 0),
            "total_nodes": brain_dict.get("total_nodes", 0),
            "total_edges": brain_dict.get("total_edges", 0),
            "community_count": brain_dict.get("community_count", 0),
            "last_updated": brain_dict.get("last_updated", ""),
            "status": brain_dict.get("status", "ready"),
            "communities_json": json.dumps(communities_raw, default=str),
        }
        if communities_by_level is not None:
            props["communities_by_level_json"] = json.dumps(
                [c if isinstance(c, dict) else getattr(c, "model_dump", lambda: c)() for c in communities_by_level],
                default=str,
            )
        with driver.session(database=self._database) as session:
            self._ensure_brain_index(session)
            session.run(
                """
                MERGE (b:Brain {user_id: $user_id})
                SET b += $props
                """,
                user_id=user_id,
                props=props,
            )
        logger.success("Brain node saved to Neo4j", user_id=user_id, communities=len(communities_raw))

    def get_brain_node(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a user's :Brain node from Neo4j.

        Returns a dict matching the UserBrain schema (with 'communities' already
        deserialized from JSON), or None if no Brain node exists yet.
        """
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            result = session.run(
                "MATCH (b:Brain {user_id: $user_id}) RETURN b",
                user_id=user_id,
            )
            record = result.single()
            if record is None:
                return None
            props = dict(record["b"])
            communities_json = props.pop("communities_json", "[]")
            communities_by_level_json = props.pop("communities_by_level_json", None)
            try:
                communities = json.loads(communities_json)
            except Exception:
                communities = []
            try:
                communities_by_level = (
                    json.loads(communities_by_level_json)
                    if communities_by_level_json
                    else None
                )
            except Exception:
                communities_by_level = None
            return {
                "user_id": props.get("user_id", user_id),
                "document_count": props.get("document_count", 0),
                "total_nodes": props.get("total_nodes", 0),
                "total_edges": props.get("total_edges", 0),
                "community_count": props.get("community_count", 0),
                "last_updated": props.get("last_updated", ""),
                "status": props.get("status", "ready"),
                "communities": communities,
                "communities_by_level": communities_by_level,
            }

    def delete_user_data(self, user_id: str) -> None:
        """
        Permanently delete all Neo4j data for the user: entity nodes, relationships,
        Community nodes, and the Brain node. Used for "Clear Brain" / start from scratch.
        """
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            session.run(
                "MATCH (n) WHERE n.user_id = $user_id DETACH DELETE n",
                user_id=user_id,
            )
            session.run(
                "MATCH (c:Community {derived_user_id: $user_id}) DETACH DELETE c",
                user_id=user_id,
            )
        logger.info("User data deleted from Neo4j", user_id=user_id)
