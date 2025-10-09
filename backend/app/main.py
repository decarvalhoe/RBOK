from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Request, status
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.base import BaseHTTPMiddleware
from redis.exceptions import RedisError
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

from .auth import Token, authenticate_user, create_access_token, require_role
from .cache import get_redis_client
from .database import get_db

from .auth import Token, User, authenticate_user, create_access_token, require_role

logger = logging.getLogger("rbok.api")
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class CorrelationIdFilter(logging.Filter):
    """Inject the correlation id into structured log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging helper
        record.correlation_id = correlation_id_var.get() or "unknown"
        return True


def configure_logging() -> logging.Logger:  # pragma: no cover - logging helper
def configure_logging() -> None:
    """Configure application level logging with correlation ids."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s [correlation_id=%(correlation_id)s] %(message)s",
    )
    logging.getLogger().addFilter(CorrelationIdFilter())


configure_logging()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation id and timing information to each request."""

    async def dispatch(self, request: Request, call_next):  # pragma: no cover - middleware glue
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
    async def dispatch(self, request: Request, call_next):  # pragma: no cover - FastAPI interface
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        token = correlation_id_var.set(correlation_id)
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Unhandled exception", extra={"path": request.url.path})
            raise
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            correlation_id_var.reset(token)
            logger.info(
                "Request completed",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "duration_ms": duration_ms,
                },
            )
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time-ms"] = f"{duration_ms:.2f}"
        return response


app = FastAPI(
    title="Réalisons API",
    description="API pour l'assistant procédural Réalisons",
    version="0.2.0",
    description=(
        "API pour l'assistant procédural Réalisons. Les opérations d'écriture nécessitent un token "
        "Bearer issu de l'endpoint `/auth/token`. Les administrateurs peuvent créer des procédures tandis "
        "que les utilisateurs standard ne peuvent lancer que des exécutions."
    ),
    version="0.1.0",
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
class ProcedureStep(BaseModel):
    key: str
    title: str
    prompt: str
    slots: List[Dict[str, str]] = Field(default_factory=list)
    slots: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ProcedurePayload(BaseModel):
class Procedure(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
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
class ProcedureCreateRequest(BaseModel):
    name: str
    description: str
    steps: List[ProcedureStep]


class ProcedureRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: Optional[datetime] = None




class RunStepCommitRequest(BaseModel):
    payload: Dict[str, Any]


class RunStepStateResponse(BaseModel):
    id: str
    run_id: str
    step_key: str
    payload: Dict[str, Any]
    committed_at: datetime

    model_config = ConfigDict(from_attributes=True)
class ProcedureRunCreateRequest(BaseModel):
    procedure_id: str
    user_id: Optional[str] = None


PROCEDURE_LIST_CACHE_KEY = "procedures:index"
PROCEDURE_LIST_TTL = 60
PROCEDURE_META_TTL = 120
PROCEDURE_STEPS_TTL = 300
RUN_DETAIL_TTL = 60


def procedure_meta_cache_key(procedure_id: str) -> str:
    return f"procedures:{procedure_id}:meta"

procedures_db: Dict[str, Procedure] = {}
runs_db: Dict[str, ProcedureRun] = {}

def procedure_steps_cache_key(procedure_id: str) -> str:
    return f"procedures:{procedure_id}:steps"


def run_cache_key(run_id: str) -> str:
    return f"runs:{run_id}"


def _cache_get_json(key: str) -> Optional[Any]:
    try:
        cached = get_redis_client().get(key)
    except RedisError as exc:  # pragma: no cover - defensive logging
        logger.warning("Redis GET failed", extra={"key": key, "error": str(exc)})
        return None
    if cached is None:
        return None
    try:
        return json.loads(cached)
    except json.JSONDecodeError:  # pragma: no cover - corrupted cache entry
        logger.warning("Invalid JSON cached", extra={"key": key})
        return None


def _cache_set_json(key: str, value: Any, ttl: int) -> None:
    try:
        get_redis_client().setex(key, ttl, json.dumps(value))
    except RedisError as exc:  # pragma: no cover - defensive logging
        logger.warning("Redis SETEX failed", extra={"key": key, "error": str(exc)})


def _cache_delete(*keys: str) -> None:
    keys = tuple(filter(None, keys))
    if not keys:
        return
    try:
        get_redis_client().delete(*keys)
    except RedisError as exc:  # pragma: no cover - defensive logging
        logger.warning("Redis DELETE failed", extra={"keys": keys, "error": str(exc)})


def _combine_cached_procedure(procedure_id: str) -> Optional[Dict[str, Any]]:
    meta = _cache_get_json(procedure_meta_cache_key(procedure_id))
    steps = _cache_get_json(procedure_steps_cache_key(procedure_id))
    if meta is None or steps is None:
        return None
    combined: Dict[str, Any] = {"steps": steps, **meta}
    return combined


def _serialize_procedure(procedure: models.Procedure) -> Dict[str, Any]:
    return Procedure.model_validate(procedure).model_dump(mode="json")


def _serialize_run(run: models.ProcedureRun) -> Dict[str, Any]:
    return ProcedureRun.model_validate(run).model_dump(mode="json")


def _store_procedure_in_cache(procedure_data: Dict[str, Any]) -> None:
    procedure_id = procedure_data["id"]
    meta = {key: procedure_data[key] for key in ("id", "name", "description")}
    steps = procedure_data.get("steps", [])
    _cache_set_json(procedure_meta_cache_key(procedure_id), meta, PROCEDURE_META_TTL)
    _cache_set_json(procedure_steps_cache_key(procedure_id), steps, PROCEDURE_STEPS_TTL)


def _invalidate_procedure_cache(procedure_id: str) -> None:
    _cache_delete(procedure_meta_cache_key(procedure_id), procedure_steps_cache_key(procedure_id))


def _invalidate_procedure_list_cache() -> None:
    _cache_delete(PROCEDURE_LIST_CACHE_KEY)


def _store_procedure_index(procedures: List[Dict[str, Any]]) -> None:
    ids = [procedure["id"] for procedure in procedures]
    _cache_set_json(PROCEDURE_LIST_CACHE_KEY, ids, PROCEDURE_LIST_TTL)


class DomainError(Exception):
    """Base domain exception."""


class ProcedureNotFoundError(DomainError):
    """Raised when the requested procedure does not exist."""


class RunNotFoundError(DomainError):
    """Raised when the requested run does not exist."""


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
        "Domain error",
        extra={"path": request.url.path, "error": exc.__class__.__name__},
    )
    return JSONResponse(status_code=404, content={"detail": str(exc) or exc.__class__.__name__})


@app.post("/auth/token", response_model=Token, tags=["auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"sub": user.username, "role": user.role})
    return Token(access_token=access_token)


@app.get("/")
def root() -> Dict[str, str]:
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
    return {"status": "healthy", "version": app.version or "0.1.0"}


@app.get("/procedures", response_model=List[Procedure])
def list_procedures() -> List[Procedure]:
    logger.info("Listing procedures", extra={"count": len(procedures_db)})
    return list(procedures_db.values())

@app.post("/auth/token", response_model=Token, tags=["auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Dict[str, str]:
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/procedures", response_model=List[Procedure])
def list_procedures(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    cached_ids = _cache_get_json(PROCEDURE_LIST_CACHE_KEY)
    if cached_ids is not None:
        if not cached_ids:
            logger.debug("Returning empty procedure list from cache")
            return []
        cached_procedures = [
            _combine_cached_procedure(procedure_id) for procedure_id in cached_ids
        ]
        if all(item is not None for item in cached_procedures):
            logger.debug(
                "Returning procedures from cache",
                extra={"count": len(cached_procedures)},
            )
            return [item for item in cached_procedures if item is not None]

    procedures = (
        db.query(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .order_by(models.Procedure.name)
        .all()
    )
    serialized = [_serialize_procedure(procedure) for procedure in procedures]
    if serialized:
        for payload in serialized:
            _store_procedure_in_cache(payload)
        _store_procedure_index(serialized)
    else:
        _cache_set_json(PROCEDURE_LIST_CACHE_KEY, [], PROCEDURE_LIST_TTL)
    return serialized


@app.post(
    "/procedures",
    response_model=Procedure,
    status_code=status.HTTP_201_CREATED,
)
def create_procedure(
    payload: ProcedureCreateRequest,
    current_user: User = Depends(require_role("admin")),
) -> Procedure:
    _ = current_user  # used for dependency side-effects only
    procedure_id = str(uuid.uuid4())
    procedure = Procedure(
        id=procedure_id,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
) -> Dict[str, Any]:
    logger.info(
        "Creating procedure",
        extra={"procedure_name": payload.name, "user": current_user.username},
    )
    procedure = models.Procedure(
        id=str(uuid.uuid4()),
        name=payload.name,
        description=payload.description,
    )
    procedures_db[procedure_id] = procedure
    logger.info(
        "Procedure created", extra={"procedure_id": procedure_id, "author": current_user.username}
    )
    return procedure


@app.get("/procedures/{procedure_id}", response_model=Procedure)
def get_procedure(procedure_id: str) -> Procedure:
    try:
        return procedures_db[procedure_id]
    except KeyError as exc:
        raise ProcedureNotFoundError("Procedure not found") from exc
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

    serialized = _serialize_procedure(procedure)
    _store_procedure_in_cache(serialized)
    _invalidate_procedure_list_cache()
    return serialized


@app.get("/procedures/{procedure_id}", response_model=Procedure)
def get_procedure(procedure_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    cached = _combine_cached_procedure(procedure_id)
    if cached is not None:
        logger.debug("Returning procedure from cache", extra={"procedure_id": procedure_id})
        return cached

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
        raise HTTPException(status_code=404, detail="Procedure not found")

    serialized = _serialize_procedure(procedure)
    _store_procedure_in_cache(serialized)
    return serialized


@app.post(
    "/runs",
    response_model=ProcedureRun,
    status_code=status.HTTP_201_CREATED,
)
def start_procedure_run(
    payload: ProcedureRunCreateRequest | None = Body(default=None),
    procedure_id: Optional[str] = None,
    current_user: User = Depends(require_role("user")),
) -> ProcedureRun:
    effective_procedure_id = procedure_id or (payload.procedure_id if payload else None)
    if not effective_procedure_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="procedure_id is required"
        )
    if effective_procedure_id not in procedures_db:
        raise ProcedureNotFoundError("Procedure not found")

    run_id = str(uuid.uuid4())
    run = ProcedureRun(
        id=run_id,
        procedure_id=effective_procedure_id,
        user_id=(payload.user_id if payload and payload.user_id else current_user.username),
        state="started",
        created_at=datetime.utcnow(),
    )
    runs_db[run_id] = run
    logger.info(
        "Procedure run started",
        extra={
            "procedure_id": effective_procedure_id,
            "run_id": run_id,
            "user": current_user.username,
        },
    )
    return run


@app.get("/runs/{run_id}", response_model=ProcedureRun)
def get_run(run_id: str) -> ProcedureRun:
    try:
        return runs_db[run_id]
    except KeyError as exc:
        raise RunNotFoundError("Run not found") from exc


__all__ = ["app", "procedures_db", "runs_db"]
    payload: ProcedureRunCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("user")),
) -> Dict[str, Any]:
    logger.info(
        "Starting procedure run",
        extra={"procedure_id": payload.procedure_id, "user": current_user.username},
    )
    procedure_exists = (
        db.query(models.Procedure.id)
        .filter(models.Procedure.id == payload.procedure_id)
        .first()
    )
    if not procedure_exists:
        raise HTTPException(status_code=404, detail="Procedure not found")

    run = models.ProcedureRun(
        id=str(uuid.uuid4()),
        procedure_id=payload.procedure_id,
        user_id=payload.user_id or current_user.username,
        state="started",
        created_at=datetime.utcnow(),
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



    serialized = _serialize_run(run)
    _cache_set_json(run_cache_key(run.id), serialized, RUN_DETAIL_TTL)
    return serialized


@app.get("/runs/{run_id}", response_model=ProcedureRun)
def get_run(run_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    cached = _cache_get_json(run_cache_key(run_id))
    if cached is not None:
        logger.debug("Returning run from cache", extra={"run_id": run_id})
        return cached

    run = db.get(models.ProcedureRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    serialized = _serialize_run(run)
    _cache_set_json(run_cache_key(run_id), serialized, RUN_DETAIL_TTL)
    return serialized


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
