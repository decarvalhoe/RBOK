from __future__ import annotations

import json
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
from redis.exceptions import RedisError
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.base import BaseHTTPMiddleware

from . import models
from .auth import Token, authenticate_user, create_access_token, require_role
from .cache import get_redis_client
from .database import get_db


class DomainError(Exception):
    """Base class for domain errors."""


class NotFoundError(DomainError):
    """Raised when an entity is not found."""


class ProcedureNotFoundError(NotFoundError):
    """Raised when a procedure cannot be located."""


class RunNotFoundError(NotFoundError):
    """Raised when a run cannot be located."""


correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class CorrelationIdFilter(logging.Filter):
    """Inject the current correlation id into each log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get() or "unknown"
        return True


def configure_logging() -> logging.Logger:
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

    async def dispatch(self, request: Request, call_next):  # pragma: no cover - FastAPI interface
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        token = correlation_id_var.set(correlation_id)
        start_time = time.perf_counter()
        response = None
        try:
            logger.info("Handling request", extra={"path": request.url.path, "method": request.method})
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Unhandled exception during request",
                extra={"path": request.url.path, "method": request.method},
            )
            raise exc
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


class ProcedureStep(BaseModel):
    key: str
    title: str
    prompt: str
    slots: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class Procedure(BaseModel):
    id: Optional[str] = None
    name: str
    description: str
    steps: List[ProcedureStep] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ProcedureCreateRequest(BaseModel):
    name: str
    description: str
    steps: List[ProcedureStep]


class ProcedureRun(BaseModel):
    id: Optional[str] = None
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: Optional[datetime] = None

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


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    logger.warning(
        "Resource not found",
        extra={"path": request.url.path, "detail": str(exc) or exc.__class__.__name__},
    )
    return JSONResponse(status_code=404, content={"detail": str(exc) or "Resource not found"})


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    logger.warning(
        "Domain error raised",
        extra={"path": request.url.path, "detail": str(exc) or exc.__class__.__name__},
    )
    return JSONResponse(status_code=400, content={"detail": str(exc) or "Bad request"})


@app.get("/")
def read_root() -> Dict[str, str]:
    logger.debug("Root endpoint accessed")
    return {"message": "Bienvenue sur l'API de l'assistant Réalisons v0.1"}


@app.get("/health")
def health_check() -> Dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "healthy", "version": "0.1.0"}


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
