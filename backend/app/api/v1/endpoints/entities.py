"""
Entity extraction endpoints.
Uses parallel LLM extraction with progress tracking stored in Redis.
Relationship extraction runs automatically after entity extraction completes.
"""
import uuid
import asyncio
from datetime import datetime
import hashlib
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from app.api.v1.deps import get_current_user
from app.models.user import User
from app.services.entity_extraction_service import EntityExtractionService
from app.services.relationship_extraction_service import RelationshipExtractionService
from app.schemas.entities import (
    DocumentEntities,
    ExtractionJobStatus,
    ExtractionJobStarted,
)
from app.schemas.entities import ExtractedEntities
from app.schemas.relationships import DocumentGraph, RelationshipJobStatus, Relationship
from app.core.config import settings
from app.core.logger import logger
from app.core.cache import (
    cache_get,
    cache_key_document,
    cache_key_extraction_job,
    cache_key_relationship_job,
    cache_key_entities_by_chunk_hash,
    cache_key_relationships_by_chunk_hash,
    cache_set,
    EXTRACTION_JOB_TTL,
    EXTRACTION_CHUNK_CACHE_TTL,
)
from app.api.v1.endpoints.documents import _chunk_text

router = APIRouter()

# Suffix for the relationship job id when auto-triggered after entity extraction
RELATIONSHIP_JOB_ID_SUFFIX = "_rel"


def get_extraction_service() -> EntityExtractionService:
    """Dependency to get entity extraction service."""
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=503, detail="Entity extraction not configured (OPENAI_API_KEY not set)"
        )
    if not settings.ENTITY_EXTRACTION_MODEL:
        raise HTTPException(
            status_code=503, detail="Entity extraction not configured (ENTITY_EXTRACTION_MODEL not set)"
        )
    return EntityExtractionService(
        api_key=settings.OPENAI_API_KEY,
        model=settings.ENTITY_EXTRACTION_MODEL or "gpt-4o-mini",
    )


async def _run_relationship_task(
    rel_job_id: str,
    entity_job_id: str,
    user_id: str,
    filename: str,
    chunks: List[str],
    entity_result: dict,
) -> None:
    """Background task: run relationship extraction after entities are extracted."""
    rel_extractor = RelationshipExtractionService(
        api_key=settings.OPENAI_API_KEY,
        model=settings.ENTITY_EXTRACTION_MODEL or "gpt-4o-mini",
    )
    doc_entities = DocumentEntities(**entity_result)
    await rel_extractor.extract_from_chunks_parallel(
        chunks=chunks,
        document_entities=doc_entities,
        job_id=rel_job_id,
        entity_job_id=entity_job_id,
        user_id=user_id,
        filename=filename,
    )


async def _run_extraction_task(
    job_id: str,
    user_id: str,
    filename: str,
    chunks: list,
) -> None:
    """Background task: run parallel entity extraction and store result in Redis.
    When entity extraction completes, automatically triggers relationship extraction
    if AUTO_EXTRACT_RELATIONSHIPS is True.
    """
    # Streamed extraction: relationship extraction begins per-chunk as soon as that chunk's
    # entities are ready (instead of waiting for all entities to finish).
    extractor = EntityExtractionService(api_key=settings.OPENAI_API_KEY, model=settings.ENTITY_EXTRACTION_MODEL)
    rel_extractor = RelationshipExtractionService(
        api_key=settings.OPENAI_API_KEY,
        model=settings.ENTITY_EXTRACTION_MODEL or "gpt-4o-mini",
    )

    n = len(chunks)
    entity_key = cache_key_extraction_job(job_id)
    rel_job_id = job_id + RELATIONSHIP_JOB_ID_SUFFIX
    rel_key = cache_key_relationship_job(rel_job_id)

    entity_payload: Dict[str, Any] = {
        "status": "running",
        "user_id": user_id,
        "filename": filename,
        "total_chunks": n,
        "completed_chunks": 0,
        "result": None,
        "error": None,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    await cache_set(entity_key, entity_payload, ttl_seconds=EXTRACTION_JOB_TTL)

    relationship_payload: Dict[str, Any] = {
        "status": "pending",
        "user_id": user_id,
        "filename": filename,
        "entity_job_id": job_id,
        "total_chunks": n,
        "completed_chunks": 0,
        "result": None,
        "error": None,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    await cache_set(rel_key, relationship_payload, ttl_seconds=EXTRACTION_JOB_TTL)

    entity_done = 0
    rel_done = 0
    entity_lock = asyncio.Lock()
    rel_lock = asyncio.Lock()

    extracted_by_index: List[ExtractedEntities] = [ExtractedEntities(
        chunk_id=i,
        people=[],
        organizations=[],
        dates=[],
        locations=[],
        key_terms=[],
    ) for i in range(n)]
    all_relationships: List[Relationship] = []
    relationships_lock = asyncio.Lock()

    entity_concurrency = getattr(settings, "ENTITY_EXTRACTION_CONCURRENCY", getattr(settings, "ENTITY_EXTRACTION_BATCH_SIZE", 10)) or 10
    rel_concurrency = getattr(settings, "RELATIONSHIP_EXTRACTION_CONCURRENCY", getattr(settings, "RELATIONSHIP_EXTRACTION_BATCH_SIZE", 10)) or 10
    entity_sem = asyncio.Semaphore(max(1, int(entity_concurrency)))
    rel_sem = asyncio.Semaphore(max(1, int(rel_concurrency)))

    def _chunk_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def _process_chunk(i: int, text: str) -> None:
        nonlocal entity_done, rel_done

        # Entities
        chash = _chunk_hash(text)
        ent_cache_key = cache_key_entities_by_chunk_hash(user_id, chash)
        cached_ent = await cache_get(ent_cache_key)
        if cached_ent:
            try:
                ent = ExtractedEntities(**cached_ent)
                ent.chunk_id = i
            except Exception:
                ent = None
        else:
            ent = None

        if ent is None:
            extraction_succeeded = False
            try:
                async with entity_sem:
                    ent = await extractor.extract_entities_async(text, i)
                extraction_succeeded = True
            except Exception as exc:
                logger.error("Chunk entity extraction failed", chunk_id=i, error=str(exc))
                ent = ExtractedEntities(
                    chunk_id=i,
                    people=[],
                    organizations=[],
                    dates=[],
                    locations=[],
                    key_terms=[],
                )
            # Cache entities by chunk hash for retries on identical content
            # Only cache when the LLM extraction succeeded so transient errors
            # don't poison the cache with empty results.
            if extraction_succeeded:
                try:
                    await cache_set(
                        ent_cache_key,
                        ent.model_dump(),
                        ttl_seconds=EXTRACTION_CHUNK_CACHE_TTL,
                    )
                except Exception:
                    # Cache failures should never fail extraction
                    pass

        extracted_by_index[i] = ent
        async with entity_lock:
            entity_done += 1
            entity_payload["completed_chunks"] = entity_done
            await cache_set(entity_key, entity_payload, ttl_seconds=EXTRACTION_JOB_TTL)

        if not getattr(settings, "AUTO_EXTRACT_RELATIONSHIPS", True):
            return

        # Relationships for this chunk
        # Build a stable entity-list hash for relationship caching (relationship prompt depends on entity list)
        entity_list = rel_extractor.build_entity_list(ent)
        ent_list_hash = hashlib.sha256(entity_list.encode("utf-8")).hexdigest()
        rel_cache_key = cache_key_relationships_by_chunk_hash(user_id, chash, ent_list_hash)
        cached_rels = await cache_get(rel_cache_key)
        if cached_rels is not None:
            try:
                rels = [Relationship(**r) for r in cached_rels]
            except Exception:
                rels = None
        else:
            rels = None

        if rels is None:
            extraction_succeeded = False
            try:
                async with rel_sem:
                    rels = await rel_extractor.extract_relationship_list_async(text, ent, i)
                extraction_succeeded = True
            except Exception as exc:
                logger.error("Chunk relationship extraction failed", chunk_id=i, error=str(exc))
                # Use an empty list for downstream aggregation but do not cache this failure.
                rels = []
            if extraction_succeeded and rels is not None:
                try:
                    await cache_set(
                        rel_cache_key,
                        [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in rels],
                        ttl_seconds=EXTRACTION_CHUNK_CACHE_TTL,
                    )
                except Exception:
                    # Cache failures must not break extraction flow
                    pass

        async with relationships_lock:
            all_relationships.extend(rels)

        async with rel_lock:
            # Mark relationship job running on first completion
            if relationship_payload.get("status") in ("pending", None):
                relationship_payload["status"] = "running"
            rel_done += 1
            relationship_payload["completed_chunks"] = rel_done
            await cache_set(rel_key, relationship_payload, ttl_seconds=EXTRACTION_JOB_TTL)

    try:
        await asyncio.gather(*(_process_chunk(i, chunks[i]) for i in range(n)))

        doc_entities = DocumentEntities(
            filename=filename,
            chunk_entities=extracted_by_index,
            extracted_at=datetime.utcnow().isoformat() + "Z",
        )
        entity_payload["status"] = "completed"
        entity_payload["completed_chunks"] = n
        entity_payload["result"] = doc_entities.model_dump()
        entity_payload["error"] = None
        await cache_set(entity_key, entity_payload, ttl_seconds=EXTRACTION_JOB_TTL)

        if getattr(settings, "AUTO_EXTRACT_RELATIONSHIPS", True):
            graph = rel_extractor.build_graph_from_entities_and_relationships(
                doc_entities, all_relationships, filename
            )
            relationship_payload["status"] = "completed"
            relationship_payload["completed_chunks"] = n
            relationship_payload["result"] = graph.model_dump()
            relationship_payload["error"] = None
            await cache_set(rel_key, relationship_payload, ttl_seconds=EXTRACTION_JOB_TTL)
        else:
            relationship_payload["status"] = "completed"
            relationship_payload["completed_chunks"] = 0
            relationship_payload["result"] = None
            relationship_payload["error"] = None
            await cache_set(rel_key, relationship_payload, ttl_seconds=EXTRACTION_JOB_TTL)

        logger.success(
            "Streamed extraction job completed",
            job_id=job_id,
            chunks=n,
            relationships=len(all_relationships),
        )
    except Exception as exc:
        logger.exception("Streamed extraction job failed", job_id=job_id)
        entity_payload["status"] = "failed"
        entity_payload["error"] = str(exc)
        entity_payload["result"] = None
        await cache_set(entity_key, entity_payload, ttl_seconds=EXTRACTION_JOB_TTL)

        relationship_payload["status"] = "failed"
        relationship_payload["error"] = str(exc)
        relationship_payload["result"] = None
        await cache_set(rel_key, relationship_payload, ttl_seconds=EXTRACTION_JOB_TTL)


@router.post("/extract", response_model=ExtractionJobStarted)
async def start_entity_extraction(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    extractor: EntityExtractionService = Depends(get_extraction_service),
):
    """
    Start entity extraction on the user's uploaded document.
    Returns a job_id; use GET /extract/status/{job_id} for progress and
    GET /extract/result/{job_id} for the result when completed.
    """
    user_id = str(current_user.id)
    logger.info("Entity extraction requested", user=user_id)

    doc = await cache_get(cache_key_document(user_id))
    if not doc:
        raise HTTPException(status_code=404, detail="No document uploaded")

    chunks = _chunk_text(doc["content"])
    filename = doc.get("filename", "document.pdf")
    logger.info("Text chunks prepared for extraction", user=user_id, chunks=len(chunks))

    job_id = str(uuid.uuid4())
    background_tasks.add_task(
        _run_extraction_task,
        job_id=job_id,
        user_id=user_id,
        filename=filename,
        chunks=chunks,
    )

    logger.success("Entity extraction job queued", job_id=job_id, user=user_id)
    return ExtractionJobStarted(job_id=job_id)


@router.get("/extract/status/{job_id}", response_model=ExtractionJobStatus)
async def get_extraction_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the status and progress of an entity extraction job.
    """
    user_id = str(current_user.id)
    key = cache_key_extraction_job(job_id)
    job = await cache_get(key)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")

    return ExtractionJobStatus(
        job_id=job_id,
        status=job.get("status", "pending"),
        total_chunks=job.get("total_chunks", 0),
        completed_chunks=job.get("completed_chunks", 0),
        filename=job.get("filename"),
        created_at=job.get("created_at"),
        error=job.get("error"),
    )


@router.get("/extract/result/{job_id}", response_model=DocumentEntities)
async def get_extraction_result(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the extraction result when the job is completed.
    Returns 202 with status if still running.
    """
    user_id = str(current_user.id)
    key = cache_key_extraction_job(job_id)
    job = await cache_get(key)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")

    status = job.get("status", "pending")
    if status == "running" or status == "pending":
        raise HTTPException(
            status_code=202,
            detail={
                "message": "Extraction still in progress",
                "job_id": job_id,
                "completed_chunks": job.get("completed_chunks", 0),
                "total_chunks": job.get("total_chunks", 0),
            },
        )
    if status == "failed":
        raise HTTPException(
            status_code=500,
            detail=job.get("error", "Extraction failed"),
        )

    result = job.get("result")
    if not result:
        raise HTTPException(status_code=404, detail="Result not available")

    return DocumentEntities(**result)


def _relationship_job_id_for_entity_job(entity_job_id: str) -> str:
    """Return the relationship job id used when relationship extraction is auto-triggered."""
    return entity_job_id + RELATIONSHIP_JOB_ID_SUFFIX


@router.get(
    "/extract/relationships/status/{job_id}",
    response_model=RelationshipJobStatus,
)
async def get_relationship_extraction_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the status and progress of a relationship extraction job.
    Use job_id from the entity extraction job with suffix _rel (e.g. entity_job_id_rel).
    """
    user_id = str(current_user.id)
    key = cache_key_relationship_job(job_id)
    job = await cache_get(key)

    if not job:
        raise HTTPException(status_code=404, detail="Relationship job not found or expired")

    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")

    return RelationshipJobStatus(
        job_id=job_id,
        status=job.get("status", "pending"),
        entity_job_id=job.get("entity_job_id", ""),
        total_chunks=job.get("total_chunks", 0),
        completed_chunks=job.get("completed_chunks", 0),
        filename=job.get("filename"),
        created_at=job.get("created_at"),
        error=job.get("error"),
    )


@router.get(
    "/extract/relationships/result/{job_id}",
    response_model=DocumentGraph,
)
async def get_relationship_extraction_result(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the graph-ready result (nodes + edges) when the relationship extraction job is completed.
    Returns 202 if still running.
    """
    user_id = str(current_user.id)
    key = cache_key_relationship_job(job_id)
    job = await cache_get(key)

    if not job:
        raise HTTPException(status_code=404, detail="Relationship job not found or expired")

    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")

    status = job.get("status", "pending")
    if status in ("running", "pending"):
        raise HTTPException(
            status_code=202,
            detail={
                "message": "Relationship extraction still in progress",
                "job_id": job_id,
                "completed_chunks": job.get("completed_chunks", 0),
                "total_chunks": job.get("total_chunks", 0),
            },
        )
    if status == "failed":
        raise HTTPException(
            status_code=500,
            detail=job.get("error", "Relationship extraction failed"),
        )

    result = job.get("result")
    if not result:
        raise HTTPException(status_code=404, detail="Result not available")

    return DocumentGraph(**result)


@router.get("/extract/graph/{job_id}", response_model=DocumentGraph)
async def get_extraction_graph(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the complete graph (nodes + edges) for an entity extraction job.
    Uses the entity job_id; relationship extraction is auto-triggered with job_id_rel.
    Returns the graph when relationship extraction has completed.
    """
    user_id = str(current_user.id)
    entity_key = cache_key_extraction_job(job_id)
    entity_job = await cache_get(entity_key)

    if not entity_job:
        raise HTTPException(status_code=404, detail="Extraction job not found or expired")

    if entity_job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")

    if entity_job.get("status") != "completed":
        raise HTTPException(
            status_code=202,
            detail={
                "message": "Entity extraction not yet completed",
                "job_id": job_id,
                "status": entity_job.get("status", "pending"),
            },
        )

    rel_job_id = _relationship_job_id_for_entity_job(job_id)
    rel_key = cache_key_relationship_job(rel_job_id)
    rel_job = await cache_get(rel_key)

    if not rel_job:
        raise HTTPException(
            status_code=202,
            detail={
                "message": "Relationship extraction not yet started or job expired",
                "entity_job_id": job_id,
                "relationship_job_id": rel_job_id,
            },
        )

    if rel_job.get("status") in ("running", "pending"):
        raise HTTPException(
            status_code=202,
            detail={
                "message": "Relationship extraction still in progress",
                "job_id": rel_job_id,
                "completed_chunks": rel_job.get("completed_chunks", 0),
                "total_chunks": rel_job.get("total_chunks", 0),
            },
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
