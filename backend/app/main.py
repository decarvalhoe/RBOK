from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.base import BaseHTTPMiddleware

from . import models
from .auth import (
    Token,
    User,
    authenticate_user,
    create_access_token,
    get_current_user_optional,
    require_role,
)
from .database import get_db
from .services import audit


correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class CorrelationIdFilter(logging.Filter):
    """Inject the current correlation id into each log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging helper
        record.correlation_id = correlation_id_var.get() or "unknown"
        return True


def configure_logging() -> logging.Logger:  # pragma: no cover - logging helper
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s [correlation_id=%(correlation_id)s] %(message)s",
    )
    logger = logging.getLogger("realison.api")
    logger.addFilter(CorrelationIdFilter())
    logging.getLogger().addFilter(CorrelationIdFilter())
    return logger


logger = configure_logging()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach correlation ids and timing information to each request."""

    async def dispatch(self, request: Request, call_next):  # pragma: no cover - middleware glue
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        token = correlation_id_var.set(correlation_id)
        start_time = time.perf_counter()
        response = None
        try:
            logger.info("Handling request", extra={"path": request.url.path, "method": request.method})
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            status_code = getattr(response, "status_code", 500)
            logger.info(
                "Request completed",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "duration_ms": duration_ms,
                    "status_code": status_code,
                },
            )
            if response is not None:
                response.headers["X-Correlation-ID"] = correlation_id
                response.headers["X-Process-Time-ms"] = f"{duration_ms:.2f}"
            correlation_id_var.reset(token)

        return response


app = FastAPI(
    title="Réalisons API",
    description="API pour l'assistant procédural Réalisons",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)


class ProcedureStepPayload(BaseModel):
    key: str
    title: str
    prompt: str
    slots: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ProcedurePayload(BaseModel):
    name: str
    description: str
    steps: List[ProcedureStepPayload] = Field(default_factory=list)


class ProcedureResponse(ProcedurePayload):
    id: str

    model_config = ConfigDict(from_attributes=True)


class ProcedureRunPayload(BaseModel):
    procedure_id: str
    user_id: Optional[str] = Field(default="default_user")
    state: str = Field(default="started")


class ProcedureRunUpdatePayload(BaseModel):
    state: Optional[str] = None
    closed_at: Optional[datetime] = None


class ProcedureRunResponse(BaseModel):
    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RunStepCommitRequest(BaseModel):
    payload: Dict[str, Any]


class RunStepStateResponse(BaseModel):
    id: str
    run_id: str
    step_key: str
    payload: Dict[str, Any]
    committed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditEventResponse(BaseModel):
    id: str
    actor: str
    occurred_at: datetime
    action: str
    entity_type: str
    entity_id: str
    payload_diff: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


def _actor(current_user: Optional[User]) -> str:
    return current_user.username if current_user else "system"


def _serialise_procedure(procedure: models.Procedure) -> Dict[str, Any]:
    return {
        "id": procedure.id,
        "name": procedure.name,
        "description": procedure.description,
        "steps": [
            {
                "id": step.id,
                "key": step.key,
                "title": step.title,
                "prompt": step.prompt,
                "slots": step.slots,
                "position": step.position,
            }
            for step in sorted(procedure.steps, key=lambda s: s.position)
        ],
    }


def _serialise_run(run: models.ProcedureRun) -> Dict[str, Any]:
    return {
        "id": run.id,
        "procedure_id": run.procedure_id,
        "user_id": run.user_id,
        "state": run.state,
        "created_at": run.created_at.isoformat(),
        "closed_at": run.closed_at.isoformat() if run.closed_at else None,
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:  # pragma: no cover - wiring
    logger.warning(
        "HTTP exception raised",
        extra={"path": request.url.path, "detail": exc.detail, "status_code": exc.status_code},
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/")
def read_root() -> Dict[str, str]:
    logger.debug("Root endpoint accessed")
    return {"message": "Bienvenue sur l'API de l'assistant Réalisons v0.2"}


@app.get("/health")
def health_check() -> Dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "healthy", "version": "0.2.0"}


@app.post("/auth/token", response_model=Token, tags=["auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/procedures", response_model=List[ProcedureResponse])
def list_procedures(db: Session = Depends(get_db)):
    procedures = (
        db.query(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .order_by(models.Procedure.name)
        .all()
    )
    return procedures


@app.post(
    "/procedures",
    response_model=ProcedureResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_procedure(
    payload: ProcedurePayload,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    procedure = models.Procedure(
        id=str(uuid.uuid4()),
        name=payload.name,
        description=payload.description,
    )
    for index, step in enumerate(payload.steps):
        procedure.steps.append(
            models.ProcedureStep(
                key=step.key,
                title=step.title,
                prompt=step.prompt,
                slots=step.slots,
                position=index,
            )
        )
    db.add(procedure)
    db.commit()
    db.refresh(procedure)
    audit.procedure_created(db, actor=_actor(current_user), procedure=_serialise_procedure(procedure))
    return procedure


@app.put("/procedures/{procedure_id}", response_model=ProcedureResponse)
def update_procedure(
    procedure_id: str,
    payload: ProcedurePayload,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    procedure = (
        db.query(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .filter(models.Procedure.id == procedure_id)
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")

    before = _serialise_procedure(procedure)

    procedure.name = payload.name
    procedure.description = payload.description
    procedure.steps.clear()
    db.flush()
    for index, step in enumerate(payload.steps):
        procedure.steps.append(
            models.ProcedureStep(
                key=step.key,
                title=step.title,
                prompt=step.prompt,
                slots=step.slots,
                position=index,
            )
        )
    db.commit()
    db.refresh(procedure)
    audit.procedure_updated(
        db,
        actor=_actor(current_user),
        procedure_id=procedure.id,
        before=before,
        after=_serialise_procedure(procedure),
    )
    return procedure


@app.get("/procedures/{procedure_id}", response_model=ProcedureResponse)
def get_procedure(procedure_id: str, db: Session = Depends(get_db)):
    procedure = (
        db.query(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .filter(models.Procedure.id == procedure_id)
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")
    return procedure


@app.post("/runs", response_model=ProcedureRunResponse, status_code=status.HTTP_201_CREATED)
def start_procedure_run(
    payload: ProcedureRunPayload,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    procedure_exists = (
        db.query(models.Procedure.id)
        .filter(models.Procedure.id == payload.procedure_id)
        .first()
    )
    if not procedure_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procedure not found")

    run = models.ProcedureRun(
        id=str(uuid.uuid4()),
        procedure_id=payload.procedure_id,
        user_id=payload.user_id or (current_user.username if current_user else "default_user"),
        state=payload.state,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    audit.run_created(db, actor=_actor(current_user), run=_serialise_run(run))
    return run


@app.patch("/runs/{run_id}", response_model=ProcedureRunResponse)
def update_procedure_run(
    run_id: str,
    payload: ProcedureRunUpdatePayload,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    run = db.get(models.ProcedureRun, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    before = _serialise_run(run)
    if payload.state is not None:
        run.state = payload.state
    if payload.closed_at is not None:
        run.closed_at = payload.closed_at
    db.commit()
    db.refresh(run)
    audit.run_updated(
        db,
        actor=_actor(current_user),
        run_id=run.id,
        before=before,
        after=_serialise_run(run),
    )
    return run


@app.get("/runs/{run_id}", response_model=ProcedureRunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(models.ProcedureRun, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@app.post(
    "/runs/{run_id}/steps/{step_key}/commit",
    response_model=RunStepStateResponse,
    status_code=status.HTTP_201_CREATED,
)
def commit_run_step(
    run_id: str,
    step_key: str,
    request: RunStepCommitRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    run = db.get(models.ProcedureRun, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    state = (
        db.query(models.ProcedureRunStepState)
        .filter(
            models.ProcedureRunStepState.run_id == run_id,
            models.ProcedureRunStepState.step_key == step_key,
        )
        .one_or_none()
    )
    before_payload: Optional[Dict[str, Any]] = None
    if state is None:
        state = models.ProcedureRunStepState(
            run_id=run_id,
            step_key=step_key,
            payload=request.payload,
        )
        db.add(state)
    else:
        before_payload = state.payload.copy()
        state.payload = request.payload
    state.committed_at = datetime.utcnow()
    db.commit()
    db.refresh(state)
    audit.step_committed(
        db,
        actor=_actor(current_user),
        run_id=run_id,
        step_key=step_key,
        before=before_payload,
        after=request.payload,
    )
    return state


@app.get("/audit-events", response_model=List[AuditEventResponse])
def list_audit_events(
    actor: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("auditor")),
):
    query = db.query(models.AuditEvent)
    if actor:
        query = query.filter(models.AuditEvent.actor == actor)
    if entity_type:
        query = query.filter(models.AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.filter(models.AuditEvent.entity_id == entity_id)
    if action:
        query = query.filter(models.AuditEvent.action == action)
    if since:
        query = query.filter(models.AuditEvent.occurred_at >= since)
    if until:
        query = query.filter(models.AuditEvent.occurred_at <= until)

    events = query.order_by(models.AuditEvent.occurred_at.desc()).all()
    return events


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
