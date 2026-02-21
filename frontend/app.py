"""
Main Streamlit application.
"""
import streamlit as st
from utils.auth_utils import init_session_state, is_token_valid, is_authenticated, clear_session
from services.api_client import APIClient
from components.login_form import render_login_form
from components.welcome_page import render_welcome_page

# Page configuration: centered layout keeps content compact and centered naturally
st.set_page_config(
    page_title="Ship of Theseus",
    page_icon="⚓",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Visual polish: card styles, button hover, file uploader, typography
st.markdown("""
    <style>
    /* Constrain and center the content column */
    .main .block-container {
        max-width: 860px !important;
        padding: 2rem 2rem 3rem !important;
    }
    /* Buttons: consistent styling */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
    }
    .stButton > button:hover {
        box-shadow: 0 2px 8px rgba(66, 133, 244, 0.25);
    }
    /* Knowledge graph cards */
    .kg-card {
        background: var(--secondary-background-color, #161b22);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 0.85rem 1.25rem;
        margin-bottom: 0.6rem;
        display: flex;
        flex-direction: column;
        gap: 0;
        transition: box-shadow 0.2s ease, border-color 0.2s ease;
    }
    .kg-card:hover {
        box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        border-color: rgba(66, 133, 244, 0.3);
    }
    .kg-entity {
        font-weight: 600;
        font-size: 1rem;
    }
    .kg-arrow {
        color: rgba(255,255,255,0.5);
        font-size: 1.1rem;
        font-weight: 300;
    }
    .kg-rel {
        font-style: italic;
        color: rgba(255,255,255,0.85);
        font-size: 0.95rem;
    }
    .kg-context {
        width: 100%;
        margin-top: 0.6rem;
        padding-top: 0.5rem;
        padding-left: 0.75rem;
        font-size: 0.82rem;
        color: rgba(255,255,255,0.55);
        font-style: italic;
        border-top: 1px solid rgba(255,255,255,0.07);
        border-left: 3px solid rgba(66, 133, 244, 0.4);
    }
    /* Headers and vertical rhythm */
    h1, h2, h3 {
        font-weight: 600;
        letter-spacing: -0.02em;
    }
    h2 { margin-top: 1.5rem; }
    h3 { margin-top: 1.25rem; }
    /* File uploader area */
    [data-testid="stFileUploader"] {
        border-radius: 10px;
        border: 1px dashed rgba(255,255,255,0.2);
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

