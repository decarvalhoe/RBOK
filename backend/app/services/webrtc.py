"""Domain services for WebRTC signaling sessions."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models import WebRTCSession


class WebRTCSessionStatus(str, Enum):
    """Enumerate the lifecycle of a signaling session."""

    AWAITING_ANSWER = "awaiting_answer"
    ANSWERED = "answered"
    CLOSED = "closed"


class WebRTCSessionService:
    """Facade for manipulating WebRTC signaling sessions."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create_session(
        self,
        *,
        client_id: str,
        offer_sdp: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WebRTCSession:
        session = WebRTCSession(
            client_id=client_id,
            offer_sdp=offer_sdp,
            session_metadata=metadata or {},
            ice_candidates=[],
            status=WebRTCSessionStatus.AWAITING_ANSWER.value,
        )
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        return session

    def get_session(self, session_id: str) -> Optional[WebRTCSession]:
        return self._db.get(WebRTCSession, session_id)

    def attach_answer(
        self,
        session: WebRTCSession,
        *,
        answer_sdp: str,
        responder_id: str,
        responder_metadata: Optional[Dict[str, Any]] = None,
    ) -> WebRTCSession:
        session.answer_sdp = answer_sdp
        session.responder_id = responder_id
        session.responder_metadata = responder_metadata or {}
        session.status = WebRTCSessionStatus.ANSWERED.value
        session.updated_at = datetime.utcnow()
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        return session

    def append_candidate(
        self,
        session: WebRTCSession,
        *,
        candidate: Dict[str, Any],
    ) -> WebRTCSession:
        candidates: List[Dict[str, Any]] = list(session.ice_candidates or [])
        candidates.append(candidate)
        session.ice_candidates = candidates
        session.updated_at = datetime.utcnow()
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        return session

    def close_session(self, session: WebRTCSession) -> WebRTCSession:
        session.status = WebRTCSessionStatus.CLOSED.value
        session.updated_at = datetime.utcnow()
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        return session


__all__ = [
    "WebRTCSessionService",
    "WebRTCSessionStatus",
]
