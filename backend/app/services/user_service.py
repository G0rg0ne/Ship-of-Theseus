"""
User service for managing user data.
"""
from typing import Dict
from app.core.config import settings
from app.core.security import get_password_hash

# Module-level cache for user data
_user_password_hash: str = None
_user_data: Dict = None


def initialize_user():
    """Initialize user from environment variables."""
    global _user_password_hash, _user_data
    
    if _user_password_hash is None:
        # Hash the password
        _user_password_hash = get_password_hash(settings.USER_PASSWORD)
        
        # Create user data structure
        _user_data = {
            "username": settings.USERNAME,
            "email": settings.USER_EMAIL,
            "hashed_password": _user_password_hash
        }
        
        print(f"✅ User '{settings.USERNAME}' initialized from environment variables")


def get_user_password_hash() -> str:
    """Get the hashed password for the configured user."""
    if _user_password_hash is None:
        initialize_user()
    return _user_password_hash


def get_user_data() -> Dict:
    """Get the user data for the configured user."""
    if _user_data is None:
        initialize_user()
    return _user_data
