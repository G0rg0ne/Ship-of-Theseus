"""
Neo4j service for persisting and querying document knowledge graphs.
Each document's graph is isolated by document_name on nodes and relationships.
Nodes also carry a user_id property for cross-document, per-user queries used
by the community detection layer.
"""
import json
from typing import Any, Dict, List, Optional, Tuple

from neo4j import GraphDatabase, Driver

from app.core.config import settings
from app.core.logger import logger
from app.schemas.relationships import DocumentGraph, GraphEdge, GraphNode


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

    def _get_driver(self) -> Driver:
        """Lazy-init and return the Neo4j driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
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
        """Create indexes per label for document_name and (document_name, id) if they do not exist."""
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

    def get_document_graph(self, document_name: str) -> Optional[DocumentGraph]:
        """
        Load a document graph from Neo4j by document_name.
        Returns None if no nodes exist for that document.
        """
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
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

    def list_documents(self) -> List[Dict[str, Any]]:
        """Return list of document metadata (document_name, node_count, edge_count)."""
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
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

    def delete_document_graph(self, document_name: str) -> bool:
        """Delete all nodes and relationships for the given document. Returns True on success."""
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
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
                MATCH (n) WHERE n.user_id = $user_id AND n.document_name IS NOT NULL
                RETURN count(DISTINCT n.document_name) AS cnt
                """,
                user_id=user_id,
            )
            record = result.single()
            return int(record["cnt"]) if record else 0

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
            for community in communities:
                cid = community["community_id"]
                for node_id in community.get("node_ids", []):
                    session.run(
                        """
                        MATCH (n {user_id: $user_id, id: $node_id})
                        SET n.community_id = $community_id
                        """,
                        user_id=user_id,
                        node_id=node_id,
                        community_id=cid,
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

    VECTOR_DIMENSIONS = 1536  # text-embedding-3-small

    def ensure_vector_indexes(self, session: Any) -> None:
        """Create vector indexes for Entity.embedding and Community.embedding if they do not exist."""
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
                dim=self.VECTOR_DIMENSIONS,
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
                dim=self.VECTOR_DIMENSIONS,
            )
        except Exception as e:
            logger.warning(
                "Community vector index creation skipped or failed", error=str(e)
            )

    def save_community_nodes(
        self,
        user_id: str,
        communities: List[Dict[str, Any]],
    ) -> None:
        """
        MERGE :Community nodes for the user. Each community has community_id, level,
        parent_community_id, user_id, summary, and optionally embedding (list of floats).
        """
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            self.ensure_vector_indexes(session)
            for c in communities:
                cid = c.get("community_id") or ""
                level = c.get("level") or "leaf"
                parent = c.get("parent_community_id")
                summary = c.get("summary") or ""
                embedding = c.get("embedding")
                node_count = c.get("node_count", len(c.get("node_ids", [])))
                top_entities = c.get("top_entities", [])
                keywords = c.get("keywords", [])
                doc_sources = c.get("document_sources", [])
                props: Dict[str, Any] = {
                    "user_id": user_id,
                    "community_id": cid,
                    "level": level,
                    "parent_community_id": parent or "",
                    "summary": summary,
                    "node_count": node_count,
                    "top_entities_json": json.dumps(top_entities, default=str),
                    "keywords_json": json.dumps(keywords, default=str),
                    "document_sources_json": json.dumps(doc_sources, default=str),
                }
                if embedding is not None:
                    props["embedding"] = embedding
                session.run(
                    """
                    MERGE (c:Community {user_id: $user_id, community_id: $community_id})
                    SET c += $props
                    """,
                    user_id=user_id,
                    community_id=cid,
                    props=props,
                )
        logger.success(
            "Community nodes saved to Neo4j",
            user_id=user_id,
            communities=len(communities),
        )

    def save_entity_embeddings(
        self,
        user_id: str,
        embeddings_map: Dict[str, List[float]],
    ) -> None:
        """
        Set embedding property on entity nodes. Adds :Entity label if missing.
        embeddings_map: node_id -> list of floats (vector).
        """
        if not embeddings_map:
            return
        driver = self._get_driver()
        with driver.session(database=self._database) as session:
            self.ensure_vector_indexes(session)
            for node_id, embedding in embeddings_map.items():
                session.run(
                    """
                    MATCH (n) WHERE n.user_id = $user_id AND n.id = $node_id
                    SET n:Entity, n.embedding = $embedding
                    """,
                    user_id=user_id,
                    node_id=node_id,
                    embedding=embedding,
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
                "MATCH (c:Community {user_id: $user_id}) DETACH DELETE c",
                user_id=user_id,
            )
            session.run(
                "MATCH (b:Brain {user_id: $user_id}) DETACH DELETE b",
                user_id=user_id,
            )
        logger.info("User data deleted from Neo4j", user_id=user_id)
