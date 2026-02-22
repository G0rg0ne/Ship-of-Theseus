"""
Registration form component.
"""
import streamlit as st
from services.api_client import APIClient


def _render_register_form_content() -> None:
    """Render only the registration form fields and actions."""
    st.header("Create account")
    st.caption("Register to access Ship of Theseus.")

    with st.form("register_form"):
        username = st.text_input(
            "Username",
            placeholder="Choose a username",
            max_chars=255,
        )
        email = st.text_input(
            "Email",
            placeholder="your@email.com",
            type="default",
        )
        password = st.text_input(
            "Password",
            type="password",
            placeholder="At least 8 characters",
            max_chars=255,
        )
        password_confirm = st.text_input(
            "Confirm password",
            type="password",
            placeholder="Repeat your password",
            max_chars=255,
        )
        submit = st.form_submit_button("Register", use_container_width=True)

        if submit:
            if not username or not email or not password or not password_confirm:
                st.error("Please fill in all fields")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters")
            elif password != password_confirm:
                st.error("Passwords do not match")
            else:
                api_client = APIClient()
                success, message = api_client.register(username, email, password)
                if success:
                    st.session_state.registration_success_notice = True
                    st.rerun()
                else:
                    st.error(message or "Registration failed")


def render_register_form(centered: bool = True) -> None:
    """Render registration form; optional centering for standalone usage."""
    if centered:
        col_left, col_center, col_right = st.columns([1, 3, 1])
        with col_center:
            _render_register_form_content()
    else:
        _render_register_form_content()
