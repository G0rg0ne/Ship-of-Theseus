"""
Welcome page component for authenticated users.
"""
import streamlit as st
from utils.auth_utils import clear_session
from components.pdf_section import render_pdf_section


def render_welcome_page():
    """Render the welcome page for authenticated users."""
    username = "Unknown"
    if st.session_state.get("user_info"):
        username = st.session_state.user_info.get("username", "Unknown")

    # Header row: branding left, account controls right (no nested columns)
    col_title, col_account = st.columns([5, 2])
    with col_title:
        st.markdown("# ⚓ Ship of Theseus")
        st.caption("Extract knowledge graphs from your documents.")
    with col_account:
        st.markdown(
            f"""
            <div style="
                display: flex;
                align-items: center;
                justify-content: flex-end;
                gap: 0.5rem;
                padding-top: 0.75rem;
                padding-bottom: 0.4rem;
            ">
                <span style="
                    font-size: 0.65rem;
                    font-weight: 700;
                    letter-spacing: 0.06em;
                    text-transform: uppercase;
                    color: #4285f4;
                    background: rgba(66, 133, 244, 0.12);
                    border: 1px solid rgba(66, 133, 244, 0.25);
                    padding: 0.1rem 0.45rem;
                    border-radius: 4px;
                ">Admin</span>
                <span style="
                    font-size: 0.85rem;
                    color: rgba(255,255,255,0.75);
                ">{username}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Log out", key="logout_btn", type="secondary", use_container_width=True):
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
