"""
PDF upload and display section for authenticated users.
"""
import time
import streamlit as st
from services.api_client import APIClient

EXTRACTION_POLL_INTERVAL_SEC = 2
EXTRACTION_TIMEOUT_SEC = 600  # 10 minutes


def _render_entities_with_relationships_section(graph_data: dict) -> None:
    """Render expandable section with entities (nodes) and their relationships (edges)."""
    nodes = graph_data.get("nodes") or []
    edges = graph_data.get("edges") or []
    if not nodes and not edges:
        return
    with st.expander("📊 Entities & Relationships", expanded=True):
        # Build lookup: node id -> node (for edge labels)
        id_to_node = {n.get("id"): n for n in nodes}
        # Group nodes by type
        by_type = {}
        for n in nodes:
            t = n.get("type") or "other"
            by_type.setdefault(t, []).append(n)
        type_order = ("person", "organization", "location", "key_term", "other")
        for node_type in type_order:
            if node_type not in by_type:
                continue
            label = node_type.replace("_", " ").title()
            st.markdown(f"**{label}s**")
            for n in sorted(by_type[node_type], key=lambda x: (x.get("label") or "")):
                lbl = n.get("label") or n.get("id") or "—"
                props = n.get("properties") or {}
                if props:
                    parts = [f"{k}: {v}" for k, v in props.items() if v]
                    st.write(f"- **{lbl}** " + (f" ({', '.join(parts)})" if parts else ""))
                else:
                    st.write(f"- **{lbl}**")
        if edges:
            st.markdown("---")
            st.markdown("**Relationships**")
            for e in edges:
                src = id_to_node.get(e.get("source"), {})
                tgt = id_to_node.get(e.get("target"), {})
                src_label = src.get("label") or e.get("source", "?")
                tgt_label = tgt.get("label") or e.get("target", "?")
                rel = e.get("relation_type") or "related_to"
                props = e.get("properties") or {}
                ctx = props.get("context")
                line = f"**{src_label}** — *{rel}* → **{tgt_label}**"
                if ctx:
                    line += f"  \n  _{ctx}_"
                st.write(line)


def render_pdf_section():
    """Render the PDF upload section and display extracted content."""
    st.markdown("## PDF Document Upload")

    token = st.session_state.get("auth_token")
    if not token:
        st.warning("You must be logged in to upload documents.")
        return

    api_client = APIClient()

    # On first load, try to fetch current document from backend (once per session)
    if "current_pdf" not in st.session_state and not st.session_state.get("pdf_fetched"):
        st.session_state.pdf_fetched = True
        success, data, _ = api_client.get_current_document(token)
        if success and data:
            st.session_state.current_pdf = data

    # Initialize uploader key counter for resetting
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    # File uploader with dynamic key to allow reset
    uploaded_file = st.file_uploader(
        "Choose a PDF file",
        type=["pdf"],
        accept_multiple_files=False,
        key=f"pdf_uploader_{st.session_state.uploader_key}",
    )

    # Show process button if a file is uploaded
    if uploaded_file is not None:
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        last_processed = st.session_state.get("last_processed_file")
        
        # Only show button if this file hasn't been processed yet
        if file_id != last_processed:
            if st.button("📄 Process Document", type="primary", key="process_pdf"):
                file_data = uploaded_file.read()
                success, data, error = api_client.upload_pdf(
                    file_data, uploaded_file.name, token
                )
                if not success or not data:
                    st.error(f"❌ {error or 'Upload failed.'}")
                else:
                    st.session_state.current_pdf = data
                    st.session_state.last_processed_file = file_id
                    # Clear previous extraction results and errors for the new document
                    if "extraction_results" in st.session_state:
                        del st.session_state.extraction_results
                    if "extraction_job_id" in st.session_state:
                        del st.session_state.extraction_job_id
                    if "graph_saved_to_kb" in st.session_state:
                        del st.session_state.graph_saved_to_kb
                    if "extraction_error" in st.session_state:
                        del st.session_state.extraction_error

                    # Start entity extraction
                    success, job_id, error = api_client.start_entity_extraction(token)
                    if not success or not job_id:
                        st.session_state.uploader_key += 1
                        st.error(f"❌ {error or 'Failed to start entity extraction.'}")
                    else:
                        progress_bar = st.progress(0.0)
                        status_placeholder = st.empty()
                        start_time = time.time()
                        extraction_ok = False
                        extraction_error_reason = None
                        if "extraction_error" in st.session_state:
                            del st.session_state.extraction_error
                        while (time.time() - start_time) < EXTRACTION_TIMEOUT_SEC:
                            success, status_data, error = api_client.get_extraction_status(
                                job_id, token
                            )
                            if not success:
                                extraction_error_reason = error or "Status check failed"
                                status_placeholder.error(f"Status check failed: {error}")
                                break
                            completed = status_data.get("completed_chunks", 0)
                            total = max(status_data.get("total_chunks", 1), 1)
                            progress_bar.progress(0.4 * (completed / total))
                            status_placeholder.caption(
                                f"Extracting entities: {completed}/{total} chunks"
                            )
                            status = status_data.get("status", "pending")
                            if status == "completed":
                                # Wait for relationship extraction and graph
                                while (time.time() - start_time) < EXTRACTION_TIMEOUT_SEC:
                                    success, graph_data, error = api_client.get_extraction_graph(
                                        job_id, token
                                    )
                                    if success and graph_data:
                                        st.session_state.extraction_results = graph_data
                                        st.session_state.extraction_job_id = job_id
                                        extraction_ok = True
                                        progress_bar.progress(1.0)
                                        status_placeholder.caption(
                                            "Entities and relationships ready."
                                        )
                                        break
                                    if not success and error and error != "Graph not ready":
                                        extraction_error_reason = error
                                        break
                                    status_placeholder.caption(
                                        "Extracting relationships..."
                                    )
                                    progress_bar.progress(0.4 + 0.6 * 0.5)
                                    time.sleep(EXTRACTION_POLL_INTERVAL_SEC)
                                if not extraction_ok and extraction_error_reason is None:
                                    extraction_error_reason = (
                                        "Graph extraction timed out after waiting for relationship extraction."
                                    )
                                break  # exit outer poll loop when entity extraction completed
                            if status == "failed":
                                extraction_error_reason = status_data.get(
                                    "error", "Unknown error"
                                )
                                status_placeholder.error(
                                    f"❌ Extraction failed: {extraction_error_reason}"
                                )
                                break
                            time.sleep(EXTRACTION_POLL_INTERVAL_SEC)
                        else:
                            extraction_error_reason = (
                                "Extraction timed out."
                            )
                            status_placeholder.error(
                                "⏱️ Extraction timed out. You can check status later."
                            )
                        progress_bar.empty()
                        status_placeholder.empty()
                        if extraction_ok:
                            st.success(
                                f"✅ Successfully processed **{data.get('filename', uploaded_file.name)}**"
                            )
                        else:
                            st.session_state.extraction_error = (
                                "Couldn't extract the knowledge graph. "
                                + (extraction_error_reason or "Unknown error.")
                            )
                        st.session_state.uploader_key += 1
                        st.rerun()


    # Display current document if any
    current = st.session_state.get("current_pdf")
    if current:
        filename = current.get("filename", "document.pdf")
        content = current.get("content", "")
        st.markdown(f"**Current document:** {filename}")

        if content:
            with st.expander("View extracted text", expanded=True):
                st.text_area(
                    "Content",
                    value=content,
                    height=300,
                    disabled=True,
                    key="pdf_content_display",
                )
        else:
            st.caption("No text could be extracted from this PDF.")

        # Show error when graph extraction failed (no fallback to entity-only)
        if "extraction_error" in st.session_state:
            st.error(st.session_state.extraction_error)
        # Entities and relationships section (graph: nodes + edges)
        elif "extraction_results" in st.session_state:
            _render_entities_with_relationships_section(st.session_state.extraction_results)
            # Save to Knowledge Base (Neo4j) — only when graph is ready and we have job_id
            job_id = st.session_state.get("extraction_job_id")
            saved_to_kb = st.session_state.get("graph_saved_to_kb", False)
            if job_id:
                if saved_to_kb:
                    st.success("✅ Graph saved to Knowledge Base")
                else:
                    if st.button("Add to Knowledge Base", key="save_to_neo4j", help="Save this graph to the persistent Neo4j database"):
                        with st.spinner("Saving graph to Knowledge Base..."):
                            success, save_data, error = api_client.save_graph_to_neo4j(job_id, token)
                        if success:
                            st.session_state.graph_saved_to_kb = True
                            st.success(f"✅ Graph saved to Knowledge Base as **{save_data.get('document_name', filename)}**")
                            st.rerun()
                        else:
                            st.error(f"❌ {error or 'Failed to save graph.'}")

        if st.button("Clear document", key="clear_pdf"):
            success, error = api_client.clear_current_document(token)
            if success:
                if "current_pdf" in st.session_state:
                    del st.session_state.current_pdf
                if "last_processed_file" in st.session_state:
                    del st.session_state.last_processed_file
                if "extraction_results" in st.session_state:
                    del st.session_state.extraction_results
                if "extraction_job_id" in st.session_state:
                    del st.session_state.extraction_job_id
                if "graph_saved_to_kb" in st.session_state:
                    del st.session_state.graph_saved_to_kb
                if "extraction_error" in st.session_state:
                    del st.session_state.extraction_error
                # Increment uploader key to reset the file uploader
                st.session_state.uploader_key += 1
                st.rerun()
            else:
                st.error(error or "Failed to clear document.")
