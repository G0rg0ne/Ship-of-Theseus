"""
API client for communicating with the backend.
"""
import os
import requests
from typing import Tuple, Dict, Optional, List


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

    def upload_pdf(self, file_data: bytes, filename: str, token: str) -> Tuple[bool, Optional[Dict], str]:
        """
        Upload a PDF and get extracted text.

        Args:
            file_data: Raw file bytes
            filename: Original filename
            token: JWT access token

        Returns:
            Tuple of (success, response_data, error_message)
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            files = {"file": (filename, file_data, "application/pdf")}
            response = requests.post(
                f"{self.base_url}/api/documents/upload",
                headers=headers,
                files=files,
                timeout=30,
            )
            if response.status_code == 200:
                return True, response.json(), ""
            data = response.json() if response.text else {}
            detail = data.get("detail", response.text or "Upload failed")
            return False, None, detail if isinstance(detail, str) else str(detail)
        except Exception as e:
            return False, None, str(e)

    def get_current_document(self, token: str) -> Tuple[bool, Optional[Dict], str]:
        """
        Get the currently stored document for the authenticated user.

        Args:
            token: JWT access token

        Returns:
            Tuple of (success, document_data, error_message)
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(
                f"{self.base_url}/api/documents/current",
                headers=headers,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                return True, response.json(), ""
            if response.status_code == 404:
                return False, None, ""
            data = response.json() if response.text else {}
            detail = data.get("detail", response.text or "Request failed")
            return False, None, detail if isinstance(detail, str) else str(detail)
        except Exception as e:
            return False, None, str(e)

    def clear_current_document(self, token: str) -> Tuple[bool, str]:
        """
        Clear the stored document for the authenticated user.

        Args:
            token: JWT access token

        Returns:
            Tuple of (success, error_message)
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.delete(
                f"{self.base_url}/api/documents/current",
                headers=headers,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                return True, ""
            data = response.json() if response.text else {}
            detail = data.get("detail", response.text or "Request failed")
            return False, detail if isinstance(detail, str) else str(detail)
        except Exception as e:
            return False, str(e)

    def start_entity_extraction(self, token: str) -> Tuple[bool, Optional[str], str]:
        """
        Start entity extraction on the user's current document.

        Args:
            token: JWT access token

        Returns:
            Tuple of (success, job_id, error_message). job_id is set only when success is True.
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.post(
                f"{self.base_url}/api/entities/extract",
                headers=headers,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                data = response.json()
                return True, data.get("job_id", ""), ""
            data = response.json() if response.text else {}
            detail = data.get("detail", response.text or "Failed to start extraction")
            return False, None, detail if isinstance(detail, str) else str(detail)
        except Exception as e:
            return False, None, str(e)

    def get_extraction_status(
        self, job_id: str, token: str
    ) -> Tuple[bool, Optional[Dict], str]:
        """
        Get status and progress of an entity extraction job.

        Args:
            job_id: Extraction job ID
            token: JWT access token

        Returns:
            Tuple of (success, status_data, error_message)
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(
                f"{self.base_url}/api/entities/extract/status/{job_id}",
                headers=headers,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                return True, response.json(), ""
            data = response.json() if response.text else {}
            detail = data.get("detail", response.text or "Failed to get status")
            return False, None, detail if isinstance(detail, str) else str(detail)
        except Exception as e:
            return False, None, str(e)

    def get_extraction_result(
        self, job_id: str, token: str
    ) -> Tuple[bool, Optional[Dict], str]:
        """
        Get extraction result when the job is completed.

        Args:
            job_id: Extraction job ID
            token: JWT access token

        Returns:
            Tuple of (success, entities_data, error_message)
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(
                f"{self.base_url}/api/entities/extract/result/{job_id}",
                headers=headers,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                return True, response.json(), ""
            if response.status_code == 202:
                return False, None, "Extraction still in progress"
            data = response.json() if response.text else {}
            detail = data.get("detail", response.text or "Failed to get result")
            return False, None, detail if isinstance(detail, str) else str(detail)
        except Exception as e:
            return False, None, str(e)

    def get_extraction_graph(
        self, job_id: str, token: str
    ) -> Tuple[bool, Optional[Dict], str]:
        """
        Get the complete graph (nodes + edges) for an entity extraction job.
        Returns 202 from backend when relationship extraction is still in progress.

        Args:
            job_id: Entity extraction job ID (same as from start_entity_extraction)
            token: JWT access token

        Returns:
            Tuple of (success, graph_data with nodes/edges, error_message)
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(
                f"{self.base_url}/api/entities/extract/graph/{job_id}",
                headers=headers,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                return True, response.json(), ""
            if response.status_code == 202:
                return False, None, "Graph not ready"
            data = response.json() if response.text else {}
            detail = data.get("detail", response.text or "Failed to get graph")
            return False, None, detail if isinstance(detail, str) else str(detail)
        except Exception as e:
            return False, None, str(e)

    def save_graph_to_neo4j(
        self, job_id: str, token: str
    ) -> Tuple[bool, Optional[Dict], str]:
        """
        Save the extracted graph for the given job to Neo4j (knowledge base).

        Args:
            job_id: Entity extraction job ID
            token: JWT access token

        Returns:
            Tuple of (success, response_data with document_name, error_message)
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.post(
                f"{self.base_url}/api/graph/save/{job_id}",
                headers=headers,
                timeout=30,
            )
            if response.status_code == 200:
                return True, response.json(), ""
            data = response.json() if response.text else {}
            detail = data.get("detail", response.text or "Failed to save graph")
            return False, None, detail if isinstance(detail, str) else str(detail)
        except Exception as e:
            return False, None, str(e)

    def get_graph_from_neo4j(
        self, document_name: str, token: str
    ) -> Tuple[bool, Optional[Dict], str]:
        """
        Get a document graph from Neo4j by document name.

        Args:
            document_name: Document filename as stored in Neo4j
            token: JWT access token

        Returns:
            Tuple of (success, graph_data, error_message)
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(
                f"{self.base_url}/api/graph/{document_name}",
                headers=headers,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                return True, response.json(), ""
            if response.status_code == 404:
                return False, None, "Graph not found"
            data = response.json() if response.text else {}
            detail = data.get("detail", response.text or "Failed to get graph")
            return False, None, detail if isinstance(detail, str) else str(detail)
        except Exception as e:
            return False, None, str(e)

    def list_neo4j_documents(
        self, token: str
    ) -> Tuple[bool, Optional[List[Dict]], str]:
        """
        List all documents stored in Neo4j with node/edge counts.

        Args:
            token: JWT access token

        Returns:
            Tuple of (success, list of {document_name, node_count, edge_count}, error_message)
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(
                f"{self.base_url}/api/graph/list",
                headers=headers,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                data = response.json()
                return True, data.get("documents", []), ""
            data = response.json() if response.text else {}
            detail = data.get("detail", response.text or "Failed to list documents")
            return False, None, detail if isinstance(detail, str) else str(detail)
        except Exception as e:
            return False, None, str(e)

    def delete_graph_from_neo4j(
        self, document_name: str, token: str
    ) -> Tuple[bool, str]:
        """
        Delete a document graph from Neo4j.

        Args:
            document_name: Document filename as stored in Neo4j
            token: JWT access token

        Returns:
            Tuple of (success, error_message)
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.delete(
                f"{self.base_url}/api/graph/{document_name}",
                headers=headers,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                return True, ""
            data = response.json() if response.text else {}
            detail = data.get("detail", response.text or "Failed to delete graph")
            return False, detail if isinstance(detail, str) else str(detail)
        except Exception as e:
            return False, str(e)

