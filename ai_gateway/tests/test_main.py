from __future__ import annotations

import base64

from fastapi.testclient import TestClient


def test_transcription_endpoint(client: TestClient) -> None:
    payload = {
        "audio_base64": base64.b64encode(b"sample").decode(),
        "audio_format": "wav",
        "language": "fr",
    }
    response = client.post("/asr/transcriptions", json=payload)
    assert response.status_code == 200
    assert response.json()["text"] == "hello world"


def test_tts_endpoint(client: TestClient) -> None:
    payload = {"text": "bonjour", "voice": "clarity", "audio_format": "mp3"}
    response = client.post("/tts/speech", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert base64.b64decode(body["audio_base64"]).decode() == "bonjour"
    assert body["voice"] == "clarity"


def test_llm_endpoint(client: TestClient) -> None:
    payload = {
        "messages": [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
    }
    response = client.post("/llm/chat", json=payload)
    assert response.status_code == 200
    assert "response to Hello" in response.json()["content"]


def test_tool_endpoints(client: TestClient) -> None:
    required = client.post(
        "/tools/get_required_slots",
        json={"procedure_id": "p1", "step_key": "s1"},
    )
    assert required.status_code == 200
    assert len(required.json()["slots"]) == 2

    validation = client.post(
        "/tools/validate_slot",
        json={"procedure_id": "p1", "step_key": "s1", "slot_name": "email", "value": ""},
    )
    assert validation.status_code == 200
    assert validation.json() == {"is_valid": False, "reason": "Value is required"}

    commit = client.post(
        "/tools/commit_step",
        json={"run_id": "r1", "step_key": "s1", "slots": {"email": "test@example.com"}},
    )
    assert commit.status_code == 200
    assert commit.json()["status"] == "committed"


def test_backend_error_propagation(failing_backend_client: TestClient) -> None:
    response = failing_backend_client.post(
        "/tools/get_required_slots",
        json={"procedure_id": "p1", "step_key": "s1"},
    )
    assert response.status_code == 502
