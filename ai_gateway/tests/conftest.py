from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from collections.abc import Generator
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AI_GATEWAY_OPENAI_API_KEY", "test-key")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_gateway import main
from ai_gateway.clients import (
    BackendClientError,
    ChatCompletionResult,
    SpeechSynthesisResult,
    TranscriptionResult,
)


class DummyOpenAIClient:
    async def transcribe_audio(
        self,
        audio_base64: str,
        audio_format: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        return TranscriptionResult(text="hello world", language=language, confidence=0.9)

    async def synthesize_speech(
        self,
        text: str,
        voice: str | None,
        audio_format: str,
    ) -> SpeechSynthesisResult:
        encoded = base64.b64encode(text.encode()).decode()
        return SpeechSynthesisResult(audio_base64=encoded, audio_format=audio_format, voice=voice)

    async def create_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str | None = None,
        **_: Any,
    ) -> ChatCompletionResult:
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


@pytest.fixture()
def dummy_openai_client() -> DummyOpenAIClient:
    return DummyOpenAIClient()


@pytest.fixture()
def dummy_backend_client() -> DummyBackendClient:
    return DummyBackendClient()


@pytest.fixture()
def client(
    dummy_openai_client: DummyOpenAIClient,
    dummy_backend_client: DummyBackendClient,
) -> Generator[TestClient, None, None]:
    main.app.dependency_overrides[main.get_openai_client] = lambda: dummy_openai_client
    main.app.dependency_overrides[main.get_backend_client] = lambda: dummy_backend_client
    with TestClient(main.app) as http_client:
        yield http_client
    main.app.dependency_overrides.clear()


@pytest.fixture()
def failing_backend_client(
    dummy_openai_client: DummyOpenAIClient,
) -> Generator[TestClient, None, None]:
    class FailingBackend(DummyBackendClient):
        async def get_required_slots(self, procedure_id: str, step_key: str):
            raise BackendClientError("backend down")

    main.app.dependency_overrides[main.get_openai_client] = lambda: dummy_openai_client
    main.app.dependency_overrides[main.get_backend_client] = lambda: FailingBackend()
    with TestClient(main.app) as http_client:
        yield http_client
    main.app.dependency_overrides.clear()
