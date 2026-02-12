"""
Welcome page component for authenticated users.
"""
import streamlit as st
from utils.auth_utils import clear_session
from components.pdf_section import render_pdf_section


def render_welcome_page():
    """Render the welcome page for authenticated users."""
    st.markdown("# Welcome to Ship of Theseus")
    
    # Display user info if available
    if st.session_state.get("user_info"):
        user_info = st.session_state.user_info
        st.info(f"👤 Logged in as: **{user_info.get('username', 'Unknown')}**")
    
    # PDF upload and display section
    render_pdf_section()

    st.markdown("---")
    # Logout button
    if st.button("🚪 Logout"):
        clear_session()
        st.rerun()
