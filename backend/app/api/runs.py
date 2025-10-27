"""FastAPI router handling procedure run lifecycle endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..auth import (
    OPAClient,
    User,
    get_current_user,
    get_current_user_optional,
)
from ..auth import (
    get_opa_client as auth_get_opa_client,
)
from ..database import get_db
from ..services.procedure_runs import (
    ChecklistValidationError,
    InvalidTransitionError,
    ProcedureNotFoundError,
    ProcedureRunNotFoundError,
    ProcedureRunService,
    RunSnapshot,
    SlotValidationError,
)
from ..services.procedures.cache import cached_run_detail, invalidate_run_cache

router = APIRouter(prefix="/runs", tags=["procedure runs"])


def get_opa_client() -> Optional[OPAClient]:
    """Expose the OPA client factory for test monkeypatching."""

    return auth_get_opa_client()


def _service(db: Session = Depends(get_db)) -> ProcedureRunService:
    return ProcedureRunService(db)


def _augment_slot_issues(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    formatted: List[Dict[str, Any]] = []
    for issue in issues:
        data = dict(issue)
        slot = data.get("slot") or data.get("field")
        if slot is not None:
            data.setdefault("slot", slot)
        formatted.append(data)
    return formatted


class ProcedureRunCreateRequest(BaseModel):
    """Payload used to initialise a new procedure run."""

    procedure_id: str = Field(..., description="Identifier of the procedure to start")
    user_id: Optional[str] = Field(
        default=None, description="Identifier of the user running the procedure"
    )


class RunChecklistItemPayload(BaseModel):
    """Checklist submission payload for a single item."""

    key: str = Field(..., description="Unique identifier of the checklist item")
    completed: bool = Field(..., description="Whether the item has been completed")
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of completion (defaults to now when omitted)",
    )


class ProcedureRunStepCommitPayload(BaseModel):
    """Payload shared by endpoints committing a run step."""

    slots: Dict[str, Any] = Field(
        default_factory=dict,
        description="Slot values collected for the step",
    )
    checklist: List[RunChecklistItemPayload] = Field(
        default_factory=list,
        description="Checklist state associated with the step",
    )


class ProcedureRunCommitStepRequest(ProcedureRunStepCommitPayload):
    """Payload used when committing a step within a run."""

    step_key: str = Field(..., description="Key of the step to commit")


class RunChecklistItemState(BaseModel):
    key: str
    label: Optional[str] = None
    completed: bool
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ChecklistStatusModel(BaseModel):
    """Public representation of a checklist item status."""

    id: str
    key: str
    label: Optional[str] = None
    completed: bool
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ChecklistProgressModel(BaseModel):
    """Aggregated progression metrics for checklist completion."""

    total: int
    completed: int
    percentage: float


class RunStepStateModel(BaseModel):
    step_key: str
    payload: Dict[str, Any]
    committed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StepCommitResponse(BaseModel):
    """Representation returned when committing a run step."""

    run_state: str = Field(description="Current state of the run after the commit")
    step_state: RunStepStateModel = Field(
        description="State recorded for the committed step"
    )
    checklist_statuses: List[RunChecklistItemState] = Field(
        description="Aggregate checklist status for the run"
    )
    checklist_states: List[RunChecklistItemState] = Field(
        description="Alias exposing checklist statuses for backwards compatibility"
    )


class ProcedureRunModel(BaseModel):
    """Representation returned by run endpoints."""

    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: Optional[datetime]
    step_states: List[RunStepStateModel]
    checklist_states: List[ChecklistStatusModel]
    checklist_statuses: List[ChecklistStatusModel]
    checklist_progress: ChecklistProgressModel

    model_config = ConfigDict(from_attributes=True)


@dataclass
class _ChecklistSnapshot:
    """Resolved state for a checklist item combining definitions and run data."""

    item_id: str
    key: str
    label: Optional[str]
    completed: bool
    completed_at: Optional[datetime]


def _build_checklist_snapshots(snapshot: RunSnapshot) -> List[_ChecklistSnapshot]:
    """Return checklist states for all defined items in the procedure."""

    run = snapshot.run
    states_by_item_id = {
        state.checklist_item_id: state for state in run.checklist_states
    }
    snapshots: List[_ChecklistSnapshot] = []

    procedure = getattr(run, "procedure", None)
    if procedure is not None:
        ordered_steps = sorted(
            procedure.steps,
            key=lambda step: (step.position, step.key),
        )
        for step in ordered_steps:
            ordered_items = sorted(
                step.checklist_items,
                key=lambda item: (item.position, item.key),
            )
            for item in ordered_items:
                state = states_by_item_id.pop(item.id, None)
                snapshots.append(
                    _ChecklistSnapshot(
                        item_id=item.id,
                        key=item.key,
                        label=item.label,
                        completed=state.is_completed if state else False,
                        completed_at=state.completed_at if state else None,
                    )
                )

    if states_by_item_id:
        leftover_states = sorted(
            states_by_item_id.values(),
            key=lambda entry: (
                getattr(entry.checklist_item, "position", 0),
                getattr(entry.checklist_item, "key", entry.checklist_item_id),
            ),
        )
        for state in leftover_states:
            item = getattr(state, "checklist_item", None)
            snapshots.append(
                _ChecklistSnapshot(
                    item_id=getattr(item, "id", state.checklist_item_id),
                    key=getattr(item, "key", state.checklist_item_id),
                    label=getattr(item, "label", None),
                    completed=state.is_completed,
                    completed_at=state.completed_at,
                )
            )

    return snapshots


def _serialize_run(snapshot: RunSnapshot) -> ProcedureRunModel:
    run = snapshot.run
    step_states = [
        RunStepStateModel(
            step_key=state.step_key,
            payload=dict(state.payload or {}),
            committed_at=state.committed_at,
        )
        for state in sorted(snapshot.step_states.values(), key=lambda item: item.committed_at)
    ]
    checklist_snapshots = _build_checklist_snapshots(snapshot)
    checklist_states = [
        ChecklistStatusModel(
            id=snapshot.item_id,
            key=snapshot.key,
            label=snapshot.label,
            completed=snapshot.completed,
            completed_at=snapshot.completed_at,
        )
        for snapshot in checklist_snapshots
    ]
    total_items = len(checklist_states)
    completed_items = sum(1 for status in checklist_states if status.completed)
    percentage = (completed_items / total_items * 100.0) if total_items else 0.0
    checklist_progress = ChecklistProgressModel(
        total=total_items,
        completed=completed_items,
        percentage=percentage,
    )
    return ProcedureRunModel(
        id=run.id,
        procedure_id=run.procedure_id,
        user_id=run.user_id,
        state=run.state,
        created_at=run.created_at,
        closed_at=run.closed_at,
        step_states=step_states,
        checklist_states=checklist_states,
        checklist_statuses=checklist_states,
        checklist_progress=checklist_progress,
    )


def _serialize_checklist_statuses(snapshot: RunSnapshot) -> List[RunChecklistItemState]:
    return [
        RunChecklistItemState(
            key=entry.key,
            label=entry.label,
            completed=entry.completed,
            completed_at=entry.completed_at,
        )
        for entry in _build_checklist_snapshots(snapshot)
    ]


def _serialize_step_commit(snapshot: RunSnapshot, step_key: str) -> StepCommitResponse:
    step_state = snapshot.step_states[step_key]
    checklist_entries = _serialize_checklist_statuses(snapshot)
    return StepCommitResponse(
        run_state=snapshot.run.state,
        step_state=RunStepStateModel(
            step_key=step_state.step_key,
            payload=dict(step_state.payload or {}),
            committed_at=step_state.committed_at,
        ),
        checklist_statuses=checklist_entries,
        checklist_states=checklist_entries,
    )


@router.post("", response_model=ProcedureRunModel, status_code=status.HTTP_201_CREATED)
async def start_run(
    payload: ProcedureRunCreateRequest,
    service: ProcedureRunService = Depends(_service),
    current_user: User = Depends(get_current_user),
) -> ProcedureRunModel:
    """Start a new run for the given procedure."""

    client = get_opa_client()
    if client is not None:
        evaluation = client.evaluate(
            {
                "input": {
                    "subject": {
                        "id": current_user.subject,
                        "username": current_user.username,
                        "roles": list(current_user.roles),
                    },
                    "action": "runs:create",
                    "resource": payload.procedure_id,
                }
            }
        )
        decision = evaluation.get("result")
        allowed = False
        if isinstance(decision, dict):
            allowed = bool(decision.get("allow"))
        elif isinstance(decision, bool):
            allowed = decision
        if not allowed:
            reason = "Access denied by policy"
            status_code = status.HTTP_403_FORBIDDEN
            if isinstance(decision, dict) and decision.get("reason"):
                reason = str(decision["reason"])
                if reason == "not-found":
                    status_code = status.HTTP_404_NOT_FOUND
            raise HTTPException(status_code=status_code, detail=reason)

    user_id = payload.user_id or current_user.subject
    try:
        run = service.start_run(
            procedure_id=payload.procedure_id,
            user_id=user_id,
            actor=current_user.username or current_user.subject,
        )
    except ProcedureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(exc), "procedure_id": exc.procedure_id},
        ) from exc

    snapshot = service.get_snapshot(run.id)
    return _serialize_run(snapshot)


@router.get("/{run_id}", response_model=ProcedureRunModel)
async def get_run(
    run_id: str,
    service: ProcedureRunService = Depends(_service),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> ProcedureRunModel:
    """Return the state of a specific procedure run."""

    try:
        payload = cached_run_detail(
            run_id,
            lambda: _serialize_run(service.get_snapshot(run_id)).model_dump(mode="json"),
        )
    except ProcedureRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(exc), "run_id": exc.run_id},
        ) from exc

    return ProcedureRunModel.model_validate(payload)


@router.post("/{run_id}/commit-step", response_model=ProcedureRunModel)
async def commit_step(
    run_id: str,
    payload: ProcedureRunCommitStepRequest,
    service: ProcedureRunService = Depends(_service),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> ProcedureRunModel:
    """Commit a step payload and advance the run state when appropriate."""

    actor = None
    if current_user is not None:
        actor = current_user.username or current_user.subject

    try:
        snapshot = service.commit_step(
            run_id=run_id,
            step_key=payload.step_key,
            slots=payload.slots,
            checklist=[item.model_dump() for item in payload.checklist],
            actor=actor,
        )
    except ProcedureRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(exc), "run_id": exc.run_id},
        ) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "run_id": exc.run_id},
        ) from exc
    except SlotValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": str(exc), "issues": _augment_slot_issues(exc.issues)},
        ) from exc
    except ChecklistValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": str(exc), "issues": exc.issues},
        ) from exc

    invalidate_run_cache(run_id)
    return _serialize_run(snapshot)


@router.post(
    "/{run_id}/steps/{step_key}/commit",
    response_model=StepCommitResponse,
)
async def commit_step_v2(
    run_id: str,
    step_key: str,
    payload: ProcedureRunStepCommitPayload,
    service: ProcedureRunService = Depends(_service),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> StepCommitResponse:
    """Commit a step payload using the explicit step path structure."""

    actor = None
    if current_user is not None:
        actor = current_user.username or current_user.subject

    try:
        snapshot = service.commit_step(
            run_id=run_id,
            step_key=step_key,
            slots=payload.slots,
            checklist=[item.model_dump() for item in payload.checklist],
            actor=actor,
        )
    except ProcedureRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(exc), "run_id": exc.run_id},
        ) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "run_id": exc.run_id},
        ) from exc
    except SlotValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "issues": _augment_slot_issues(exc.issues)},
        ) from exc
    except ChecklistValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "issues": exc.issues},
        ) from exc

    return _serialize_step_commit(snapshot, step_key)

