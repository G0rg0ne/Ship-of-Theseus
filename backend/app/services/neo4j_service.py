"""
Neo4j service for persisting and querying document knowledge graphs.
Each document's graph is isolated by document_name on nodes and relationships.
"""
import json
from typing import Any, Dict, List, Optional

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

    def save_document_graph(self, document_graph: DocumentGraph) -> bool:
        """
        Persist a document graph to Neo4j.
        Replaces any existing graph for the same document_name.
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
                    "document_name": doc_name,
                    "extracted_at": document_graph.extracted_at,
                }
                for k, v in (node.properties or {}).items():
                    if v is not None:
                        props[k] = _serialize_value(v)
                session.run(f"CREATE (n:{label} $props)", props=props)

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
                    if node_id and node_id not in nodes_by_id:
                        entity_type = "entity"
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
