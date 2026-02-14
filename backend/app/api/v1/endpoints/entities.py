"""
Entity extraction endpoints.
Uses parallel LLM extraction with progress tracking stored in Redis.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from app.api.v1.deps import get_current_user
from app.services.entity_extraction_service import EntityExtractionService
from app.schemas.entities import (
    DocumentEntities,
    ExtractionJobStatus,
    ExtractionJobStarted,
)
from app.core.config import settings
from app.core.logger import logger
from app.core.cache import cache_get, cache_key_document, cache_key_extraction_job
from app.api.v1.endpoints.documents import _chunk_text

router = APIRouter()


def get_extraction_service() -> EntityExtractionService:
    """Dependency to get entity extraction service."""
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=503, detail="Entity extraction not configured"
        )
    return EntityExtractionService(
        api_key=settings.OPENAI_API_KEY,
        model=settings.ENTITY_EXTRACTION_MODEL,
    )


async def _run_extraction_task(
    job_id: str,
    user_id: str,
    filename: str,
    chunks: list,
) -> None:
    """Background task: run parallel entity extraction and store result in Redis."""
    extractor = EntityExtractionService(
        api_key=settings.OPENAI_API_KEY,
        model=settings.ENTITY_EXTRACTION_MODEL,
    )
    await extractor.extract_from_chunks_parallel(
        chunks=chunks,
        job_id=job_id,
        user_id=user_id,
        filename=filename,
    )


@router.post("/extract", response_model=ExtractionJobStarted)
async def start_entity_extraction(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    extractor: EntityExtractionService = Depends(get_extraction_service),
):
    """
    Start entity extraction on the user's uploaded document.
    Returns a job_id; use GET /extract/status/{job_id} for progress and
    GET /extract/result/{job_id} for the result when completed.
    """
    user_id = current_user.get("email") or current_user.get("username", "default")
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
    current_user: dict = Depends(get_current_user),
):
    """
    Get the status and progress of an entity extraction job.
    """
    user_id = current_user.get("email") or current_user.get("username", "default")
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
    current_user: dict = Depends(get_current_user),
):
    """
    Get the extraction result when the job is completed.
    Returns 202 with status if still running.
    """
    user_id = current_user.get("email") or current_user.get("username", "default")
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
