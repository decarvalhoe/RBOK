#!/usr/bin/env python3
"""AI Gateway application orchestrating ASR, TTS and LLM interactions."""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import logging
import time
from typing import Dict

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from prometheus_client.parser import text_string_to_metric_families

from .clients import (
    BackendClient,
    BackendClientError,
    ChatCompletionResult,
    OpenAIClient,
    OpenAIClientError,
    SpeechSynthesisResult,
    TranscriptionResult,
)
from .config import Settings, get_settings
from .models import (
    AsrRequest,
    AsrResponse,
    CommitStepRequest,
    CommitStepResponse,
    GetRequiredSlotsRequest,
    GetRequiredSlotsResponse,
    LlmRequest,
    LlmResponse,
    TtsRequest,
    TtsResponse,
    ValidateSlotRequest,
    ValidateSlotResponse,
)

logger = logging.getLogger("ai_gateway")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


configure_logging()


app = FastAPI(title="Réalisons AI Gateway", version="0.2.0")
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Metrics -------------------------------------------------------------------

REQUEST_DURATION = Histogram(
    "ai_gateway_request_duration_seconds",
    "Time spent processing requests",
    labelnames=("method", "path", "status_code"),
)
REQUEST_COUNT = Counter(
    "ai_gateway_request_total",
    "Total number of processed requests",
    labelnames=("method", "path", "status_code"),
)
BACKEND_DATABASE_HEALTH = Gauge(
    "ai_gateway_backend_database_up",
    "Database status as reported by the backend service",
)
BACKEND_CACHE_HEALTH = Gauge(
    "ai_gateway_backend_cache_up",
    "Cache status as reported by the backend service",
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):  # type: ignore[override]
    if request.url.path == "/metrics":
        return await call_next(request)

    start_time = time.perf_counter()
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        elapsed = time.perf_counter() - start_time
        labels = {
            "method": request.method,
            "path": request.url.path,
            "status_code": str(status_code),
        }
        REQUEST_DURATION.labels(**labels).observe(elapsed)
        REQUEST_COUNT.labels(**labels).inc()


# Dependency factories -----------------------------------------------------

def get_openai_client(settings: Settings = Depends(get_settings)) -> OpenAIClient:
    return OpenAIClient(
        api_key=settings.openai_api_key,
        chat_model=settings.openai_model,
        asr_model=settings.openai_asr_model,
        tts_model=settings.openai_tts_model,
    )


def get_backend_client(settings: Settings = Depends(get_settings)) -> BackendClient:
    return BackendClient(base_url=settings.backend_base_url)


# Routes -------------------------------------------------------------------



@app.get("/")
async def root() -> Dict[str, str]:
    return {"message": "AI Gateway opérationnel"}


@app.get("/healthz")
async def healthz(settings: Settings = Depends(get_settings)) -> Dict[str, str]:
    """Simple readiness probe for container orchestrators."""

    return {"status": "ok", "openai": "configured" if settings.openai_api_key else "missing"}


@app.post("/asr/transcriptions", response_model=AsrResponse)
async def transcribe_audio(
    payload: AsrRequest,
    openai_client: OpenAIClient = Depends(get_openai_client),
) -> AsrResponse:
    try:
        result: TranscriptionResult = await openai_client.transcribe_audio(
            audio_base64=payload.audio_base64,
            audio_format=payload.audio_format,
            language=payload.language,
        )
    except OpenAIClientError as exc:
        logger.exception("ASR transcription failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AsrResponse(text=result.text, language=result.language, confidence=result.confidence)


@app.post("/tts/speech", response_model=TtsResponse)
async def synthesize_speech(
    payload: TtsRequest,
    openai_client: OpenAIClient = Depends(get_openai_client),
    settings: Settings = Depends(get_settings),
) -> TtsResponse:
    try:
        result: SpeechSynthesisResult = await openai_client.synthesize_speech(
            text=payload.text,
            voice=payload.voice or settings.openai_tts_voice,
            audio_format=payload.audio_format,
        )
    except OpenAIClientError as exc:
        logger.exception("TTS synthesis failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return TtsResponse(
        audio_base64=result.audio_base64,
        audio_format=result.audio_format,
        voice=result.voice or payload.voice or settings.openai_tts_voice,
    )


@app.post("/llm/chat", response_model=LlmResponse)
async def chat_completion(
    payload: LlmRequest,
    openai_client: OpenAIClient = Depends(get_openai_client),
) -> LlmResponse:
    try:
        result: ChatCompletionResult = await openai_client.create_chat_completion(
            messages=[message.model_dump() for message in payload.messages],
            model=payload.model,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
        )
    except OpenAIClientError as exc:
        logger.exception("LLM chat completion failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return LlmResponse(
        content=result.content,
        model=result.model,
        finish_reason=result.finish_reason,
        usage=result.usage,
    )


@app.post("/tools/get_required_slots", response_model=GetRequiredSlotsResponse)
async def get_required_slots(
    payload: GetRequiredSlotsRequest,
    backend_client: BackendClient = Depends(get_backend_client),
) -> GetRequiredSlotsResponse:
    try:
        slots = await backend_client.get_required_slots(
            procedure_id=payload.procedure_id,
            step_key=payload.step_key,
        )
    except BackendClientError as exc:
        logger.exception("Failed to fetch required slots")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return GetRequiredSlotsResponse(slots=slots)


@app.post("/tools/validate_slot", response_model=ValidateSlotResponse)
async def validate_slot(
    payload: ValidateSlotRequest,
    backend_client: BackendClient = Depends(get_backend_client),
) -> ValidateSlotResponse:
    try:
        validation = await backend_client.validate_slot(
            procedure_id=payload.procedure_id,
            step_key=payload.step_key,
            slot_name=payload.slot_name,
            value=payload.value,
        )
    except BackendClientError as exc:
        logger.exception("Slot validation failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ValidateSlotResponse(**validation)


@app.post("/tools/commit_step", response_model=CommitStepResponse)
async def commit_step(
    payload: CommitStepRequest,
    backend_client: BackendClient = Depends(get_backend_client),
) -> CommitStepResponse:
    try:
        acknowledgement = await backend_client.commit_step(
            run_id=payload.run_id,
            step_key=payload.step_key,
            slots=payload.slots,
        )
    except BackendClientError as exc:
        logger.exception("Commit step failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return CommitStepResponse(**acknowledgement)


async def _refresh_backend_dependency_metrics(settings: Settings) -> None:
    """Scrape backend metrics and update gateway dependency gauges."""

    base_url = settings.backend_base_url.rstrip("/")
    if not base_url:
        BACKEND_DATABASE_HEALTH.set(0)
        BACKEND_CACHE_HEALTH.set(0)
        return

    database_status = 0.0
    cache_status = 0.0
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{base_url}/metrics")
            response.raise_for_status()
        for family in text_string_to_metric_families(response.text):
            if family.name == "backend_database_up":
                for sample in family.samples:
                    database_status = float(sample.value)
            elif family.name == "backend_cache_up":
                for sample in family.samples:
                    cache_status = float(sample.value)
    except Exception as exc:  # pragma: no cover - defensive monitoring path
        logger.warning("Failed to refresh backend dependency metrics", exc_info=exc)

    BACKEND_DATABASE_HEALTH.set(database_status)
    BACKEND_CACHE_HEALTH.set(cache_status)


@app.get("/metrics")
async def metrics(settings: Settings = Depends(get_settings)) -> Response:
    await _refresh_backend_dependency_metrics(settings)
    payload = generate_latest()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)
