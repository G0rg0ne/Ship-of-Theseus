"""
PDF upload and display section for authenticated users.
"""
import time
import streamlit as st
from services.api_client import APIClient

EXTRACTION_POLL_INTERVAL_SEC = 2
EXTRACTION_TIMEOUT_SEC = 300  # 5 minutes


def _aggregate_entities(result_data: dict) -> dict:
    """Aggregate entities from chunk_entities into flat lists (deduped by display string)."""
    chunks = result_data.get("chunk_entities") or []
    people_set = set()
    orgs_set = set()
    locations_set = set()
    dates_set = set()
    key_terms_set = set()
    for chunk in chunks:
        for p in chunk.get("people") or []:
            name = p.get("name", "").strip()
            if name:
                extra = []
                if p.get("role"):
                    extra.append(p["role"])
                if p.get("organization"):
                    extra.append(p["organization"])
                display = f"{name}" + (f" ({', '.join(extra)})" if extra else "")
                people_set.add(display)
        for o in chunk.get("organizations") or []:
            name = o.get("name", "").strip()
            if name:
                extra = []
                if o.get("type"):
                    extra.append(o["type"])
                if o.get("location"):
                    extra.append(o["location"])
                display = f"{name}" + (f" ({', '.join(extra)})" if extra else "")
                orgs_set.add(display)
        for loc in chunk.get("locations") or []:
            if loc and str(loc).strip():
                locations_set.add(str(loc).strip())
        for d in chunk.get("dates") or []:
            text = d.get("text", "").strip()
            if text:
                ctx = d.get("context")
                display = f"{text}" + (f" — {ctx}" if ctx else "")
                dates_set.add(display)
        for term in chunk.get("key_terms") or []:
            if term and str(term).strip():
                key_terms_set.add(str(term).strip())
    return {
        "people": sorted(people_set),
        "organizations": sorted(orgs_set),
        "locations": sorted(locations_set),
        "dates": sorted(dates_set),
        "key_terms": sorted(key_terms_set),
    }


def _render_entities_section(result_data: dict) -> None:
    """Render expandable section with extracted entities by type."""
    aggregated = _aggregate_entities(result_data)
    has_any = any(aggregated[k] for k in aggregated)
    if not has_any:
        return
    with st.expander("📊 Extracted Entities", expanded=True):
        if aggregated["people"]:
            st.markdown("**People**")
            for item in aggregated["people"]:
                st.write(f"- {item}")
        if aggregated["organizations"]:
            st.markdown("**Organizations**")
            for item in aggregated["organizations"]:
                st.write(f"- {item}")
        if aggregated["locations"]:
            st.markdown("**Locations**")
            for item in aggregated["locations"]:
                st.write(f"- {item}")
        if aggregated["dates"]:
            st.markdown("**Dates**")
            for item in aggregated["dates"]:
                st.write(f"- {item}")
        if aggregated["key_terms"]:
            st.markdown("**Key terms**")
            for item in aggregated["key_terms"]:
                st.write(f"- {item}")


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
                            progress_bar.progress(completed / total)
                            status_placeholder.caption(
                                f"Extracting entities: {completed}/{total} chunks"
                            )
                            status = status_data.get("status", "pending")
                            if status == "completed":
                                success, result_data, error = api_client.get_extraction_result(
                                    job_id, token
                                )
                                if success and result_data:
                                    st.session_state.extraction_results = result_data
                                    extraction_ok = True
                                else:
                                    status_placeholder.error(
                                        f"❌ {error or 'Failed to fetch extraction result.'}"
                                    )
                                break
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

        # Extracted entities section (separate expander)
        if "extraction_results" in st.session_state:
            _render_entities_section(st.session_state.extraction_results)

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
