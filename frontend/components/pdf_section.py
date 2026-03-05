"""
PDF upload section and knowledge brain display for authenticated users.

The entity/relationship raw viewer has been removed; extracted graphs are now
automatically merged into the user's knowledge brain via community detection.
"""
import time
from typing import Optional

import streamlit as st
from services.api_client import APIClient

EXTRACTION_POLL_INTERVAL_SEC = 2
EXTRACTION_TIMEOUT_SEC = 600  # 10 minutes

# Processing state values for stable UI
PROCESSING_IDLE = "idle"
PROCESSING_UPLOADING = "uploading"
PROCESSING_ENTITIES = "extracting_entities"
PROCESSING_RELATIONSHIPS = "extracting_relationships"
PROCESSING_DONE = "done"
PROCESSING_ERROR = "error"

# Community colour palette (cycling)
_COMMUNITY_COLORS = [
    "#4285F4", "#34A853", "#FBBC04", "#9334E6",
    "#EA4335", "#00ACC1", "#F4511E", "#0B8043",
]


def _clear_processing_state():
    """Clear processing-related session state."""
    for key in ("processing_state", "processing_job_id", "processing_progress"):
        if key in st.session_state:
            del st.session_state[key]


def _poll_extraction_once(
    api_client: APIClient, job_id: str, token: str
) -> tuple[str, Optional[str]]:
    """
    Perform one extraction status poll and update session state.
    Returns ("done_success", None) | ("done_error", message) | ("continue", None).
    Caller should st.rerun() when "continue" so the UI refreshes and this runs again.
    """
    if "extraction_poll_start" not in st.session_state:
        st.session_state.extraction_poll_start = time.time()

    start_time = st.session_state.extraction_poll_start
    if time.time() - start_time > EXTRACTION_TIMEOUT_SEC:
        _clear_processing_state()
        if "extraction_poll_start" in st.session_state:
            del st.session_state["extraction_poll_start"]
        st.session_state.processing_state = PROCESSING_ERROR
        return "done_error", "Extraction timed out."

    success, status_data, error = api_client.get_extraction_status(job_id, token)
    if not success:
        _clear_processing_state()
        if "extraction_poll_start" in st.session_state:
            del st.session_state["extraction_poll_start"]
        st.session_state.processing_state = PROCESSING_ERROR
        return "done_error", error or "Status check failed"

    completed = status_data.get("completed_chunks", 0)
    total = max(status_data.get("total_chunks", 1), 1)
    job_status = status_data.get("status", "pending")

    if job_status == "running" or job_status == "pending":
        st.session_state.processing_progress = {
            "completed": completed,
            "total": total,
            "message": f"Extracting entities: {completed}/{total} chunks",
        }
        return "continue", None

    if job_status == "failed":
        _clear_processing_state()
        if "extraction_poll_start" in st.session_state:
            del st.session_state["extraction_poll_start"]
        st.session_state.processing_state = PROCESSING_ERROR
        return "done_error", status_data.get("error", "Unknown error")

    # job_status == "completed" -> wait for graph (relationship extraction)
    st.session_state.processing_state = PROCESSING_RELATIONSHIPS
    st.session_state.processing_progress = {
        "completed": total,
        "total": total,
        "message": "Building relationships from entities…",
    }
    success_g, graph_data, err_g = api_client.get_extraction_graph(job_id, token)
    if success_g and graph_data:
        st.session_state.extraction_results = graph_data
        st.session_state.extraction_job_id = job_id
        _clear_processing_state()
        if "extraction_poll_start" in st.session_state:
            del st.session_state["extraction_poll_start"]
        st.session_state.processing_state = PROCESSING_DONE
        return "done_success", None
    if not success_g and err_g and err_g != "Graph not ready":
        _clear_processing_state()
        if "extraction_poll_start" in st.session_state:
            del st.session_state["extraction_poll_start"]
        st.session_state.processing_state = PROCESSING_ERROR
        return "done_error", err_g
    # Graph not ready yet; keep showing "Building relationships…" and continue polling
    return "continue", None


def _render_extraction_summary(graph_data: dict) -> None:
    """Show a compact extraction summary (entity + relationship counts)."""
    node_count = len(graph_data.get("nodes") or [])
    edge_count = len(graph_data.get("edges") or [])
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Entities extracted", node_count)
    with col2:
        st.metric("Relationships found", edge_count)


def _render_community_card(idx: int, community: dict) -> None:
    """Render a single community card."""
    color = _COMMUNITY_COLORS[idx % len(_COMMUNITY_COLORS)]
    cid = community.get("community_id", f"community_{idx}")
    node_count = community.get("node_count", 0)
    top_entities = community.get("top_entities") or []
    keywords = community.get("keywords") or []
    doc_sources = community.get("document_sources") or []

    entities_str = " · ".join(top_entities) if top_entities else "—"
    keywords_str = ", ".join(keywords) if keywords else "—"

    card_html = (
        f'<div style="border-left:4px solid {color};padding:0.6rem 1rem;'
        f'margin-bottom:0.6rem;background:#f8f9fa;border-radius:0 6px 6px 0;">'
        f'<div style="font-weight:600;color:{color};font-size:0.9rem;">{cid.replace("_", " ").title()}'
        f' &nbsp;<span style="color:#5f6368;font-weight:400;font-size:0.8rem;">({node_count} entities)</span></div>'
        f'<div style="font-size:0.82rem;margin-top:0.2rem;color:#202124;">{entities_str}</div>'
    )
    if keywords:
        card_html += (
            f'<div style="font-size:0.76rem;color:#5f6368;margin-top:0.15rem;">'
            f'Keywords: {keywords_str}</div>'
        )
    if doc_sources:
        docs_str = ", ".join(doc_sources)
        card_html += (
            f'<div style="font-size:0.72rem;color:#9aa0a6;margin-top:0.1rem;">'
            f'From: {docs_str}</div>'
        )
    card_html += "</div>"
    st.markdown(card_html, unsafe_allow_html=True)


def _render_brain_section(brain: dict) -> None:
    """Render the user's knowledge brain community summary."""
    st.markdown("### Your Knowledge Brain")

    communities = brain.get("communities") or []
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Documents", brain.get("document_count", 0))
    with col2:
        st.metric("Total entities", brain.get("total_nodes", 0))
    with col3:
        st.metric("Relationships", brain.get("total_edges", 0))
    with col4:
        st.metric("Communities", brain.get("community_count", 0))

    last_updated = brain.get("last_updated", "")
    if last_updated:
        st.caption(f"Last updated: {last_updated[:19].replace('T', ' ')} UTC")

    st.markdown("---")
    if not communities:
        st.info("No communities detected yet.")
        return

    st.markdown(
        "Each community groups entities that are closely connected across your documents."
    )
    for i, community in enumerate(communities):
        _render_community_card(i, community)


def render_pdf_section():
    """Render the PDF upload section and the knowledge brain display."""
    token = st.session_state.get("auth_token")
    if not token:
        st.warning("You must be logged in to upload documents.")
        return

    api_client = APIClient()

    if "processing_state" not in st.session_state:
        st.session_state.processing_state = PROCESSING_IDLE
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    if "processing_progress" not in st.session_state:
        st.session_state.processing_progress = {}

    if "current_pdf" not in st.session_state and not st.session_state.get("pdf_fetched"):
        st.session_state.pdf_fetched = True
        success, data, _ = api_client.get_current_document(token)
        if success and data:
            st.session_state.current_pdf = data

    # ----- Upload card -----
    st.markdown("## PDF Document Upload")
    upload_container = st.container()
    with upload_container:
        uploaded_file = st.file_uploader(
            "Choose a PDF file",
            type=["pdf"],
            accept_multiple_files=False,
            key=f"pdf_uploader_{st.session_state.uploader_key}",
        )
        if uploaded_file is not None:
            size_kb = len(uploaded_file.getvalue()) / 1024
            st.caption(f"**{uploaded_file.name}** — {size_kb:.1f} KB")
            file_id = f"{uploaded_file.name}_{uploaded_file.size}"
            last_processed = st.session_state.get("last_processed_file")
            if file_id != last_processed and st.session_state.processing_state == PROCESSING_IDLE:
                if st.button("Process Document", type="primary", key="process_pdf"):
                    st.session_state.processing_state = PROCESSING_UPLOADING
                    file_data = uploaded_file.read()
                    success, data, error = api_client.upload_pdf(
                        file_data, uploaded_file.name, token
                    )
                    if not success or not data:
                        st.session_state.processing_state = PROCESSING_IDLE
                        st.error(f"Upload failed: {error or 'Unknown error.'}")
                    else:
                        st.session_state.current_pdf = data
                        st.session_state.last_processed_file = file_id
                        for key in ("extraction_results", "extraction_job_id", "graph_saved_to_kb", "extraction_error"):
                            if key in st.session_state:
                                del st.session_state[key]
                        success, job_id, error = api_client.start_entity_extraction(token)
                        if not success or not job_id:
                            st.session_state.processing_state = PROCESSING_IDLE
                            st.session_state.uploader_key += 1
                            st.error(f"Failed to start extraction: {error or 'Unknown error.'}")
                        else:
                            st.session_state.processing_state = PROCESSING_ENTITIES
                            st.session_state.processing_job_id = job_id
                            st.session_state.processing_progress = {
                                "completed": 0,
                                "total": 1,
                                "message": "Starting extraction…",
                            }
                            if "extraction_poll_start" in st.session_state:
                                del st.session_state["extraction_poll_start"]
                            st.rerun()

    # ----- Processing status and poll (one poll per run, then rerun to refresh) -----
    if st.session_state.processing_state in (PROCESSING_ENTITIES, PROCESSING_RELATIONSHIPS):
        job_id = st.session_state.get("processing_job_id")
        if job_id:
            progress = st.session_state.get("processing_progress") or {}
            msg = progress.get("message", "Processing…")
            completed = progress.get("completed", 0)
            total = max(progress.get("total", 1), 1)
            with st.status(msg, expanded=True) as status:
                st.caption(msg)
                if total > 0:
                    p = (0.4 * (completed / total) if st.session_state.processing_state == PROCESSING_ENTITIES
                         else 0.4 + 0.3 * (completed / total))
                    st.progress(min(p, 1.0))
                else:
                    st.progress(0.0)
                outcome, err = _poll_extraction_once(api_client, job_id, token)
                if outcome == "done_success":
                    status.update(label="Done", state="complete")
                    st.success("Entities and relationships extracted.")
                    st.rerun()
                elif outcome == "done_error":
                    status.update(label="Error", state="error")
                    st.session_state.extraction_error = (
                        "Couldn't extract the knowledge graph. " + (err or "Unknown error.")
                    )
                    st.error(err or "Unknown error.")
                    st.rerun()
                else:
                    # continue: wait before next poll so we don't hammer the API
                    time.sleep(EXTRACTION_POLL_INTERVAL_SEC)
                    st.rerun()

    # ----- Current document and results -----
    current = st.session_state.get("current_pdf")
    if current:
        filename = current.get("filename", "document.pdf")
        st.caption(f"Document: **{filename}**")

        if "extraction_error" in st.session_state:
            st.error(st.session_state.extraction_error)
            if st.button("Try again", key="try_again"):
                del st.session_state.extraction_error
                st.session_state.uploader_key += 1
                st.session_state.processing_state = PROCESSING_IDLE
                if "extraction_poll_start" in st.session_state:
                    del st.session_state["extraction_poll_start"]
                st.rerun()

        elif "extraction_results" in st.session_state:
            _render_extraction_summary(st.session_state.extraction_results)

            job_id = st.session_state.get("extraction_job_id")
            saved_to_kb = st.session_state.get("graph_saved_to_kb", False)
            if job_id:
                if saved_to_kb:
                    col_msg, col_btn = st.columns([4, 1])
                    with col_msg:
                        st.success("Document added to your Knowledge Brain")
                    with col_btn:
                        if st.button("Upload another", key="upload_another", type="secondary"):
                            success_clear, _ = api_client.clear_current_document(token)
                            for key in (
                                "current_pdf", "last_processed_file", "extraction_results",
                                "extraction_job_id", "graph_saved_to_kb", "extraction_error",
                            ):
                                if key in st.session_state:
                                    del st.session_state[key]
                            _clear_processing_state()
                            st.session_state.uploader_key += 1
                            st.rerun()
                else:
                    if st.button(
                        "Add to Knowledge Base",
                        key="save_to_neo4j",
                        help="Save this graph and merge it into your knowledge brain",
                    ):
                        with st.spinner("Saving graph and rebuilding brain..."):
                            success, save_data, error = api_client.save_graph_to_neo4j(job_id, token)
                        if success:
                            st.session_state.graph_saved_to_kb = True
                            # Invalidate cached brain so it reloads fresh
                            if "user_brain" in st.session_state:
                                del st.session_state["user_brain"]
                            st.success(
                                f"Graph saved as **{save_data.get('document_name', filename)}**. "
                                "Community detection is running in the background."
                            )
                            st.rerun()
                        else:
                            st.error(error or "Failed to save graph.")

        with st.expander("Clear document and start over", expanded=False):
            st.caption("This will remove the current document and extracted graph from this session.")
            if st.checkbox("I want to clear the current document", key="clear_confirm"):
                if st.button("Clear document", key="clear_pdf", type="secondary"):
                    success, error = api_client.clear_current_document(token)
                    if success:
                        for key in (
                            "current_pdf", "last_processed_file", "extraction_results",
                            "extraction_job_id", "graph_saved_to_kb", "extraction_error",
                        ):
                            if key in st.session_state:
                                del st.session_state[key]
                        _clear_processing_state()
                        st.session_state.uploader_key += 1
                        st.rerun()
                    else:
                        st.error(error or "Failed to clear document.")

    st.markdown("---")

    # ----- Knowledge Brain section -----
    st.markdown("## Knowledge Brain")
    st.caption(
        "Your brain is built automatically each time you add a document to the knowledge base. "
        "It merges all your documents into a single graph and detects clusters of related knowledge."
    )

    brain_col, refresh_col = st.columns([5, 1])
    with refresh_col:
        if st.button("Refresh", key="refresh_brain", help="Re-run community detection now"):
            with st.spinner("Running community detection..."):
                ok, brain_data, err = api_client.trigger_community_detection(token)
            if ok and brain_data:
                st.session_state.user_brain = brain_data
                st.rerun()
            else:
                st.error(err or "Detection failed.")

    with st.expander("Clear Brain — start from scratch", expanded=False):
        st.caption("Permanently delete your brain and all saved document graphs from the knowledge base. This cannot be undone.")
        clear_confirm = st.checkbox("I want to permanently delete my brain and all saved graphs", key="clear_brain_confirm")
        if clear_confirm and st.button("Clear Brain", key="clear_brain_btn", type="secondary"):
            success, error = api_client.delete_user_brain(token)
            if success:
                if "user_brain" in st.session_state:
                    del st.session_state["user_brain"]
                st.success("Brain and all saved graphs deleted.")
                st.rerun()
            else:
                st.error(error or "Failed to delete brain.")

    # Load brain if not already in session state
    if "user_brain" not in st.session_state:
        ok, brain_data, err = api_client.get_user_brain(token)
        if ok and brain_data:
            st.session_state.user_brain = brain_data

    brain = st.session_state.get("user_brain")
    if brain:
        _render_brain_section(brain)
    else:
        st.info(
            "No brain data yet. Upload a document, extract its knowledge graph, "
            "then click **Add to Knowledge Base** to build your brain."
        )
