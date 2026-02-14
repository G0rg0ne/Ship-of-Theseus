"""
Document upload and retrieval endpoints.
Uses Redis (or in-memory fallback) for document storage.
"""
from datetime import datetime
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from langchain.text_splitter import RecursiveCharacterTextSplitter
from PyPDF2 import PdfReader
from io import BytesIO

from app.api.v1.deps import get_current_user
from app.core.logger import logger
from app.core.cache import (
    cache_get,
    cache_set,
    cache_delete,
    cache_key_document,
    DOCUMENT_TTL,
)

router = APIRouter()

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_CONTENT_TYPE = "application/pdf"


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF bytes. Raises ValueError on failure."""
    logger.debug("Starting PDF text extraction", size_bytes=len(file_bytes))
    reader = PdfReader(BytesIO(file_bytes))
    parts = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
            if text and text.strip():
                parts.append(text.strip())
        except Exception as e:
            logger.error(f"Failed to extract text from page {i + 1}", error=str(e))
            raise ValueError(f"Could not extract text from page {i + 1}: {e}")
    
    result = "\n\n".join(parts) if parts else ""
    logger.success("PDF text extraction completed", pages=len(parts), chars=len(result))
    return result

def _chunk_text(text: str) -> List[str]:
    """Chunk text into smaller chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        length_function=len,
        is_separator_regex=False,
    )
    return splitter.split_text(text)

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a PDF document, extract its text, and store it for the current user.
    """
    user_id = current_user.get("email") or current_user.get("username", "default")
    logger.info(f"Document upload request received", user=user_id, filename=file.filename)
    
    if file.content_type and file.content_type != ALLOWED_CONTENT_TYPE:
        logger.warning("Invalid file type rejected", content_type=file.content_type, user=user_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed",
        )

    # Read and size-check
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        logger.warning("File too large rejected", size_bytes=len(content), user=user_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB",
        )

    if len(content) == 0:
        logger.warning("Empty file rejected", user=user_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )

    try:
        text_content = _extract_text_from_pdf(content)
        
    except ValueError as e:
        logger.error("PDF extraction failed", user=user_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Unexpected error during PDF processing", user=user_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read PDF: {e}",
        )

    doc_payload = {
        "filename": file.filename or "document.pdf",
        "content": text_content,
        "uploaded_at": datetime.utcnow().isoformat() + "Z",
    }
    await cache_set(cache_key_document(user_id), doc_payload, ttl_seconds=DOCUMENT_TTL)

    logger.success(
        "Document uploaded successfully",
        user=user_id,
        filename=file.filename,
        size_bytes=len(content),
        text_length=len(text_content),
    )

    return {
        "filename": doc_payload["filename"],
        "content": text_content,
        "uploaded_at": doc_payload["uploaded_at"],
    }


@router.get("/current")
async def get_current_document(
    current_user: dict = Depends(get_current_user),
):
    """
    Get the currently stored document for the authenticated user.
    """
    user_id = current_user.get("email") or current_user.get("username", "default")
    logger.info("Document retrieval request", user=user_id)

    doc = await cache_get(cache_key_document(user_id))
    if not doc:
        logger.warning("No document found for user", user=user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No document uploaded",
        )

    logger.success(
        "Document retrieved successfully", user=user_id, filename=doc.get("filename")
    )
    return doc


@router.delete("/current")
async def clear_current_document(
    current_user: dict = Depends(get_current_user),
):
    """
    Remove the stored document for the authenticated user.
    """
    user_id = current_user.get("email") or current_user.get("username", "default")
    logger.info("Document deletion request", user=user_id)

    key = cache_key_document(user_id)
    doc = await cache_get(key)
    await cache_delete(key)
    if doc:
        logger.success(
            "Document deleted successfully", user=user_id, filename=doc.get("filename")
        )
    else:
        logger.info("No document to delete", user=user_id)

    return {"message": "Document cleared"}
