"""Pydantic schemas for procedure run endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProcedureRunCreate(BaseModel):
    procedure_id: str
    user_id: str
    state: str = "pending"


class ProcedureRunResponse(BaseModel):
    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: str
    closed_at: Optional[str]
    procedure: Optional[Dict[str, Any]] = None
    step_states: List[Dict[str, Any]]


class ProcedureRunStepCommit(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ProcedureRunCreate",
    "ProcedureRunResponse",
    "ProcedureRunStepCommit",
]
