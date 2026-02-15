"""
Relationship extraction service using LangChain and LLM.
Constrains relationships to only use previously extracted entities.
Supports parallel chunk processing with progress tracking via Redis.
Outputs graph-ready format (nodes + edges).
"""
import asyncio
import re
from datetime import datetime
from typing import Dict, List, Set, Tuple

from langchain_openai import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate

from app.core.config import settings
from app.core.logger import logger
from app.core.cache import (
    cache_get,
    cache_set,
    cache_key_relationship_job,
    EXTRACTION_JOB_TTL,
)
from app.schemas.entities import DocumentEntities, ExtractedEntities
from app.schemas.relationships import (
    DocumentGraph,
    ExtractedRelationships,
    GraphEdge,
    GraphNode,
    Relationship,
)


def _slug(label: str, index: int) -> str:
    """Create a safe node id from label and index."""
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", label.strip()).strip("_") or "entity"
    return f"n_{index}_{safe}"[:64]


class RelationshipExtractionService:
    """LangChain-based relationship extraction constrained to existing entities."""

    def __init__(self, api_key: str, model: str):
        self.llm = ChatOpenAI(
            model=model,
            temperature=0,
            openai_api_key=api_key,
        )
        self.parser = PydanticOutputParser(pydantic_object=ExtractedRelationships)
        self.prompt = PromptTemplate(
            template="""Extract relationships between entities from the text.

CRITICAL CONSTRAINT: You MUST ONLY create relationships between the entities provided in the list below.
Do NOT introduce new entities. Source and Target must EXACTLY match entity names from the list.

Available Entities:
{entity_list}

Text:
{text}

Extract relationships as triplets: (Source Entity, Relation Type, Target Entity).
Only use entities from the provided list above. Use short relation types (e.g., works_for, located_in, founded_by).

{format_instructions}
""",
            input_variables=["entity_list", "text"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )
        self.chain = self.prompt | self.llm | self.parser

    @staticmethod
    def _build_entity_list(chunk_entities: ExtractedEntities) -> str:
        """Build formatted entity list for the LLM prompt."""
        lines: List[str] = []
        for p in chunk_entities.people:
            lines.append(f"- {p.name} (Person)")
        for o in chunk_entities.organizations:
            lines.append(f"- {o.name} (Organization)")
        for loc in chunk_entities.locations:
            lines.append(f"- {loc} (Location)")
        for term in chunk_entities.key_terms:
            lines.append(f"- {term} (KeyTerm)")
        return "\n".join(lines) if lines else "(No entities in this chunk)"

    @staticmethod
    def _validate_relationships(
        relationships: List[Relationship], valid_entities: Set[str]
    ) -> List[Relationship]:
        """Filter out relationships whose source or target are not in valid_entities."""
        valid: List[Relationship] = []
        for rel in relationships:
            if rel.source in valid_entities and rel.target in valid_entities:
                valid.append(rel)
            else:
                logger.warning(
                    "Invalid relationship filtered",
                    source=rel.source,
                    target=rel.target,
                    relation_type=rel.relation_type,
                )
        return valid

    def extract_relationships(
        self,
        text: str,
        chunk_entities: ExtractedEntities,
        chunk_id: int,
    ) -> ExtractedRelationships:
        """Extract relationships from a single chunk (sync)."""
        entity_list = self._build_entity_list(chunk_entities)
        result = self.chain.invoke({"entity_list": entity_list, "text": text})
        result.chunk_id = chunk_id
        return result

    async def extract_relationships_async(
        self,
        text: str,
        chunk_entities: ExtractedEntities,
        chunk_id: int,
    ) -> ExtractedRelationships:
        """Extract relationships from a single chunk (async for parallel use)."""
        entity_list = self._build_entity_list(chunk_entities)
        result = await self.chain.ainvoke({"entity_list": entity_list, "text": text})
        result.chunk_id = chunk_id
        return result

    @staticmethod
    def _build_graph(
        document_entities: DocumentEntities,
        all_relationships: List[Relationship],
        filename: str,
    ) -> DocumentGraph:
        """
        Build graph-ready output: unique nodes from entities, edges from relationships.
        Validates that edge endpoints exist in nodes and deduplicates edges.
        """
        # Collect unique entities and assign node ids
        label_to_id: Dict[str, str] = {}
        nodes: List[GraphNode] = []
        idx = 0

        for chunk_ent in document_entities.chunk_entities:
            for p in chunk_ent.people:
                name = p.name.strip()
                if name and name not in label_to_id:
                    nid = _slug(name, idx)
                    idx += 1
                    label_to_id[name] = nid
                    nodes.append(
                        GraphNode(
                            id=nid,
                            label=name,
                            type="person",
                            properties={
                                k: v
                                for k, v in (p.model_dump()).items()
                                if v is not None and k != "name"
                            },
                        )
                    )
            for o in chunk_ent.organizations:
                name = o.name.strip()
                if name and name not in label_to_id:
                    nid = _slug(name, idx)
                    idx += 1
                    label_to_id[name] = nid
                    nodes.append(
                        GraphNode(
                            id=nid,
                            label=name,
                            type="organization",
                            properties={
                                k: v
                                for k, v in (o.model_dump()).items()
                                if v is not None and k != "name"
                            },
                        )
                    )
            for loc in chunk_ent.locations:
                name = (loc if isinstance(loc, str) else str(loc)).strip()
                if name and name not in label_to_id:
                    nid = _slug(name, idx)
                    idx += 1
                    label_to_id[name] = nid
                    nodes.append(
                        GraphNode(id=nid, label=name, type="location", properties={})
                    )
            for term in chunk_ent.key_terms:
                name = (term if isinstance(term, str) else str(term)).strip()
                if name and name not in label_to_id:
                    nid = _slug(name, idx)
                    idx += 1
                    label_to_id[name] = nid
                    nodes.append(
                        GraphNode(id=nid, label=name, type="key_term", properties={})
                    )

        valid_entities = set(label_to_id.keys())
        valid_rels = RelationshipExtractionService._validate_relationships(
            all_relationships, valid_entities
        )

        # Deduplicate edges by (source_id, target_id, relation_type)
        seen: Set[Tuple[str, str, str]] = set()
        edges: List[GraphEdge] = []
        for rel in valid_rels:
            sid = label_to_id.get(rel.source)
            tid = label_to_id.get(rel.target)
            if sid is None or tid is None:
                continue
            key = (sid, tid, rel.relation_type)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                GraphEdge(
                    source=sid,
                    target=tid,
                    relation_type=rel.relation_type,
                    properties={
                        k: v
                        for k, v in (rel.model_dump()).items()
                        if v is not None and k not in ("source", "target", "relation_type")
                    },
                )
            )

        return DocumentGraph(
            filename=filename,
            nodes=nodes,
            edges=edges,
            extracted_at=datetime.utcnow().isoformat() + "Z",
            entity_count=len(nodes),
            relationship_count=len(edges),
        )

    async def extract_from_chunks_parallel(
        self,
        chunks: List[str],
        document_entities: DocumentEntities,
        job_id: str,
        entity_job_id: str,
        user_id: str,
        filename: str,
    ) -> None:
        """
        Extract relationships from all chunks in parallel batches.
        Progress is written to Redis. Final result is a DocumentGraph.
        """
        key = cache_key_relationship_job(job_id)
        n = len(chunks)
        batch_size = getattr(
            settings, "RELATIONSHIP_EXTRACTION_BATCH_SIZE", 5
        ) or 5

        job_payload = {
            "status": "running",
            "user_id": user_id,
            "filename": filename,
            "entity_job_id": entity_job_id,
            "total_chunks": n,
            "completed_chunks": 0,
            "result": None,
            "error": None,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        await cache_set(key, job_payload, ttl_seconds=EXTRACTION_JOB_TTL)
        logger.info(
            "Relationship extraction job started",
            job_id=job_id,
            entity_job_id=entity_job_id,
            user_id=user_id,
            total_chunks=n,
            batch_size=batch_size,
        )

        chunk_entities_list = document_entities.chunk_entities
        if len(chunk_entities_list) != n:
            logger.warning(
                "Chunk count mismatch: entities has %s chunks, text has %s; aligning by index",
                len(chunk_entities_list),
                n,
            )

        all_relationships: List[Relationship] = []
        try:
            for i in range(0, n, batch_size):
                batch_size_actual = min(batch_size, n - i)
                tasks = []
                for j in range(batch_size_actual):
                    chunk_idx = i + j
                    chunk_text = chunks[chunk_idx]
                    chunk_ent = (
                        chunk_entities_list[chunk_idx]
                        if chunk_idx < len(chunk_entities_list)
                        else ExtractedEntities(
                            chunk_id=chunk_idx,
                            people=[],
                            organizations=[],
                            dates=[],
                            locations=[],
                            key_terms=[],
                        )
                    )
                    tasks.append(
                        self.extract_relationships_async(
                            chunk_text, chunk_ent, chunk_idx
                        )
                    )
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for j, res in enumerate(batch_results):
                    chunk_idx = i + j
                    if isinstance(res, Exception):
                        logger.error(
                            "Relationship chunk extraction failed",
                            chunk_id=chunk_idx,
                            error=str(res),
                        )
                    else:
                        all_relationships.extend(res.relationships)

                completed = min(i + batch_size_actual, n)
                job_payload["completed_chunks"] = completed
                await cache_set(key, job_payload, ttl_seconds=EXTRACTION_JOB_TTL)
                logger.debug(
                    "Relationship extraction progress",
                    job_id=job_id,
                    completed=completed,
                    total=n,
                )

            graph = self._build_graph(
                document_entities, all_relationships, filename
            )
            job_payload["status"] = "completed"
            job_payload["completed_chunks"] = n
            job_payload["result"] = graph.model_dump()
            job_payload["error"] = None
            await cache_set(key, job_payload, ttl_seconds=EXTRACTION_JOB_TTL)
            logger.success(
                "Relationship extraction job completed",
                job_id=job_id,
                entity_count=graph.entity_count,
                relationship_count=graph.relationship_count,
            )
        except Exception as e:
            logger.exception("Relationship extraction job failed", job_id=job_id)
            job_payload = await cache_get(key) or {}
            job_payload["status"] = "failed"
            job_payload["error"] = str(e)
            job_payload["result"] = None
            await cache_set(key, job_payload, ttl_seconds=EXTRACTION_JOB_TTL)
