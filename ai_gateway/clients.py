"""Wrappers around third-party AI services."""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import httpx
from opentelemetry import trace
from opentelemetry.propagate import inject
from opentelemetry.trace import Status, StatusCode
from openai import OpenAI
from openai import OpenAIError
from structlog.contextvars import get_contextvars

from .telemetry import get_correlation_id

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class OpenAIClientError(RuntimeError):
    """Raised when the OpenAI client fails to fulfil a request."""


@dataclass
class TranscriptionResult:
    """Container for ASR transcription results."""

    text: str
    language: Optional[str] = None
    confidence: Optional[float] = None


@dataclass
class SpeechSynthesisResult:
    """Container for synthesized speech payloads."""

    audio_base64: str
    audio_format: str
    voice: Optional[str] = None


@dataclass
class ChatCompletionResult:
    """Container for chat completion responses."""

    content: str
    model: str
    usage: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None


class OpenAIClient:
    """Simple wrapper around the official OpenAI client."""

    def __init__(
        self,
        api_key: str,
        chat_model: str,
        asr_model: str,
        tts_model: str,
    ) -> None:
        self._client = OpenAI(api_key=api_key)
        self._chat_model = chat_model
        self._asr_model = asr_model
        self._tts_model = tts_model

    async def create_chat_completion(
        self,
        messages: Iterable[Dict[str, str]],
        model: Optional[str] = None,
        **params: Any,
    ) -> ChatCompletionResult:
        """Call the Chat Completions API and normalise the response."""

        def _call() -> ChatCompletionResult:
            try:
                response = self._client.chat.completions.create(
                    model=model or self._chat_model,
                    messages=list(messages),
                    **params,
                )
            except OpenAIError as exc:  # pragma: no cover - defensive
                logger.exception("OpenAI chat completion failed")
                raise OpenAIClientError(str(exc)) from exc

            if not response.choices:
                raise OpenAIClientError("No choices returned by OpenAI chat completion")

            choice = response.choices[0]
            content = getattr(choice.message, "content", None)
            if content is None:
                raise OpenAIClientError("Chat completion did not include content")

            return ChatCompletionResult(
                content=content,
                model=response.model or model or self._chat_model,
                usage=getattr(response, "usage", None),
                finish_reason=getattr(choice, "finish_reason", None),
            )

        span_attributes = {
            "llm.system": "openai",
            "llm.operation": "chat.completion",
            "llm.model": model or self._chat_model,
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            span_attributes["correlation.id"] = correlation_id

        with tracer.start_as_current_span("OpenAI.chatCompletion") as span:
            for key, value in span_attributes.items():
                span.set_attribute(key, value)
            try:
                result = await asyncio.to_thread(_call)
            except OpenAIClientError as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            span.set_status(Status(StatusCode.OK))
            if result.finish_reason:
                span.set_attribute("llm.finish_reason", result.finish_reason)
            if result.usage:
                for usage_key, usage_value in result.usage.items():
                    if isinstance(usage_value, (int, float)):
                        span.set_attribute(f"llm.usage.{usage_key}", usage_value)
            return result

    async def transcribe_audio(
        self,
        audio_base64: str,
        audio_format: str = "wav",
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe audio content using Whisper models."""

        def _call() -> TranscriptionResult:
            try:
                audio_bytes = base64.b64decode(audio_base64)
            except (ValueError, TypeError) as exc:  # pragma: no cover - validated earlier
                raise OpenAIClientError("Invalid base64 audio payload") from exc

            buffer = io.BytesIO(audio_bytes)
            buffer.name = f"audio.{audio_format}"

            try:
                response = self._client.audio.transcriptions.create(
                    model=self._asr_model,
                    file=(buffer.name, buffer, f"audio/{audio_format}"),
                    language=language,
                )
            except OpenAIError as exc:  # pragma: no cover - defensive
                logger.exception("OpenAI transcription failed")
                raise OpenAIClientError(str(exc)) from exc

            text = getattr(response, "text", None)
            if text is None:
                raise OpenAIClientError("Transcription did not return text")

            return TranscriptionResult(text=text, language=language)

        span_attributes = {
            "asr.system": "openai",
            "asr.model": self._asr_model,
            "asr.audio_format": audio_format,
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            span_attributes["correlation.id"] = correlation_id

        with tracer.start_as_current_span("OpenAI.transcription") as span:
            for key, value in span_attributes.items():
                span.set_attribute(key, value)
            try:
                result = await asyncio.to_thread(_call)
            except OpenAIClientError as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            span.set_status(Status(StatusCode.OK))
            return result

    async def synthesize_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        audio_format: str = "mp3",
    ) -> SpeechSynthesisResult:
        """Convert text into speech using the TTS API."""

        def _call() -> SpeechSynthesisResult:
            try:
                response = self._client.audio.speech.create(
                    model=self._tts_model,
                    voice=voice,
                    input=text,
                    response_format=audio_format,
                )
            except OpenAIError as exc:  # pragma: no cover - defensive
                logger.exception("OpenAI speech synthesis failed")
                raise OpenAIClientError(str(exc)) from exc

            audio_bytes: Optional[bytes] = None
            if hasattr(response, "iter_bytes"):
                audio_bytes = b"".join(response.iter_bytes())
            elif hasattr(response, "audio"):
                audio_bytes = response.audio  # type: ignore[attr-defined]

            if not audio_bytes:
                raise OpenAIClientError("Speech synthesis did not return audio bytes")

            encoded = base64.b64encode(audio_bytes).decode("utf-8")

            return SpeechSynthesisResult(
                audio_base64=encoded,
                audio_format=audio_format,
                voice=voice,
            )

        span_attributes = {
            "tts.system": "openai",
            "tts.model": self._tts_model,
            "tts.audio_format": audio_format,
        }
        if voice:
            span_attributes["tts.voice"] = voice
        correlation_id = get_correlation_id()
        if correlation_id:
            span_attributes["correlation.id"] = correlation_id

        with tracer.start_as_current_span("OpenAI.speechSynthesis") as span:
            for key, value in span_attributes.items():
                span.set_attribute(key, value)
            try:
                result = await asyncio.to_thread(_call)
            except OpenAIClientError as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            span.set_status(Status(StatusCode.OK))
            return result


class BackendClientError(RuntimeError):
    """Raised when the procedural backend cannot fulfil a request."""


class BackendClient:
    """Async HTTP client to interact with the procedural backend."""

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = kwargs.pop("headers", {})
        correlation_id = get_contextvars().get("correlation_id")
        if correlation_id and "X-Correlation-ID" not in headers:
            headers["X-Correlation-ID"] = correlation_id

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            logger.exception("Backend request failed: %s %s", method, url)
            raise BackendClientError(str(exc)) from exc

        if response.status_code >= 400:
            logger.error(
                "Backend returned error %s for %s %s: %s",
                response.status_code,
                method,
                url,
                response.text,
            )
            raise BackendClientError(
                f"Backend error {response.status_code}: {response.text}"
            )

            span.set_status(Status(StatusCode.OK))
            return response.json()

    async def get_procedure(self, procedure_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/procedures/{procedure_id}")

    async def get_run(self, run_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/runs/{run_id}")

    async def get_required_slots(self, procedure_id: str, step_key: str) -> List[Dict[str, Any]]:
        procedure = await self.get_procedure(procedure_id)
        for step in procedure.get("steps", []):
            if step.get("key") == step_key:
                return step.get("slots", [])
        raise BackendClientError(
            f"Step '{step_key}' not found in procedure '{procedure_id}'"
        )

    async def validate_slot(
        self,
        procedure_id: str,
        step_key: str,
        slot_name: str,
        value: Any,
    ) -> Dict[str, Any]:
        slots = await self.get_required_slots(procedure_id, step_key)
        slot = next((item for item in slots if item.get("name") == slot_name), None)
        if slot is None:
            raise BackendClientError(
                f"Slot '{slot_name}' not found for step '{step_key}'"
            )

        is_required = slot.get("required", False)
        is_valid = value is not None and (not isinstance(value, str) or value.strip())
        if is_required and not is_valid:
            return {"is_valid": False, "reason": "Value is required"}

        return {"is_valid": True, "reason": None}

    async def commit_step(
        self,
        run_id: str,
        step_key: str,
        slots: Dict[str, Any],
    ) -> Dict[str, Any]:
        run = await self.get_run(run_id)
        return {
            "status": "committed",
            "run_id": run_id,
            "step_key": step_key,
            "slots": slots,
            "run_state": run.get("state"),
        }
