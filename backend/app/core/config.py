"""
Application configuration settings.
"""
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings


def _parse_origins(value: str) -> List[str]:
    """Parse comma-separated origins string into a list."""
    if not value or not value.strip():
        return ["http://localhost:3000"]
    return [origin.strip() for origin in value.split(",") if origin.strip()]


class Settings(BaseSettings):
    """Application settings."""
    
    # API Settings
    API_V1_PREFIX: str = "/api"
    PROJECT_NAME: str = "Authentication API"
    VERSION: str = "1.0.0"
    
    # Security - REQUIRED (no defaults for security-critical values)
    SECRET_KEY: str  # Must be set in .env - will raise error if missing
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS - stored as string from env (e.g. "http://localhost:3000,http://localhost:8000")
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    
    @property
    def allowed_origins_list(self) -> List[str]:
        """CORS origins as a list for FastAPI middleware."""
        return _parse_origins(self.ALLOWED_ORIGINS)
    
    # Database (PostgreSQL) - used for user registration/auth
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/shipoftheseus"

    # Debug - optional with default; empty env value is treated as False
    DEBUG: bool = False

    @field_validator("DEBUG", mode="before")
    @classmethod
    def coerce_debug(cls, v: object) -> bool:
        if v is None or v == "":
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes")
        return bool(v)
    
    # Redis (optional; in-memory fallback when not set)
    REDIS_URL: Optional[str] = None
    
    # LLM Configuration
    OPENAI_API_KEY: Optional[str] = None
    ENTITY_EXTRACTION_MODEL: str = "gpt-4o-mini"
    ENTITY_EXTRACTION_BATCH_SIZE: int = 5

    # Relationship extraction (runs after entity extraction)
    RELATIONSHIP_EXTRACTION_BATCH_SIZE: int = 5
    AUTO_EXTRACT_RELATIONSHIPS: bool = True

    # Neo4j graph database (persistent storage for extracted knowledge graphs)
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password123"
    NEO4J_DATABASE: str = "neo4j"

    # GraphRAG: community summarization and embedding
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    COMMUNITY_SUMMARIZATION_MODEL: str = "gpt-4o-mini"

    class Config:
        case_sensitive = True
        env_file = ".env"


# Initialize settings - will raise ValidationError if required fields are missing
settings = Settings()
