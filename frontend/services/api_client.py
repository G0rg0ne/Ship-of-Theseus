"""
API client for communicating with the backend.
"""
import os
import requests
from typing import Tuple, Dict


class APIClient:
    """Client for backend API communication."""
    
    def __init__(self):
        self.base_url = os.getenv("API_BASE_URL", "http://backend:8000")
        self.timeout = 5
    
    def login(self, username: str, password: str) -> Tuple[bool, str, Dict]:
        """
        Attempt to login user.
        
        Args:
            username: User's username
            password: User's password
            
        Returns:
            Tuple of (success, token, user_info)
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"username": username, "password": password},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                token = data["access_token"]
                
                # Get user info
                user_info = self.get_user_info(token)
                if user_info:
                    return True, token, user_info
            
            return False, "", {}
        except Exception as e:
            print(f"Login error: {str(e)}")
            return False, "", {}
    
    def get_user_info(self, token: str) -> Dict:
        """
        Get current user information.
        
        Args:
            token: JWT access token
            
        Returns:
            User information dict or empty dict on failure
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(
                f"{self.base_url}/api/auth/me",
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            print(f"Get user info error: {str(e)}")
            return {}
    
    def verify_token(self, token: str) -> bool:
        """
        Verify token with backend API.
        
        Args:
            token: JWT access token
            
        Returns:
            True if token is valid, False otherwise
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(
                f"{self.base_url}/api/auth/verify",
                headers=headers,
                timeout=self.timeout
            )
            return response.status_code == 200
        except Exception:
            return False
