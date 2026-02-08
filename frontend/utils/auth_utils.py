"""
Authentication utility functions.
"""
from datetime import datetime
import jwt
import streamlit as st


def is_token_valid(token: str) -> bool:
    """
    Check if JWT token is still valid.
    
    Args:
        token: JWT access token
        
    Returns:
        True if token is valid, False otherwise
    """
    try:
        # Decode without verification to check expiration
        decoded = jwt.decode(token, options={"verify_signature": False})
        exp = decoded.get("exp")
        if exp:
            return datetime.fromtimestamp(exp) > datetime.utcnow()
        return False
    except:
        return False


def clear_session():
    """Clear all authentication-related session state."""
    keys_to_clear = ["auth_token", "user_info"]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]


def init_session_state():
    """Initialize session state variables."""
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = None
    if "user_info" not in st.session_state:
        st.session_state.user_info = None


def is_authenticated() -> bool:
    """Check if user is authenticated."""
    return (
        st.session_state.get("auth_token") is not None and
        st.session_state.get("user_info") is not None
    )
