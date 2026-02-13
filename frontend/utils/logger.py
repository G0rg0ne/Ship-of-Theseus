"""
Loguru logger configuration for the Streamlit frontend.
"""
import sys
from pathlib import Path
from loguru import logger


def configure_logging():
    """
    Configure loguru logger for Streamlit application.
    
    Sets up:
    - Console logging with color
    - File rotation for logs
    - Streamlit-friendly formatting
    """
    # Remove default handler
    logger.remove()
    
    # Console handler with custom format
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )
    
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # File handler with rotation
    logger.add(
        log_dir / "frontend_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # Rotate at midnight
        retention="30 days",  # Keep logs for 30 days
        compression="zip",  # Compress old logs
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        enqueue=True,  # Thread-safe logging
    )
    
    logger.info("Frontend logger configured successfully")


# Export the logger for easy importing
__all__ = ["logger", "configure_logging"]
