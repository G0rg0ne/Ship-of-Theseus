"""
Welcome page component for authenticated users.
"""
import streamlit as st
from utils.auth_utils import clear_session
from components.pdf_section import render_pdf_section


def render_welcome_page():
    """Render the welcome page for authenticated users."""
    # Header: title + tagline on left; user chip and logout on right (logout less prominent)
    col_title, col_spacer, col_user = st.columns([2, 1, 1])
    with col_title:
        st.markdown("# ⚓ Ship of Theseus")
        st.caption("Extract knowledge graphs from your documents.")
    with col_user:
        if st.session_state.get("user_info"):
            user_info = st.session_state.user_info
            username = user_info.get("username", "Unknown")
            st.markdown(
                f'<span style="font-size:0.9rem; color: var(--text-color); opacity:0.9;">'
                f"👤 {username}</span>",
                unsafe_allow_html=True,
            )
        if st.button("Log out", key="logout_btn", type="secondary"):
            clear_session()
            st.rerun()

    with st.expander("What happens next?", expanded=False):
        st.markdown(
            """
            1. **Upload** a PDF — drag and drop or browse.
            2. **Process** — we extract entities and relationships into a knowledge graph.
            3. **Explore** — search, filter, and inspect the graph; optionally **Save to Knowledge Base**.
            4. **Clear** when you want to start with a new document.
            """
        )

    st.markdown("---")

    # PDF upload and knowledge graph section
    render_pdf_section()
