"""Pydantic schemas for procedure endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProcedureStepBase(BaseModel):
    key: str
    title: str
    prompt: str
    slots: List[Dict[str, Any]] = Field(default_factory=list)
    position: Optional[int] = None


class ProcedureStepCreate(ProcedureStepBase):
    pass


class ProcedureStepUpdate(ProcedureStepBase):
    pass


class ProcedureCreate(BaseModel):
    name: str
    description: str
    steps: List[ProcedureStepCreate] = Field(default_factory=list)


class ProcedureUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[List[ProcedureStepUpdate]] = None


class ProcedureStepResponse(ProcedureStepBase):
    id: str
    position: int


class ProcedureResponse(BaseModel):
    id: str
    name: str
    description: str
    steps: List[ProcedureStepResponse]


__all__ = [
    "ProcedureCreate",
    "ProcedureResponse",
    "ProcedureStepCreate",
    "ProcedureStepResponse",
    "ProcedureStepUpdate",
    "ProcedureUpdate",
]
