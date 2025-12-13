import streamlit as st
import requests
import os
from datetime import datetime, timedelta
import jwt

# Page configuration
st.set_page_config(
    page_title="Authentication App",
    page_icon="🔐",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://backend:8000")
TOKEN_KEY = "auth_token"
USER_KEY = "user_info"

# Custom CSS for better UI
st.markdown("""
    <style>
    .main {
        padding-top: 2rem;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
    }
    .error-message {
        padding: 1rem;
        border-radius: 5px;
        background-color: #ffebee;
        color: #c62828;
        margin: 1rem 0;
    }
    .success-message {
        padding: 1rem;
        border-radius: 5px;
        background-color: #e8f5e9;
        color: #2e7d32;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)


def is_token_valid(token: str) -> bool:
    """Check if JWT token is still valid."""
    try:
        # Decode without verification to check expiration
        decoded = jwt.decode(token, options={"verify_signature": False})
        exp = decoded.get("exp")
        if exp:
            return datetime.fromtimestamp(exp) > datetime.utcnow()
        return False
    except:
        return False


def verify_token_with_api(token: str) -> bool:
    """Verify token with backend API."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{API_BASE_URL}/api/auth/verify",
            headers=headers,
            timeout=5
        )
        return response.status_code == 200
    except:
        return False


def login_user(username: str, password: str) -> tuple[bool, str, dict]:
    """Attempt to login user."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/auth/login",
            json={"username": username, "password": password},
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data["access_token"]
            
            # Get user info
            headers = {"Authorization": f"Bearer {token}"}
            user_response = requests.get(
                f"{API_BASE_URL}/api/auth/me",
                headers=headers,
                timeout=5
            )
            
            if user_response.status_code == 200:
                user_info = user_response.json()
                return True, token, user_info
        
        return False, "", {}
    except Exception as e:
        st.error(f"Connection error: {str(e)}")
        return False, "", {}


def logout_user():
    """Clear session state."""
    for key in [TOKEN_KEY, USER_KEY]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


# Initialize session state
if TOKEN_KEY not in st.session_state:
    st.session_state[TOKEN_KEY] = None
if USER_KEY not in st.session_state:
    st.session_state[USER_KEY] = None

# Check if user is already logged in
if st.session_state[TOKEN_KEY]:
    token = st.session_state[TOKEN_KEY]
    if is_token_valid(token) and verify_token_with_api(token):
        # User is authenticated, show welcome page
        user_info = st.session_state[USER_KEY]
        
        # Welcome message
        st.markdown("# Welcome to Ship of Theseus")
        
        # Logout button
        if st.button("🚪 Logout"):
            logout_user()
        
    else:
        # Token expired or invalid
        st.session_state[TOKEN_KEY] = None
        st.session_state[USER_KEY] = None
        st.rerun()
else:
    # Show login interface
    st.header("🔐 Login")
    st.info("Please enter your credentials to access the application.")
    
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Enter your username")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        submit = st.form_submit_button("Login", use_container_width=True)
        
        if submit:
            if username and password:
                success, token, user_info = login_user(username, password)
                if success:
                    st.session_state[TOKEN_KEY] = token
                    st.session_state[USER_KEY] = user_info
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
            else:
                st.error("Please fill in all fields")

