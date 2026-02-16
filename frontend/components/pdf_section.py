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
                    # Clear previous extraction results for the new document
                    if "extraction_results" in st.session_state:
                        del st.session_state.extraction_results

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
                        while (time.time() - start_time) < EXTRACTION_TIMEOUT_SEC:
                            success, status_data, error = api_client.get_extraction_status(
                                job_id, token
                            )
                            if not success:
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
                                        extraction_ok = True
                                        progress_bar.progress(1.0)
                                        status_placeholder.caption(
                                            "Entities and relationships ready."
                                        )
                                        break
                                    rel_detail = (
                                        getattr(error, "detail", None)
                                        if hasattr(error, "detail")
                                        else error
                                    )
                                    status_placeholder.caption(
                                        "Extracting relationships..."
                                    )
                                    progress_bar.progress(0.4 + 0.6 * 0.5)
                                    time.sleep(EXTRACTION_POLL_INTERVAL_SEC)
                                if not extraction_ok:
                                    # Fallback: try entity-only result if graph never ready
                                    success, result_data, _ = api_client.get_extraction_result(
                                        job_id, token
                                    )
                                    if success and result_data:
                                        # Build minimal graph from entities for display
                                        nodes = []
                                        seen = set()
                                        for chunk in result_data.get("chunk_entities") or []:
                                            for p in chunk.get("people") or []:
                                                name = (p.get("name") or "").strip()
                                                if name and name not in seen:
                                                    seen.add(name)
                                                    nodes.append({
                                                        "id": f"n_{len(nodes)}",
                                                        "label": name,
                                                        "type": "person",
                                                        "properties": {k: v for k, v in p.items() if k != "name" and v},
                                                    })
                                            for o in chunk.get("organizations") or []:
                                                name = (o.get("name") or "").strip()
                                                if name and name not in seen:
                                                    seen.add(name)
                                                    nodes.append({
                                                        "id": f"n_{len(nodes)}",
                                                        "label": name,
                                                        "type": "organization",
                                                        "properties": {k: v for k, v in o.items() if k != "name" and v},
                                                    })
                                            for loc in chunk.get("locations") or []:
                                                name = (str(loc) or "").strip()
                                                if name and name not in seen:
                                                    seen.add(name)
                                                    nodes.append({"id": f"n_{len(nodes)}", "label": name, "type": "location", "properties": {}})
                                            for term in chunk.get("key_terms") or []:
                                                name = (str(term) or "").strip()
                                                if name and name not in seen:
                                                    seen.add(name)
                                                    nodes.append({"id": f"n_{len(nodes)}", "label": name, "type": "key_term", "properties": {}})
                                        st.session_state.extraction_results = {
                                            "nodes": nodes,
                                            "edges": [],
                                            "filename": result_data.get("filename", ""),
                                            "entity_count": len(nodes),
                                            "relationship_count": 0,
                                        }
                                        extraction_ok = True
                                break  # exit outer poll loop when entity extraction completed
                            if status == "failed":
                                status_placeholder.error(
                                    f"❌ Extraction failed: {status_data.get('error', 'Unknown error')}"
                                )
                                break
                            time.sleep(EXTRACTION_POLL_INTERVAL_SEC)
                        else:
                            status_placeholder.error(
                                "⏱️ Extraction timed out. You can check status later."
                            )
                        progress_bar.empty()
                        status_placeholder.empty()
                        if extraction_ok:
                            st.success(
                                f"✅ Successfully processed **{data.get('filename', uploaded_file.name)}**"
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

        # Entities and relationships section (graph: nodes + edges)
        if "extraction_results" in st.session_state:
            _render_entities_with_relationships_section(st.session_state.extraction_results)

        if st.button("Clear document", key="clear_pdf"):
            success, error = api_client.clear_current_document(token)
            if success:
                if "current_pdf" in st.session_state:
                    del st.session_state.current_pdf
                if "last_processed_file" in st.session_state:
                    del st.session_state.last_processed_file
                if "extraction_results" in st.session_state:
                    del st.session_state.extraction_results
                # Increment uploader key to reset the file uploader
                st.session_state.uploader_key += 1
                st.rerun()
            else:
                st.error(error or "Failed to clear document.")
