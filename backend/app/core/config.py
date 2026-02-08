"""
Application configuration settings.
"""
import os
from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings."""
    
    # API Settings
    API_V1_PREFIX: str = "/api"
    PROJECT_NAME: str = "Authentication API"
    VERSION: str = "1.0.0"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # CORS
    ALLOWED_ORIGINS: List[str] = os.getenv("ALLOWED_ORIGINS", "http://localhost:8501").split(",")
    
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
