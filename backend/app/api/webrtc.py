"""FastAPI router exposing WebRTC signaling endpoints."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import WebRTCSession
from ..services.webrtc import WebRTCSessionService

router = APIRouter(prefix="/webrtc", tags=["webrtc"])


class IceServerResponse(BaseModel):
    urls: List[str]
    username: Optional[str] = None
    credential: Optional[str] = None


class WebRTCConfigResponse(BaseModel):
    ice_servers: List[IceServerResponse]


class WebRTCSessionCreateRequest(BaseModel):
    client_id: str = Field(..., max_length=255)
    offer_sdp: str = Field(..., description="SDP offer from the initiating peer")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WebRTCSessionResponse(BaseModel):
    id: str
    client_id: str
    responder_id: Optional[str]
    status: str
    offer_sdp: str
    answer_sdp: Optional[str]
    metadata: Dict[str, Any]
    responder_metadata: Dict[str, Any]
    ice_candidates: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebRTCSessionAnswerRequest(BaseModel):
    responder_id: str = Field(..., max_length=255)
    answer_sdp: str = Field(..., description="SDP answer from the responding peer")
    responder_metadata: Dict[str, Any] = Field(default_factory=dict)


class WebRTCSessionCandidateRequest(BaseModel):
    candidate: Dict[str, Any]


def _service(db: Session = Depends(get_db)) -> WebRTCSessionService:
    return WebRTCSessionService(db)


def _to_response(session: WebRTCSession) -> WebRTCSessionResponse:
    return WebRTCSessionResponse(
        id=session.id,
        client_id=session.client_id,
        responder_id=session.responder_id,
        status=session.status,
        offer_sdp=session.offer_sdp,
        answer_sdp=session.answer_sdp,
        metadata=session.session_metadata,
        responder_metadata=session.responder_metadata,
        ice_candidates=session.ice_candidates,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _split_env_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@router.get("/config", response_model=WebRTCConfigResponse)
async def get_webrtc_config() -> WebRTCConfigResponse:
    """Expose sanitized ICE server configuration for clients."""

    stun_servers = _split_env_list(os.getenv("WEBRTC_STUN_SERVERS"))
    turn_servers = _split_env_list(os.getenv("WEBRTC_TURN_SERVERS"))
    turn_username = os.getenv("WEBRTC_TURN_USERNAME") or None
    turn_password = os.getenv("WEBRTC_TURN_PASSWORD") or None

    ice_servers: List[IceServerResponse] = []

    if stun_servers:
        ice_servers.append(IceServerResponse(urls=stun_servers))

    if turn_servers:
        ice_servers.append(
            IceServerResponse(
                urls=turn_servers,
                username=turn_username,
                credential=turn_password,
            )
        )

    return WebRTCConfigResponse(ice_servers=ice_servers)


@router.post("/sessions", response_model=WebRTCSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: WebRTCSessionCreateRequest,
    service: WebRTCSessionService = Depends(_service),
) -> WebRTCSessionResponse:
    session = service.create_session(
        client_id=payload.client_id,
        offer_sdp=payload.offer_sdp,
        metadata=payload.metadata,
    )
    return _to_response(session)


@router.get("/sessions/{session_id}", response_model=WebRTCSessionResponse)
async def get_session(
    session_id: str,
    service: WebRTCSessionService = Depends(_service),
) -> WebRTCSessionResponse:
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return _to_response(session)


@router.post("/sessions/{session_id}/answer", response_model=WebRTCSessionResponse)
async def submit_answer(
    session_id: str,
    payload: WebRTCSessionAnswerRequest,
    service: WebRTCSessionService = Depends(_service),
) -> WebRTCSessionResponse:
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    updated = service.attach_answer(
        session,
        answer_sdp=payload.answer_sdp,
        responder_id=payload.responder_id,
        responder_metadata=payload.responder_metadata,
    )
    return _to_response(updated)


@router.post("/sessions/{session_id}/candidates", response_model=WebRTCSessionResponse)
async def submit_candidate(
    session_id: str,
    payload: WebRTCSessionCandidateRequest,
    service: WebRTCSessionService = Depends(_service),
) -> WebRTCSessionResponse:
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    updated = service.append_candidate(session, candidate=payload.candidate)
    return _to_response(updated)


@router.post("/sessions/{session_id}/close", response_model=WebRTCSessionResponse)
async def close_session(
    session_id: str,
    service: WebRTCSessionService = Depends(_service),
) -> WebRTCSessionResponse:
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    updated = service.close_session(session)
    return _to_response(updated)
