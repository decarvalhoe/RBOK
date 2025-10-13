from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace

import httpx
import pytest

from ai_gateway.clients import BackendClient, BackendClientError, OpenAIClient
from ai_gateway.telemetry import reset_correlation_id, set_correlation_id


@pytest.mark.asyncio
async def test_openai_client_spans(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OpenAIClient(api_key="test", chat_model="gpt-4o", asr_model="whisper-1", tts_model="gpt-4o-mini")

    class DummyChatCompletions:
        def create(self, **kwargs):
            choice = SimpleNamespace(message=SimpleNamespace(content="bonjour"), finish_reason="stop")
            return SimpleNamespace(choices=[choice], model=kwargs["model"], usage={"total_tokens": 3})

    class DummyTranscriptions:
        def create(self, **kwargs):
            return SimpleNamespace(text="salut")

    class DummySpeechResponse:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def iter_bytes(self):
            yield self._payload

    class DummySpeech:
        def create(self, **kwargs):
            return DummySpeechResponse(b"audio-bytes")

    dummy_openai = SimpleNamespace(
        chat=SimpleNamespace(completions=DummyChatCompletions()),
        audio=SimpleNamespace(transcriptions=DummyTranscriptions(), speech=DummySpeech()),
    )
    client._client = dummy_openai  # type: ignore[attr-defined]

    async def immediate(func, *args, **kwargs):  # pragma: no cover - helper for tests
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", immediate)
    token = set_correlation_id("trace-openai")
    try:
        chat = await client.create_chat_completion([{ "role": "user", "content": "hi" }])
        assert chat.content == "bonjour"
        transcription = await client.transcribe_audio(base64.b64encode(b"sample").decode(), language="fr")
        assert transcription.text == "salut"
        speech = await client.synthesize_speech("bonjour", voice="emma")
        assert base64.b64decode(speech.audio_base64) == b"audio-bytes"
    finally:
        reset_correlation_id(token)


@pytest.mark.asyncio
async def test_backend_client_traced_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_headers: dict[str, str] = {}

    class DummyResponse:
        status_code = 200
        text = "ok"

        def json(self) -> dict[str, str]:
            return {"status": "ok"}

        @property
        def content(self) -> bytes:  # pragma: no cover - compat shim
            return b"{}"

    class DummyAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "DummyAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, method: str, url: str, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return DummyResponse()

    monkeypatch.setattr(httpx, "AsyncClient", DummyAsyncClient)

    client = BackendClient(base_url="http://example.com")
    token = set_correlation_id("trace-backend")
    try:
        payload = await client._request("GET", "/healthz")
    finally:
        reset_correlation_id(token)

    assert payload == {"status": "ok"}
    assert captured_headers.get("X-Correlation-ID") == "trace-backend"


@pytest.mark.asyncio
async def test_backend_client_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "DummyAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, method: str, url: str, **kwargs):
            raise httpx.TimeoutException("boom")

    monkeypatch.setattr(httpx, "AsyncClient", DummyAsyncClient)

    client = BackendClient(base_url="http://example.com")
    with pytest.raises(BackendClientError):
        await client._request("GET", "/slow")
