# /tests/test_api.py

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
from pathlib import Path


MINIMAX_BASE_URL = "https://api.minimax.io/v1"

@pytest.fixture
def mock_audio_file(tmp_path: Path) -> Path:
    """Create a dummy audio file for testing uploads."""
    file_path = tmp_path / "test_audio.mp3"
    file_path.write_bytes(b"dummy audio content")
    return file_path

@respx.mock
def test_clone_and_generate_success(test_client: TestClient, mock_audio_file: Path):
    """
    Test the full automated workflow: clone a voice and generate speech.
    This test mocks all external API calls to MiniMax.
    """
   
    # 1. Mock the file upload endpoint
    upload_route = respx.post(f"{MINIMAX_BASE_URL}/files/upload").mock(
        return_value=Response(
            200,
            json={
                "file": {"file_id": "file12345"},
                "base_resp": {"status_code": 0, "status_msg": "success"}
            }
        )
    )

    # 2. Mock the voice clone endpoint
    clone_route = respx.post(f"{MINIMAX_BASE_URL}/voice_clone").mock(
        return_value=Response(
            200,
            json={
                "voice_id": "MyAutomatedVoice",
                "base_resp": {"status_code": 0, "status_msg": "success"}
            }
        )
    )

    # 3. Mock the TTS endpoint
    mock_audio_hex = "0102030405" # Dummy hex string for audio
    tts_route = respx.post(f"{MINIMAX_BASE_URL}/t2a_v2").mock(
        return_value=Response(
            200,
            json={
                "data": {"audio": mock_audio_hex},
                "base_resp": {"status_code": 0, "status_msg": "success"}
            }
        )
    )

    # Prepare form data and file for the request
    form_data = {
        "text": "This is a test of the automated workflow.",
        "new_voice_id": "MyAutomatedVoice"
    }
    with open(mock_audio_file, "rb") as f:
        files = {"audio_file": (mock_audio_file.name, f, "audio/mpeg")}
        
        # Make the API call to our service
        response = test_client.post(
            "/api/v1/voice/clone-and-generate",
            data=form_data,
            files=files
        )

    # Assertions
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == bytes.fromhex(mock_audio_hex)
    
    # Verify that all mocked API endpoints were called
    assert upload_route.called
    assert clone_route.called
    assert tts_route.called

def test_health_check(test_client: TestClient):
    """Test the health check endpoint."""
    response = test_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service_name"] == "MiniMax TTS and Voice Cloning API"
    assert "minimax_tts" in data["services"]
    assert data["services"]["minimax_tts"]["initialized"] is True