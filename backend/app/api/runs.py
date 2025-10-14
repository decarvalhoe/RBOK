"""Procedure run management endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
"""FastAPI router for procedure run lifecycle management."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import models
from app.auth import User, get_current_user, get_opa_client
from app.database import get_db
from app.services.procedures import ProcedureFSM
from app.services.procedures.exceptions import (
    ChecklistValidationError,
    InvalidTransitionError,
    SlotValidationError,
    StepNotFoundError,
    StepOrderError,
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


router = APIRouter(prefix="/runs", tags=["procedure runs"])


def _service(db: Session = Depends(get_db)) -> ProcedureRunService:
    return ProcedureRunService(db)


class ProcedureRunCreateRequest(BaseModel):
    procedure_id: str = Field(..., description="Identifier of the procedure to start")
    user_id: Optional[str] = Field(
        default=None, description="Identifier of the user running the procedure"
    )


class RunChecklistItemPayload(BaseModel):
    key: str = Field(..., description="Unique identifier of the checklist item")
    label: Optional[str] = Field(
        default=None, description="Human-readable label for the checklist item"
    )
    completed: bool = Field(..., description="Whether the item has been completed")
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of completion (defaults to now when omitted)",
    )


class ProcedureRunCommitStepRequest(BaseModel):
    step_key: str = Field(..., description="Key of the step to commit")
    slots: Dict[str, Any] = Field(
        default_factory=dict,
        description="Slot values collected for the step",
    )
    checklist: List[RunChecklistItemPayload] = Field(
        default_factory=list,
        description="Checklist state associated with the step",
    )


class RunChecklistItemState(BaseModel):
    key: str
    label: Optional[str] = None
    completed: bool
    completed_at: Optional[datetime] = None


class ProcedureRunStepStateResponse(BaseModel):
    key: str
    title: str
    prompt: str
    status: str
    collected_slots: Dict[str, Any]
    checklist: List[RunChecklistItemState]
    committed_at: Optional[datetime] = None


class ProcedureRunDetailResponse(BaseModel):
from ..models import ProcedureRun, ProcedureRunChecklistStatus
from ..services.procedures import (
    ChecklistIncompleteError,
    InvalidChecklistItemError,
    ProcedureRunNotFoundError,
    ProcedureRunService,
    ProcedureStepNotFoundError,
)

router = APIRouter(prefix="/runs", tags=["procedure-runs"])


class RunCreate(BaseModel):
    procedure_id: str
    user_id: Optional[str] = None


class RunResponse(BaseModel):
class ChecklistUpdateModel(BaseModel):
    completed_item_ids: List[str] = Field(default_factory=list)


class CommitStepRequest(BaseModel):
    step_key: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)
    checklist: ChecklistUpdateModel | None = None


class RunStepStateModel(BaseModel):
    step_key: str
    payload: Dict[str, Any]
    committed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunChecklistStatusModel(BaseModel):
    checklist_item_id: str
    step_key: str
    item_key: str
    item_label: str
    completed: bool
    completed_at: datetime | None = None


class ProcedureRunModel(BaseModel):
    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: datetime | None
    closed_at: Optional[datetime]
    current_step: Optional[str]
    steps: List[ProcedureRunStepStateResponse]
    closed_at: datetime | None = None
    step_states: List[RunStepStateModel]
    checklist_statuses: List[RunChecklistStatusModel]

    model_config = ConfigDict(from_attributes=True)


class RunStepPayload(BaseModel):
    slots: Dict[str, Any] = Field(default_factory=dict)
    checklist: List[Dict[str, Any]] | Dict[str, Any] | None = None


class RunStepResponse(BaseModel):
    id: str
    run_id: str
    step_key: str
    payload: Dict[str, Any]
    committed_at: datetime
    run_state: str

    model_config = ConfigDict(from_attributes=True)


def _evaluate_policy(user: User, action: str, resource: Optional[str]) -> None:
    client = get_opa_client()
    if client is None:
        return
    evaluation = client.evaluate(
        {
            "input": {
                "subject": {
                    "id": user.subject,
                    "username": user.username,
                    "roles": list(user.roles),
                },
                "action": action,
                "resource": resource,
            }
        }
    )
    decision = evaluation.get("result")
    allowed = False
    if isinstance(decision, dict):
        allowed = bool(decision.get("allow", False))
    elif isinstance(decision, bool):
        allowed = decision
    if not allowed:
        reason = None
        if isinstance(decision, dict):
            reason = decision.get("reason")
        detail = str(reason) if reason else "Access denied by policy"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: RunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunResponse:
    procedure = db.get(models.Procedure, payload.procedure_id)
    if procedure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")

    _evaluate_policy(current_user, "runs:create", procedure.id)

    run = models.ProcedureRun(
        procedure_id=procedure.id,
        user_id=payload.user_id or current_user.subject,
def _parse_timestamp(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    value = raw
    if raw.endswith("Z"):
        value = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _build_response(snapshot: RunSnapshot) -> ProcedureRunDetailResponse:
    run = snapshot.run
    procedure_steps = sorted(run.procedure.steps, key=lambda step: step.position)
    pending_steps = [step for step in procedure_steps if step.key not in snapshot.step_states]
    current_step_key = pending_steps[0].key if pending_steps else None

    responses: List[ProcedureRunStepStateResponse] = []
    for step in procedure_steps:
        state = snapshot.step_states.get(step.key)
        if state:
            payload = state.payload or {}
            slots = payload.get("slots") or {}
            raw_checklist = payload.get("checklist") or []
            checklist_items = [
                RunChecklistItemState(
                    key=item.get("key", ""),
                    label=item.get("label"),
                    completed=bool(item.get("completed", False)),
                    completed_at=_parse_timestamp(item.get("completed_at")),
                )
                for item in raw_checklist
                if item
            ]
            responses.append(
                ProcedureRunStepStateResponse(
                    key=step.key,
                    title=step.title,
                    prompt=step.prompt,
                    status="completed",
                    collected_slots=slots,
                    checklist=checklist_items,
                    committed_at=state.committed_at,
                )
            )
        else:
            status_value = "pending"
            if current_step_key == step.key and run.state != "completed":
                status_value = "in_progress"
            responses.append(
                ProcedureRunStepStateResponse(
                    key=step.key,
                    title=step.title,
                    prompt=step.prompt,
                    status=status_value,
                    collected_slots={},
                    checklist=[],
                    committed_at=None,
                )
            )

    return ProcedureRunDetailResponse(
def _serialize_checklist_status(status: ProcedureRunChecklistStatus) -> RunChecklistStatusModel:
    item = status.checklist_item
    step = item.step
    return RunChecklistStatusModel(
        checklist_item_id=status.checklist_item_id,
        step_key=step.key,
        item_key=item.key,
        item_label=item.label,
        completed=status.completed,
        completed_at=status.completed_at,
    )


def _serialize_run(run: ProcedureRun) -> ProcedureRunModel:
    return ProcedureRunModel(
        id=run.id,
        procedure_id=run.procedure_id,
        user_id=run.user_id,
        state=run.state,
        created_at=run.created_at,
        closed_at=run.closed_at,
        current_step=current_step_key,
        steps=responses,
    )


@router.post("", response_model=ProcedureRunDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: ProcedureRunCreateRequest,
    service: ProcedureRunService = Depends(_service),
) -> ProcedureRunDetailResponse:
    user_id = payload.user_id or "anonymous"
    try:
        run = service.start_run(
            procedure_id=payload.procedure_id,
            user_id=user_id,
            actor=user_id,
        )
    except ProcedureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "procedure_not_found", "procedure_id": exc.procedure_id},
        ) from exc

    snapshot = service.get_snapshot(run.id)
    return _build_response(snapshot)


@router.get("/{run_id}", response_model=ProcedureRunDetailResponse)
async def get_run(
    run_id: str,
    service: ProcedureRunService = Depends(_service),
) -> ProcedureRunDetailResponse:
    try:
        snapshot = service.get_snapshot(run_id)
    except ProcedureRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "run_not_found", "run_id": exc.run_id},
        ) from exc
    return _build_response(snapshot)


@router.post("/{run_id}/commit-step", response_model=ProcedureRunDetailResponse)
async def commit_step(
    run_id: str,
    payload: ProcedureRunCommitStepRequest,
    service: ProcedureRunService = Depends(_service),
) -> ProcedureRunDetailResponse:
    try:
        snapshot = service.commit_step(
            run_id=run_id,
            step_key=payload.step_key,
            slots=payload.slots,
            checklist=[item.model_dump(mode="python") for item in payload.checklist],
            actor=None,
        )
    except ProcedureRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "run_not_found", "run_id": exc.run_id},
        ) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "invalid_transition", "message": str(exc)},
        ) from exc
    except SlotValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "slot_validation_failed", "issues": exc.issues},
        ) from exc
    except ChecklistValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "checklist_validation_failed", "issues": exc.issues},
        ) from exc

    return _build_response(snapshot)
        step_states=[RunStepStateModel.model_validate(state) for state in run.step_states],
        checklist_statuses=[_serialize_checklist_status(status) for status in run.checklist_statuses],
    )


@router.get("/{run_id}", response_model=ProcedureRunModel)
def get_run(run_id: str, db: Session = Depends(get_db)) -> ProcedureRunModel:
    service = ProcedureRunService(db)
    try:
        run = service.get_run(run_id)
    except ProcedureRunNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return _serialize_run(run)


@router.post("/{run_id}/commit-step", response_model=ProcedureRunModel)
def commit_step(
    run_id: str, request: CommitStepRequest, db: Session = Depends(get_db)
) -> ProcedureRunModel:
    service = ProcedureRunService(db)
    completed_ids: Iterable[str] | None = None
    if request.checklist is not None:
        completed_ids = request.checklist.completed_item_ids
    try:
        run = service.commit_step(
            run_id=run_id,
            step_key=request.step_key,
            payload=request.payload,
            completed_checklist_item_ids=completed_ids,
        )
        db.commit()
    except ProcedureRunNotFoundError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    except ProcedureStepNotFoundError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown step key for procedure"
        )
    except InvalidChecklistItemError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_checklist_items", "invalid_item_ids": exc.invalid_item_ids},
        )
    except ChecklistIncompleteError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "checklist_incomplete", "missing_item_ids": exc.missing_item_ids},
        )

    return _serialize_run(run)
"""REST API endpoints for procedure runs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Procedure, ProcedureRun, ProcedureRunStepState
from ..schemas.runs import ProcedureRunCreate, ProcedureRunResponse, ProcedureRunStepCommit
from ..services.procedures import cached_run_detail, invalidate_run_cache
from ..utils.serialization import serialize_run

logger = structlog.get_logger(__name__)

router = APIRouter()


def _get_run_or_404(run_id: str, db: Session) -> ProcedureRun:
    run = (
        db.query(ProcedureRun)
        .options(selectinload(ProcedureRun.procedure).selectinload(Procedure.steps))
        .filter(ProcedureRun.id == run_id)
        .one_or_none()
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post("/runs", response_model=ProcedureRunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(payload: ProcedureRunCreate, db: Session = Depends(get_db)) -> ProcedureRunResponse:
    """Create a new procedure run."""

    procedure = db.query(Procedure).filter(Procedure.id == payload.procedure_id).one_or_none()
    if procedure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")

    run = ProcedureRun(
        procedure_id=payload.procedure_id,
        user_id=payload.user_id,
        state=payload.state,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return RunResponse.model_validate(run)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> RunResponse:
    run = db.get(models.ProcedureRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return RunResponse.model_validate(run)


@router.post("/{run_id}/steps/{step_key}/commit", response_model=RunStepResponse)
def commit_step(
    run_id: str,
    step_key: str,
    payload: RunStepPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunStepResponse:
    run = db.get(models.ProcedureRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    if run.procedure_id != payload.slots.get("procedure_id", run.procedure_id):
        # Prevent cross-procedure tampering when slots contain procedure references
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid procedure context")

    _evaluate_policy(current_user, "runs:commit_step", run.procedure_id)

    fsm = ProcedureFSM(db)
    try:
        state = fsm.commit_step(run, step_key, payload.slots, payload.checklist)
        db.commit()
        db.refresh(run)
        db.refresh(state)
    except StepNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StepOrderError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (SlotValidationError, ChecklistValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return RunStepResponse(
        id=state.id,
        run_id=state.run_id,
        step_key=state.step_key,
        payload=state.payload,
        committed_at=state.committed_at,
        run_state=run.state,
    )


__all__ = [
    "router",
    "RunCreate",
    "RunResponse",
]
    run.procedure = procedure

    logger.info("procedure_run_created", run_id=run.id, procedure_id=run.procedure_id)
    invalidate_run_cache(run.id)

    return ProcedureRunResponse(**serialize_run(run, []))


@router.get("/runs/{run_id}", response_model=ProcedureRunResponse)
async def get_run(run_id: str, db: Session = Depends(get_db)) -> ProcedureRunResponse:
    """Return the details of a procedure run, cached when possible."""

    def fetch() -> Dict[str, Any]:
        run = _get_run_or_404(run_id, db)
        states: List[ProcedureRunStepState] = (
            db.query(ProcedureRunStepState)
            .filter(ProcedureRunStepState.run_id == run.id)
            .order_by(ProcedureRunStepState.committed_at)
            .all()
        )
        return serialize_run(run, states)

    payload = cached_run_detail(run_id, fetch)
    return ProcedureRunResponse(**payload)


@router.post(
    "/runs/{run_id}/steps/{step_key}/commit",
    response_model=ProcedureRunResponse,
    status_code=status.HTTP_200_OK,
)
async def commit_step(
    run_id: str,
    step_key: str,
    payload: ProcedureRunStepCommit,
    db: Session = Depends(get_db),
) -> ProcedureRunResponse:
    """Persist the payload for a given step and invalidate the run cache."""

    run = _get_run_or_404(run_id, db)

    state = (
        db.query(ProcedureRunStepState)
        .filter(
            ProcedureRunStepState.run_id == run_id,
            ProcedureRunStepState.step_key == step_key,
        )
        .one_or_none()
    )
    if state is None:
        state = ProcedureRunStepState(run_id=run_id, step_key=step_key, payload=payload.payload)
        db.add(state)
    else:
        state.payload = payload.payload
        state.committed_at = datetime.utcnow()

    db.commit()

    logger.info("procedure_run_step_committed", run_id=run_id, step_key=step_key)
    invalidate_run_cache(run_id)

    states: List[ProcedureRunStepState] = (
        db.query(ProcedureRunStepState)
        .filter(ProcedureRunStepState.run_id == run_id)
        .order_by(ProcedureRunStepState.committed_at)
        .all()
    )
    return ProcedureRunResponse(**serialize_run(run, states))


__all__ = ["router"]
