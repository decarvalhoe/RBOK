from __future__ import annotations

import base64
import os
import pathlib
import sys
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

os.environ.setdefault("AI_GATEWAY_OPENAI_API_KEY", "test-key")

from ai_gateway import main
from ai_gateway.clients import (
    BackendClientError,
    ChatCompletionResult,
    SpeechSynthesisResult,
    TranscriptionResult,
)


class DummyOpenAIClient:
    async def transcribe_audio(self, audio_base64: str, audio_format: str, language: str | None = None) -> TranscriptionResult:
        return TranscriptionResult(text="hello world", language=language, confidence=0.9)

    async def synthesize_speech(self, text: str, voice: str | None, audio_format: str) -> SpeechSynthesisResult:
        encoded = base64.b64encode(text.encode()).decode()
        return SpeechSynthesisResult(audio_base64=encoded, audio_format=audio_format, voice=voice)

    async def create_chat_completion(self, messages: List[Dict[str, str]], model: str | None = None, **_: Any) -> ChatCompletionResult:
        content = f"response to {messages[-1]['content']}"
        return ChatCompletionResult(content=content, model=model or "dummy-model", usage={"total_tokens": 42})


class DummyBackendClient:
    async def get_required_slots(self, procedure_id: str, step_key: str):
        return [
            {"name": "email", "label": "Email", "type": "string", "required": True},
            {"name": "notes", "label": "Notes", "type": "string", "required": False},
        ]

    async def validate_slot(self, procedure_id: str, step_key: str, slot_name: str, value: Any):
        if slot_name == "email" and not value:
            return {"is_valid": False, "reason": "Value is required"}
        return {"is_valid": True, "reason": None}

    async def commit_step(self, run_id: str, step_key: str, slots: Dict[str, Any]):
        return {
            "status": "committed",
            "run_id": run_id,
            "step_key": step_key,
            "slots": slots,
            "run_state": "in_progress",
        }


@pytest.fixture
def client() -> TestClient:
    main.app.dependency_overrides[main.get_openai_client] = lambda: DummyOpenAIClient()
    main.app.dependency_overrides[main.get_backend_client] = lambda: DummyBackendClient()
    with TestClient(main.app) as http_client:
        yield http_client
    main.app.dependency_overrides.clear()


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


def test_backend_error_propagation() -> None:
    class FailingBackend(DummyBackendClient):
        async def get_required_slots(self, procedure_id: str, step_key: str):
            raise BackendClientError("backend down")

    main.app.dependency_overrides[main.get_openai_client] = lambda: DummyOpenAIClient()
    main.app.dependency_overrides[main.get_backend_client] = lambda: FailingBackend()
    with TestClient(main.app) as http_client:
        response = http_client.post(
            "/tools/get_required_slots",
            json={"procedure_id": "p1", "step_key": "s1"},
        )
        assert response.status_code == 502
    main.app.dependency_overrides.clear()
