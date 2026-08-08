import io
import unittest
from fastapi.testclient import TestClient
from main import app


class TestSendITAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Initializes the test client and authenticates a test user."""
        cls.client = TestClient(app)
        cls.auth_headers = {}

    def test_01_health_check(self):
        """Tests the GET /health endpoint."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    def test_02_register_user(self):
        """Tests POST /register."""
        user_data = {
            "username": "doc_user",
            "email": "docuser@sendit.com",
            "full_name": "Doc User",
            "role": "user",
            "password": "SecurePassword123!"
        }
        response = self.client.post("/register", json=user_data)
        self.assertIn(response.status_code, [201, 400])  # 201 created or 400 if already exists

    def test_03_login_user(self):
        """Tests POST /login and extracts JWT token."""
        login_data = {
            "username": "doc_user",
            "password": "SecurePassword123!"
        }
        response = self.client.post("/login", data=login_data)
        self.assertEqual(response.status_code, 200)
        token = response.json().get("access_token")
        self.assertIsNotNone(token)
        
        # Save authorization header for authenticated routes
        TestSendITAPI.auth_headers = {"Authorization": f"Bearer {token}"}

    def test_04_upload_document(self):
        """Tests POST /documents/upload with form data and a mock file."""
        file_content = b"%PDF-1.4 mock pdf content for testing sendit api"
        files = {
            "file": ("invoice.pdf", io.BytesIO(file_content), "application/pdf")
        }
        data = {
            "city": "Nairobi",
            "country": "Kenya",
            "description": "Monthly Financial Report"
        }
        response = self.client.post(
            "/documents/upload",
            files=files,
            data=data,
            headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("document_id", response.json())

    def test_05_list_documents(self):
        """Tests GET /documents for the logged-in user."""
        response = self.client.get("/documents", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_06_search_documents(self):
        """Tests GET /documents/search query parameters."""
        response = self.client.get("/documents/search?q=invoice", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_07_unauthorized_access(self):
        """Tests fetching documents without authentication (expects 401)."""
        response = self.client.get("/documents")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)