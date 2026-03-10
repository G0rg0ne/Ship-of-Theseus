"""
Relationship extraction service using LangChain and LLM.
Constrains relationships to only use previously extracted entities.
Supports parallel chunk processing with progress tracking via Redis.
Outputs graph-ready format (nodes + edges).
"""
import asyncio
import random
import re
from datetime import datetime
from typing import Dict, List, Set, Tuple

from langchain_openai import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate

from app.core.config import settings
from app.core.logger import logger
from app.core.prompt_manager import PromptManager
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
        prompt_data = PromptManager.get_prompt("relationship_extraction")
        self.prompt = PromptTemplate(
            template=prompt_data["template"],
            input_variables=prompt_data["input_variables"],
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
            lines.append(f"- {loc.name} (Location)")
        for term in chunk_entities.key_terms:
            lines.append(f"- {term.name} (KeyTerm)")
        return "\n".join(lines) if lines else "(No entities in this chunk)"

    def build_entity_list(self, chunk_entities: ExtractedEntities) -> str:
        """Public wrapper for building the entity list string used in the prompt."""
        return self._build_entity_list(chunk_entities)

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
                # Expected: LLM often returns source/target not in entity set; we keep graph consistent
                logger.debug(
                    "Relationship skipped (source or target not in entity set)",
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
        result = await self._ainvoke_with_retry(
            {"entity_list": entity_list, "text": text}, chunk_id=chunk_id
        )
        result.chunk_id = chunk_id
        return result

    async def extract_relationship_list_async(
        self,
        text: str,
        chunk_entities: ExtractedEntities,
        chunk_id: int,
    ) -> List[Relationship]:
        """Extract relationships for a chunk and return Relationship list."""
        res = await self.extract_relationships_async(text, chunk_entities, chunk_id)
        return res.relationships or []

    async def _ainvoke_with_retry(self, payload: dict, *, chunk_id: int) -> ExtractedRelationships:
        attempts = max(1, int(getattr(settings, "LLM_RETRY_MAX_ATTEMPTS", 3) or 3))
        base_ms = int(getattr(settings, "LLM_RETRY_BASE_DELAY_MS", 500) or 500)
        max_ms = int(getattr(settings, "LLM_RETRY_MAX_DELAY_MS", 5_000) or 5_000)

        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await self.chain.ainvoke(payload)
            except Exception as exc:
                last_exc = exc if isinstance(exc, Exception) else Exception(str(exc))
                if attempt >= attempts:
                    break
                delay_ms = min(max_ms, base_ms * (2 ** (attempt - 1)))
                jitter = random.uniform(0.75, 1.25)
                await asyncio.sleep((delay_ms * jitter) / 1000.0)
                logger.warning(
                    "Relationship extraction transient failure; retrying",
                    chunk_id=chunk_id,
                    attempt=attempt,
                    max_attempts=attempts,
                    error=str(last_exc),
                )

        assert last_exc is not None
        raise last_exc

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
                name = loc.name.strip()
                if name and name not in label_to_id:
                    nid = _slug(name, idx)
                    idx += 1
                    label_to_id[name] = nid
                    props = {}
                    if loc.description is not None:
                        props["description"] = loc.description
                    nodes.append(
                        GraphNode(id=nid, label=name, type="location", properties=props)
                    )
            for term in chunk_ent.key_terms:
                name = term.name.strip()
                if name and name not in label_to_id:
                    nid = _slug(name, idx)
                    idx += 1
                    label_to_id[name] = nid
                    props = {}
                    if term.description is not None:
                        props["description"] = term.description
                    nodes.append(
                        GraphNode(id=nid, label=name, type="key_term", properties=props)
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

    def build_graph_from_entities_and_relationships(
        self,
        document_entities: DocumentEntities,
        all_relationships: List[Relationship],
        filename: str,
    ) -> DocumentGraph:
        """Public wrapper for building a graph from extracted entities and relationships."""
        return self._build_graph(document_entities, all_relationships, filename)

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
        concurrency = getattr(settings, "RELATIONSHIP_EXTRACTION_CONCURRENCY", batch_size) or batch_size
        semaphore = asyncio.Semaphore(max(1, int(concurrency)))

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
                            key_terms=[],  # List[LocationEntity] / List[KeyTermEntity]
                        )
                    )
                    tasks.append(
                        self._extract_relationships_async_limited(
                            semaphore, chunk_text, chunk_ent, chunk_idx
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

    async def _extract_relationships_async_limited(
        self,
        semaphore: asyncio.Semaphore,
        text: str,
        chunk_entities: ExtractedEntities,
        chunk_id: int,
    ) -> ExtractedRelationships:
        async with semaphore:
            return await self.extract_relationships_async(text, chunk_entities, chunk_id)
