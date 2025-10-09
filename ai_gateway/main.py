#!/usr/bin/env python3
"""AI Gateway application orchestrating ASR, TTS and LLM interactions."""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import logging
from typing import Dict

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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
