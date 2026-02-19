"""
Login form component.
"""
import streamlit as st
from services.api_client import APIClient


def render_login_form():
    """Render the login form component, centered with constrained width."""
    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        st.header("Sign in")
        st.caption("Enter your credentials to access Ship of Theseus.")

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submit = st.form_submit_button("Login", use_container_width=True)

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
