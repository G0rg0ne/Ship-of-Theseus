from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.api.v1.deps import get_current_user
from app.services.entity_extraction_service import EntityExtractionService
from app.schemas.entities import DocumentEntities, ExtractedEntities
from app.core.config import settings
from app.core.logger import logger
from app.api.v1.endpoints.documents import _documents_cache, _chunk_text

router = APIRouter()

def get_extraction_service() -> EntityExtractionService:
    """Dependency to get entity extraction service."""
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="Entity extraction not configured")
    return EntityExtractionService(
        api_key=settings.OPENAI_API_KEY,
        model=settings.ENTITY_EXTRACTION_MODEL
    )

@router.post("/extract", response_model=DocumentEntities)
async def extract_entities_from_document(
    current_user: dict = Depends(get_current_user),
    extractor: EntityExtractionService = Depends(get_extraction_service)
):
    """Extract entities from the user's uploaded document."""
    user_id = current_user.get("email") or current_user.get("username", "default")
    logger.info("Entity extraction requested", user=user_id)
    
    doc = _documents_cache.get(user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="No document uploaded")
    
    # Chunk the document
    chunks = _chunk_text(doc["content"])
    logger.info("Text chunks extracted", user=user_id, chunks=len(chunks))
    # Extract entities from each chunk
    try:
        chunk_entities = extractor.extract_entities(chunks)
        
        result = DocumentEntities(
            filename=doc["filename"],
            chunk_entities=chunk_entities,
            extracted_at=datetime.utcnow().isoformat() + "Z"
        )
        
        logger.success("Entity extraction completed", 
                      user=user_id, 
                      chunks=len(chunk_entities))
        return result
        
    except Exception as e:
        logger.exception("Entity extraction failed", user=user_id)
        raise HTTPException(status_code=500, detail=str(e))