"""
PDF upload and display section for authenticated users.
"""
import streamlit as st
from services.api_client import APIClient


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
                with st.spinner("Uploading and extracting text..."):
                    file_data = uploaded_file.read()
                    success, data, error = api_client.upload_pdf(
                        file_data, uploaded_file.name, token
                    )
                    if success and data:
                        st.session_state.current_pdf = data
                        st.session_state.last_processed_file = file_id
                        # Increment the uploader key to reset the file uploader
                        st.session_state.uploader_key += 1
                        st.success(f"✅ Successfully processed **{data.get('filename', uploaded_file.name)}**")
                        st.rerun()
                    else:
                        st.error(f"❌ {error or 'Upload failed.'}")

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

        if st.button("Clear document", key="clear_pdf"):
            success, error = api_client.clear_current_document(token)
            if success:
                if "current_pdf" in st.session_state:
                    del st.session_state.current_pdf
                if "last_processed_file" in st.session_state:
                    del st.session_state.last_processed_file
                # Increment uploader key to reset the file uploader
                st.session_state.uploader_key += 1
                st.rerun()
            else:
                st.error(error or "Failed to clear document.")
