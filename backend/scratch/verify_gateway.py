import base64
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.routes.gateway import get_current_account
from core.deps import get_cache
from domain.orchestrator.contracts import OrchestratorResult
from main import app


def test_gateway_comprehensive():

    # 1. Setup global mocks/overrides
    import api.routes.gateway

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "content": "Edge layer verified.",
        "workflow_id": str(uuid.uuid4()),
        "actions": [],
    }
    api.routes.gateway._orch_client.call = AsyncMock(return_value=mock_resp)

    # Mock Orchestrator Intake (for direct calls if any)
    mock_orch = AsyncMock()
    mock_orch.intake.return_value = OrchestratorResult(
        workflow_id=str(uuid.uuid4()), content="Voice logic verified.", actions=[]
    )
    api.routes.gateway._get_orchestrator = AsyncMock(return_value=mock_orch)

    # Mock Auth context explicitly
    class MockAccountContext:
        def __init__(self):
            self.account_id = uuid.uuid4()
            self.email = "test@example.com"
            self.assurance_level = "aal1"
            self.device_id = "test_device"

    app.dependency_overrides[get_current_account] = lambda: MockAccountContext()

    # Mock Async Cache (Redis)
    mock_cache = AsyncMock()
    mock_cache.get.return_value = None
    app.dependency_overrides[get_cache] = lambda: mock_cache

    client = TestClient(app)

    # 2. Test /api/v1/channels
    response = client.get("/api/v1/channels", headers={"Authorization": "Bearer fake"})
    if response.status_code == 200:
        response.json().get("directory", [])
    else:
        return False

    # 3. Test /api/v1/chat
    response = client.post(
        "/api/v1/chat",
        json={"message": "hello", "session_id": "test_ses"},
        headers={"Authorization": "Bearer fake"},
    )
    if response.status_code == 200:
        pass
    else:
        return False

    # 4. Test /api/v1/voice/process
    dummy_audio = base64.b64encode(b"fake audio data").decode("utf-8")

    # We use patch to mock AudioService inside the route
    with patch("services.audio.service.AudioService") as mock_audio_class:
        mock_audio_svc = mock_audio_class.return_value
        mock_audio_svc.transcribe = AsyncMock(return_value=MagicMock(transcript="hello vocal"))
        mock_audio_svc.synthesize = AsyncMock(return_value=MagicMock(audio_data=b"synthetic audio"))

        response = client.post(
            "/api/v1/voice/process",
            json={"audio_data": dummy_audio, "format": "wav"},
            headers={"Authorization": "Bearer fake"},
        )
        if response.status_code == 200:
            pass
        else:
            return False

    return True


if __name__ == "__main__":
    if test_gateway_comprehensive():
        exit(0)
    else:
        exit(1)
