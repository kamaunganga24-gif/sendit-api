import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

@pytest.fixture
def auth_header():
    """Registers a user/admin, logs in, and returns a valid Authorization header."""
    user_data = {
        "username": "test_sender",
        "email": "sender@sendit.com",
        "password": "SecurePassword123!",
        "full_name": "Test Sender",
        "role": "user"
    }
    # Register user
    client.post("/register", json=user_data)
    
    # Login to retrieve access token
    login_res = client.post(
        "/login", 
        data={"username": user_data["username"], "password": user_data["password"]}
    )
    
    if login_res.status_code == 200:
        token = login_res.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}

    return {}


def test_health_check():
    """Tests the health check endpoint for SendIT API."""
    response = client.get("/health")
    if response.status_code == 404:
        response = client.get("/")
    assert response.status_code == 200


def test_create_parcel_delivery_order(auth_header):
    """Tests creating a new parcel delivery order."""
    parcel_payload = {
        "item_name": "Laptop Charger",
        "weight_kg": 0.5,
        "pickup_location": "Nairobi CBD",
        "destination": "Westlands, Nairobi",
        "recipient_name": "Jane Doe",
        "recipient_phone": "+254700000000"
    }
    response = client.post("/parcels", json=parcel_payload, headers=auth_header)
    assert response.status_code in [200, 201]


def test_get_parcels_list(auth_header):
    """Tests retrieving parcel delivery orders."""
    response = client.get("/parcels", headers=auth_header)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_unauthorized_parcel_access():
    """Accessing parcel routes without authentication should return 401 or 403."""
    response = client.get("/parcels")
    assert response.status_code in [401, 403]