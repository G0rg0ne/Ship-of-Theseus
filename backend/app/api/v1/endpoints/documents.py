"""
Document upload and retrieval endpoints.
"""
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from PyPDF2 import PdfReader
from io import BytesIO

from app.api.v1.deps import get_current_user

router = APIRouter()

# In-memory storage: keyed by user email
_documents_cache: Dict[str, Dict[str, Any]] = {}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_CONTENT_TYPE = "application/pdf"


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF bytes. Raises ValueError on failure."""
    reader = PdfReader(BytesIO(file_bytes))
    parts = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
            if text and text.strip():
                parts.append(text.strip())
        except Exception as e:
            raise ValueError(f"Could not extract text from page {i + 1}: {e}")
    return "\n\n".join(parts) if parts else ""


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a PDF document, extract its text, and store it for the current user.
    """
    if file.content_type and file.content_type != ALLOWED_CONTENT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed",
        )

    # Read and size-check
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )

    try:
        text_content = _extract_text_from_pdf(content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read PDF: {e}",
        )

    user_id = current_user.get("email") or current_user.get("username", "default")
    _documents_cache[user_id] = {
        "filename": file.filename or "document.pdf",
        "content": text_content,
        "uploaded_at": datetime.utcnow().isoformat() + "Z",
    }

    return {
        "filename": _documents_cache[user_id]["filename"],
        "content": text_content,
        "uploaded_at": _documents_cache[user_id]["uploaded_at"],
    }


@router.get("/current")
async def get_current_document(
    current_user: dict = Depends(get_current_user),
):
    """
    Get the currently stored document for the authenticated user.
    """
    user_id = current_user.get("email") or current_user.get("username", "default")
    doc = _documents_cache.get(user_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No document uploaded",
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
    _documents_cache.pop(user_id, None)
    return {"message": "Document cleared"}
