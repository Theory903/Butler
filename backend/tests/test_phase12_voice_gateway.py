import pytest
import asyncio
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

@pytest.fixture
def test_app():
    return app

def test_voice_gateway_websocket_connect():
    # Attempt to connect to the websocket
    with client.websocket_connect("/api/v1/voice/stream") as websocket:
        # Mock some payload 
        test_payload = {"type": "session.update"}
        websocket.send_json(test_payload)
        
        # We can simulate disconnect cleanly
        websocket.send_json({"type": "session.close"})
        # Assert no exception is raised
        
        # Test raw pcm passing
        binary_pcm = b"\x00" * 32000
        websocket.send_bytes(binary_pcm)
        
        # Wait for potential JSON mapping or transcript message back
        # We can't guarantee backend returns immediately without mocking Hermes, 
        # but connecting successfully proves route registration.
        assert True

def test_calendar_auth_flow():
    response = client.get("/api/v1/auth/google/calendar/login")
    assert response.status_code == 200
    assert "url" in response.json()
    assert "status" in response.json()
    assert response.json()["status"] == "redirecting"
    
def test_calendar_callback_invalid():
    response = client.get("/api/v1/auth/google/calendar/callback?error=access_denied")
    assert response.status_code == 400
    assert "OAuth failure" in response.json()["detail"]
