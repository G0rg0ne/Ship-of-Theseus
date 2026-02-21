"""
PDF upload and display section for authenticated users.
"""
import json
import time
from collections import Counter
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

# Entity type → (emoji, CSS color) for knowledge graph cards
ENTITY_STYLE = {
    "person": ("👤", "#4285F4"),
    "organization": ("🏢", "#34A853"),
    "location": ("📍", "#FBBC04"),
    "key_term": ("🔑", "#9334E6"),
    "other": ("•", "#5F6368"),
}


_TYPE_ALIASES: dict[str, str] = {
    # Neo4j label round-trips: _type_to_label strips underscores, so restore them
    "keyterm": "key_term",
    "keyphrase": "key_term",
    "key phrase": "key_term",
    "entity": "other",
}


def _entity_icon_and_color(node_type: str) -> tuple[str, str]:
    """Return (emoji, hex color) for an entity type.

    Normalises the type string so Neo4j label round-trips (e.g. 'keyterm' from
    the stored label 'Keyterm') still resolve to the correct style entry.
    """
    t = (node_type or "other").strip().lower().replace(" ", "_").replace("-", "_")
    t = _TYPE_ALIASES.get(t, t)
    return ENTITY_STYLE.get(t, ENTITY_STYLE["other"])


def _clear_processing_state():
    """Clear processing-related session state."""
    for key in ("processing_state", "processing_job_id", "processing_progress"):
        if key in st.session_state:
            del st.session_state[key]


def _escape_html(s: str) -> str:
    """Escape HTML for safe display."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _render_knowledge_graph_section(graph_data: dict, key_prefix: str = "") -> None:
    """Render knowledge graph with explorer toolbar, filters, sort, and cards (context in expanders)."""
    nodes = graph_data.get("nodes") or []
    edges = graph_data.get("edges") or []
    if not nodes and not edges:
        return

    k = key_prefix or "kg"
    id_to_node = {n.get("id"): n for n in nodes}

    # Build enriched edge list for filtering/sorting
    edge_rows = []
    for i, e in enumerate(edges):
        src = id_to_node.get(e.get("source"), {})
        tgt = id_to_node.get(e.get("target"), {})
        src_type = (src.get("type") or "other").lower().replace(" ", "_")
        tgt_type = (tgt.get("type") or "other").lower().replace(" ", "_")
        src_label = src.get("label") or e.get("source") or "?"
        tgt_label = tgt.get("label") or e.get("target") or "?"
        rel = e.get("relation_type") or "related_to"
        props = e.get("properties") or {}
        ctx = props.get("context", "")
        edge_rows.append({
            "idx": i,
            "src_label": src_label,
            "tgt_label": tgt_label,
            "src_type": src_type,
            "tgt_type": tgt_type,
            "rel": rel,
            "context": ctx,
            "source": e.get("source"),
            "target": e.get("target"),
        })

    # Unique types and relation types for filters
    entity_types = sorted(set(r["src_type"] for r in edge_rows) | set(r["tgt_type"] for r in edge_rows))
    rel_types = sorted(set(r["rel"] for r in edge_rows))

    # Summary metrics and Download JSON
    st.markdown("### Knowledge graph")
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
    with col1:
        st.metric("Entities", len(nodes))
    with col2:
        st.metric("Relationships", len(edges))
    with col3:
        st.metric("Document", "Processed")
    with col4:
        st.download_button(
            "Download graph JSON",
            data=json.dumps(graph_data, indent=2),
            file_name="knowledge_graph.json",
            mime="application/json",
            key=f"{k}_download_kg_json",
        )
    st.markdown("---")

    if not edges:
        st.info("No relationships extracted. Entities were found but no links between them.")
        # Entities-only tab
        _render_entities_tab(nodes)
        return

    # Explore toolbar: search, filters, sort
    st.markdown("**Explore**")
    tb1, tb2, tb3, tb4 = st.columns([2, 1, 1, 1])
    with tb1:
        search_query = st.text_input("Search", placeholder="Entity, relationship, or context...", key=f"{k}_search")
    with tb2:
        filter_entity_type = st.multiselect("Entity type", options=entity_types, default=[], key=f"{k}_filter_entity")
    with tb3:
        filter_rel_type = st.multiselect("Relationship type", options=rel_types, default=[], key=f"{k}_filter_rel")
    with tb4:
        sort_by = st.selectbox(
            "Sort by",
            options=["Original", "Source entity", "Relationship type"],
            key=f"{k}_sort",
        )

    # Apply search (case-insensitive match on labels, rel, context)
    q = (search_query or "").strip().lower()
    if q:
        def matches(row):
            return (
                q in row["src_label"].lower()
                or q in row["tgt_label"].lower()
                or q in row["rel"].lower()
                or q in row["context"].lower()
            )
        edge_rows = [r for r in edge_rows if matches(r)]
    if filter_entity_type:
        edge_rows = [
            r for r in edge_rows
            if r["src_type"] in filter_entity_type or r["tgt_type"] in filter_entity_type
        ]
    if filter_rel_type:
        edge_rows = [r for r in edge_rows if r["rel"] in filter_rel_type]
    if sort_by == "Source entity":
        edge_rows = sorted(edge_rows, key=lambda r: (r["src_label"].lower(), r["rel"]))
    elif sort_by == "Relationship type":
        edge_rows = sorted(edge_rows, key=lambda r: (r["rel"].lower(), r["src_label"].lower()))

    # Tabs: Relationships (cards) and Entities
    tab_rel, tab_ent = st.tabs(["Relationships", "Entities"])
    with tab_rel:
        st.caption("Entity → Relationship → Entity")
        for i, row in enumerate(edge_rows):
            src_icon, src_color = _entity_icon_and_color(row["src_type"])
            tgt_icon, tgt_color = _entity_icon_and_color(row["tgt_type"])
            src_label_esc = _escape_html(row["src_label"])
            tgt_label_esc = _escape_html(row["tgt_label"])
            rel_esc = _escape_html(row["rel"])
            context_esc = _escape_html(row["context"])
            # Build as a compact single-line string: Streamlit's Markdown parser treats
            # 4-space-indented lines as code blocks, so any newlines inside the HTML
            # would cause inner divs to render as raw text instead of HTML.
            context_part = f'<div class="kg-context">{context_esc}</div>' if context_esc else ""
            card_html = (
                f'<div class="kg-card">'
                f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:0.5rem 0.75rem;width:100%;">'
                f'<span class="kg-entity" style="color:{src_color};">{src_icon} {src_label_esc}</span>'
                f'<span class="kg-arrow">→</span>'
                f'<span class="kg-rel">{rel_esc}</span>'
                f'<span class="kg-arrow">→</span>'
                f'<span class="kg-entity" style="color:{tgt_color};">{tgt_icon} {tgt_label_esc}</span>'
                f'</div>'
                f'{context_part}'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)
    with tab_ent:
        _render_entities_tab(nodes, key_suffix=f"{k}_tab")
    st.markdown("---")
    return


def _render_entities_tab(nodes: list, key_suffix: str = "") -> None:
    """Render entities list by type with optional search."""
    if not nodes:
        st.info("No entities.")
        return
    type_counts = Counter((n.get("type") or "other").lower().replace(" ", "_") for n in nodes)
    entity_search = st.text_input("Search entities", key=f"entity_search_{key_suffix}", placeholder="Filter by label...")
    q = (entity_search or "").strip().lower()
    for etype in sorted(type_counts.keys()):
        count = type_counts[etype]
        icon, color = _entity_icon_and_color(etype)
        label = etype.replace("_", " ").title()
        with st.expander(f"{icon} {label} ({count})", expanded=False):
            subset = [n for n in nodes if (n.get("type") or "other").lower().replace(" ", "_") == etype]
            if q:
                subset = [n for n in subset if q in (n.get("label") or "").lower()]
            for n in subset:
                st.caption(n.get("label") or n.get("id") or "?")


def _run_extraction_poll_loop(api_client: APIClient, job_id: str, token: str) -> tuple[bool, str | None]:
    """Poll extraction status until done or timeout. Returns (success, error_message)."""
    start_time = time.time()
    extraction_error_reason = None
    while (time.time() - start_time) < EXTRACTION_TIMEOUT_SEC:
        success, status_data, error = api_client.get_extraction_status(job_id, token)
        if not success:
            return False, error or "Status check failed"
        completed = status_data.get("completed_chunks", 0)
        total = max(status_data.get("total_chunks", 1), 1)
        st.session_state.processing_progress = {
            "completed": completed,
            "total": total,
            "message": f"Extracting entities: {completed}/{total} chunks",
        }
        status = status_data.get("status", "pending")
        if status == "completed":
            while (time.time() - start_time) < EXTRACTION_TIMEOUT_SEC:
                success, graph_data, error = api_client.get_extraction_graph(job_id, token)
                if success and graph_data:
                    st.session_state.extraction_results = graph_data
                    st.session_state.extraction_job_id = job_id
                    _clear_processing_state()
                    st.session_state.processing_state = PROCESSING_DONE
                    return True, None
                if not success and error and error != "Graph not ready":
                    extraction_error_reason = error
                    break
                time.sleep(EXTRACTION_POLL_INTERVAL_SEC)
            if extraction_error_reason is None:
                extraction_error_reason = "Graph extraction timed out."
            break
        if status == "failed":
            extraction_error_reason = status_data.get("error", "Unknown error")
            break
        time.sleep(EXTRACTION_POLL_INTERVAL_SEC)
    else:
        extraction_error_reason = "Extraction timed out."
    _clear_processing_state()
    st.session_state.processing_state = PROCESSING_ERROR
    return False, extraction_error_reason


def render_pdf_section():
    """Render the PDF upload section and display extracted content."""
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

    # ----- Upload card: single primary area -----
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
                            st.session_state.processing_progress = {"completed": 0, "total": 1, "message": "Starting..."}
                            st.rerun()

    # ----- Show processing status and run poll loop when in progress -----
    if st.session_state.processing_state in (PROCESSING_ENTITIES, PROCESSING_RELATIONSHIPS):
        job_id = st.session_state.get("processing_job_id")
        if job_id:
            progress = st.session_state.get("processing_progress") or {}
            msg = progress.get("message", "Processing...")
            with st.status(msg, expanded=True) as status:
                st.caption(msg)
                completed = progress.get("completed", 0)
                total = max(progress.get("total", 1), 1)
                p = 0.4 * (completed / total) if st.session_state.processing_state == PROCESSING_ENTITIES else 0.7
                st.progress(p)
                ok, err = _run_extraction_poll_loop(api_client, job_id, token)
                if ok:
                    status.update(label="Done", state="complete")
                    st.success("Entities and relationships ready.")
                else:
                    status.update(label="Error", state="error")
                    st.session_state.extraction_error = (
                        "Couldn't extract the knowledge graph. " + (err or "Unknown error.")
                    )
                    st.error(err or "Unknown error.")
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
                st.rerun()
        elif "extraction_results" in st.session_state:
            _render_knowledge_graph_section(st.session_state.extraction_results)
            job_id = st.session_state.get("extraction_job_id")
            saved_to_kb = st.session_state.get("graph_saved_to_kb", False)
            if job_id:
                if saved_to_kb:
                    st.success("Graph saved to Knowledge Base")
                else:
                    if st.button("Add to Knowledge Base", key="save_to_neo4j", help="Save this graph to the persistent Neo4j database"):
                        with st.spinner("Saving graph to Knowledge Base..."):
                            success, save_data, error = api_client.save_graph_to_neo4j(job_id, token)
                        if success:
                            st.session_state.graph_saved_to_kb = True
                            st.success(f"Graph saved to Knowledge Base as **{save_data.get('document_name', filename)}**")
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

    # ----- Knowledge Base: browse saved graphs (collapsible) -----
    # Note: Streamlit forbids nesting expanders; the graph explorer uses expanders (Context + Entities),
    # so we implement KB "collapsible" as a toggle instead of an outer expander.
    show_kb = st.toggle("Knowledge Base — browse saved graphs", value=False, key="kb_show_toggle")
    if show_kb:
        success, doc_list, error = api_client.list_neo4j_documents(token)
        if not success or doc_list is None:
            st.caption("Could not load saved documents." if not error else error)
        elif not doc_list:
            st.caption("No saved graphs yet. Process a document and use **Add to Knowledge Base** to save one.")
        else:
            doc_names = [d.get("document_name") or d.get("name", "?") for d in doc_list]
            selected = st.selectbox(
                "Select a saved document",
                options=doc_names,
                key="kb_doc_select",
            )
            if st.button("Load graph", key="kb_load_btn"):
                with st.spinner("Loading..."):
                    ok, graph_data, load_err = api_client.get_graph_from_neo4j(selected, token)
                if ok and graph_data:
                    st.session_state.kb_loaded_graph = graph_data
                    st.session_state.kb_loaded_name = selected
                    st.rerun()
                else:
                    st.error(load_err or "Failed to load graph.")
            if st.session_state.get("kb_loaded_graph"):
                st.markdown(f"**{st.session_state.get('kb_loaded_name', 'Graph')}**")
                _render_knowledge_graph_section(st.session_state.kb_loaded_graph, key_prefix="kb")
