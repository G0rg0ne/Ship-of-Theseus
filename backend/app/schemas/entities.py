from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import date

class Person(BaseModel):
    """Extracted person entity."""
    name: str = Field(description="Full name of the person")
    role: Optional[str] = Field(None, description="Job title or role")
    organization: Optional[str] = Field(None, description="Associated organization")

class Organization(BaseModel):
    """Extracted organization entity."""
    name: str = Field(description="Organization name")
    type: Optional[str] = Field(None, description="Type (company, NGO, government, etc.)")
    location: Optional[str] = Field(None, description="Location or headquarters")

class DateEntity(BaseModel):
    """Extracted date or time reference."""
    text: str = Field(description="Original date text")
    parsed_date: Optional[date] = Field(None, description="Structured date if parseable")
    context: Optional[str] = Field(None, description="What the date refers to")

class ExtractedEntities(BaseModel):
    """All entities extracted from a text chunk."""
    chunk_id: int = Field(description="Index of the chunk")
    people: List[Person] = Field(default_factory=list)
    organizations: List[Organization] = Field(default_factory=list)
    dates: List[DateEntity] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    key_terms: List[str] = Field(default_factory=list, description="Domain-specific terms")

class DocumentEntities(BaseModel):
    """All entities from a complete document."""
    filename: str
    chunk_entities: List[ExtractedEntities]
    extracted_at: str


class ExtractionJobStatus(BaseModel):
    """Status of an entity extraction job (for progress tracking)."""
    job_id: str
    status: str  # pending | running | completed | failed
    total_chunks: int
    completed_chunks: int
    filename: Optional[str] = None
    created_at: Optional[str] = None
    error: Optional[str] = None


class ExtractionJobStarted(BaseModel):
    """Response when an extraction job is started."""
    job_id: str
    message: str = "Entity extraction started. Poll /extract/status/{job_id} for progress."