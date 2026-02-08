"""
Application configuration settings.
"""
import os
from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


def _parse_origins(value: str) -> List[str]:
    """Parse comma-separated origins string into a list."""
    if not value or not value.strip():
        return ["http://localhost:8501"]
    return [origin.strip() for origin in value.split(",") if origin.strip()]


class Settings(BaseSettings):
    """Application settings."""
    
    # API Settings
    API_V1_PREFIX: str = "/api"
    PROJECT_NAME: str = "Authentication API"
    VERSION: str = "1.0.0"
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS - stored as string from env (e.g. "http://localhost:8501,http://127.0.0.1:8501")
    ALLOWED_ORIGINS: str = "http://localhost:8501"
    
    @property
    def allowed_origins_list(self) -> List[str]:
        """CORS origins as a list for FastAPI middleware."""
        return _parse_origins(self.ALLOWED_ORIGINS)
    
    # User Configuration (from environment variables)
    USERNAME: str = os.getenv("USERNAME", "")
    USER_EMAIL: str = os.getenv("USER_EMAIL", "")
    USER_PASSWORD: str = os.getenv("USER_PASSWORD", "")
    
    # Debug
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()

# Validate required environment variables
if not settings.USERNAME or not settings.USER_EMAIL or not settings.USER_PASSWORD:
    raise ValueError(
        "Missing required environment variables: USERNAME, USER_EMAIL, USER_PASSWORD. "
        "Please set these in your .env file."
    )
