"""
Login form component.
"""
import streamlit as st
from services.api_client import APIClient


def render_login_form():
    """Render the login form component."""
    st.header("🔐 Login")
    st.info("Please enter your credentials to access the application.")
    
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
