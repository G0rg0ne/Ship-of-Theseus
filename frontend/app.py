"""
Main Streamlit application.
"""
import streamlit as st
from utils.auth_utils import init_session_state, is_token_valid, is_authenticated, clear_session
from services.api_client import APIClient
from components.login_form import render_login_form
from components.welcome_page import render_welcome_page

# Page configuration
st.set_page_config(
    page_title="Authentication App",
    page_icon="🔐",
    layout="centered",
    initial_sidebar_state="collapsed"
)

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
    </style>
""", unsafe_allow_html=True)

# Initialize session state
init_session_state()

# Check if user is already logged in
if is_authenticated():
    token = st.session_state.auth_token
    
    # Verify token is still valid
    if is_token_valid(token):
        api_client = APIClient()
        if api_client.verify_token(token):
            # User is authenticated, show welcome page
            render_welcome_page()
        else:
            # Token invalid with API
            clear_session()
            st.rerun()
    else:
        # Token expired
        clear_session()
        st.rerun()
else:
    # Show login interface
    render_login_form()

