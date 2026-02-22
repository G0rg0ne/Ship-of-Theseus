"""
Login and registration form component with tab toggle.
"""
import streamlit as st
from services.api_client import APIClient
from components.register_form import render_register_form


def render_login_form():
    """Render the login/register form component with tab toggle."""
    if st.session_state.get("registration_success_notice"):
        st.success("Account created successfully. Please go to the **Sign in** tab above to log in.")
        st.session_state.registration_success_notice = False

    tab_login, tab_register = st.tabs(["Sign in", "Create account"])
    with tab_login:
        st.header("Sign in")
        st.caption("Enter your credentials to access Ship of Theseus.")

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input(
                "Password", type="password", placeholder="Enter your password"
            )
            submit = st.form_submit_button("Sign in", use_container_width=True)

            if submit:
                if username and password:
                    api_client = APIClient()
                    success, token, user_info = api_client.login(username, password)

                    if success:
                        st.session_state.auth_token = token
                        st.session_state.user_info = user_info
                        st.success("Login successful!")
                        st.rerun()
                    else:
                        st.error("Invalid username or password")
                else:
                    st.error("Please fill in all fields")
    with tab_register:
        render_register_form(centered=False)
