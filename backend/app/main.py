"""Main FastAPI application for the Réalisons backend."""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from redis.exceptions import RedisError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
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
from .cache import get_redis_client
from .config import Settings, get_settings
from .database import get_db
from .env import analyse_environment, validate_environment
from .services import audit

load_dotenv()

logger = logging.getLogger("realisons.backend")
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)

limiter = Limiter(key_func=get_remote_address)
_active_settings: Optional[Settings] = None


# ============================================================================
# Logging and Middleware
# ============================================================================


class CorrelationIdFilter(logging.Filter):
    """Inject the current correlation identifier into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging utility
        record.correlation_id = correlation_id_var.get() or "unknown"
        return True


def configure_logging() -> None:
    """Configure application level logging with correlation ids."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s [correlation_id=%(correlation_id)s] %(message)s",
    )
    logging.getLogger().addFilter(CorrelationIdFilter())


configure_logging()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach correlation identifiers to every request."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        """Attach a correlation identifier and processing time to each response."""
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


# ============================================================================
# Domain Errors
# ============================================================================


class DomainError(Exception):
    """Base class for domain-level errors."""


class NotFoundError(DomainError):
    """Raised when an entity cannot be located."""


class ProcedureNotFoundError(NotFoundError):
    """Raised when a procedure cannot be found."""


class RunNotFoundError(NotFoundError):
    """Raised when a run cannot be found."""


# ============================================================================
# Pydantic Models
# ============================================================================


class ProcedureStep(BaseModel):
    """A single step within a procedure."""
    
    key: str
    title: str
    prompt: str
    slots: List[Dict[str, Any]] = Field(default_factory=list)
    
    model_config = ConfigDict(from_attributes=True)


class Procedure(BaseModel):
    """A complete procedure with its steps."""
    
    id: str
    name: str
    description: str
    steps: List[ProcedureStep] = Field(default_factory=list)
    
    model_config = ConfigDict(from_attributes=True)


class ProcedureCreateRequest(BaseModel):
    """Request payload for creating a new procedure."""
    
    name: str
    description: str
    steps: List[ProcedureStep] = Field(default_factory=list)


class ProcedureRun(BaseModel):
    """A run instance of a procedure."""
    
    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class ProcedureRunCreateRequest(BaseModel):
    """Request payload for creating a new run."""
    
    procedure_id: str
    user_id: Optional[str] = None


class ProcedureRunUpdatePayload(BaseModel):
    """Payload for updating an existing run."""
    
    state: Optional[str] = None
    closed_at: Optional[datetime] = None


class RunStepCommitRequest(BaseModel):
    """Request payload for committing a step state."""
    
    payload: Dict[str, Any]


class RunStepStateResponse(BaseModel):
    """Response model for a committed step state."""
    
    id: str
    run_id: str
    step_key: str
    payload: Dict[str, Any]
    committed_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class AuditEventResponse(BaseModel):
    """Response model for audit events."""
    
    id: str
    actor: str
    occurred_at: datetime
    action: str
    entity_type: str
    entity_id: str
    payload_diff: Dict[str, Any]
    
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Cache Keys and TTLs
# ============================================================================

PROCEDURE_LIST_CACHE_KEY = "procedures:index"
PROCEDURE_LIST_TTL = 60
PROCEDURE_META_TTL = 120
PROCEDURE_STEPS_TTL = 300
RUN_DETAIL_TTL = 60


def procedure_meta_cache_key(procedure_id: str) -> str:
    """Generate cache key for procedure metadata."""
    return f"procedures:{procedure_id}:meta"


def procedure_steps_cache_key(procedure_id: str) -> str:
    """Generate cache key for procedure steps."""
    return f"procedures:{procedure_id}:steps"


def run_cache_key(run_id: str) -> str:
    """Generate cache key for run details."""
    return f"runs:{run_id}"


# ============================================================================
# Cache Helper Functions
# ============================================================================


def _cache_get_json(key: str) -> Optional[Any]:
    """Retrieve and deserialize a JSON value from cache."""
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
    """Serialize and store a value in cache with TTL."""
    try:
        get_redis_client().setex(key, ttl, json.dumps(value))
    except RedisError as exc:  # pragma: no cover - defensive logging
        logger.warning("Redis SETEX failed", extra={"key": key, "error": str(exc)})


def _cache_delete(*keys: str) -> None:
    """Delete one or more keys from cache."""
    keys = tuple(filter(None, keys))
    if not keys:
        return
    
    try:
        get_redis_client().delete(*keys)
    except RedisError as exc:  # pragma: no cover - defensive logging
        logger.warning("Redis DELETE failed", extra={"keys": keys, "error": str(exc)})


def _combine_cached_procedure(procedure_id: str) -> Optional[Dict[str, Any]]:
    """Reconstruct a full procedure from cached parts."""
    meta = _cache_get_json(procedure_meta_cache_key(procedure_id))
    steps = _cache_get_json(procedure_steps_cache_key(procedure_id))
    
    if meta is None or steps is None:
        return None
    
    combined: Dict[str, Any] = {"steps": steps, **meta}
    return combined


def _serialize_procedure(procedure: models.Procedure) -> Dict[str, Any]:
    """Convert a Procedure model to a JSON-serializable dict."""
    return Procedure.model_validate(procedure).model_dump(mode="json")


def _serialize_run(run: models.ProcedureRun) -> Dict[str, Any]:
    """Convert a ProcedureRun model to a JSON-serializable dict."""
    return ProcedureRun.model_validate(run).model_dump(mode="json")


def _store_procedure_in_cache(procedure_data: Dict[str, Any]) -> None:
    """Store procedure metadata and steps in cache."""
    procedure_id = procedure_data["id"]
    meta = {key: procedure_data[key] for key in ("id", "name", "description")}
    steps = procedure_data.get("steps", [])
    
    _cache_set_json(procedure_meta_cache_key(procedure_id), meta, PROCEDURE_META_TTL)
    _cache_set_json(procedure_steps_cache_key(procedure_id), steps, PROCEDURE_STEPS_TTL)


def _invalidate_procedure_cache(procedure_id: str) -> None:
    """Remove procedure data from cache."""
    _cache_delete(procedure_meta_cache_key(procedure_id), procedure_steps_cache_key(procedure_id))


def _invalidate_procedure_list_cache() -> None:
    """Remove the procedure list index from cache."""
    _cache_delete(PROCEDURE_LIST_CACHE_KEY)


def _store_procedure_index(procedures: List[Dict[str, Any]]) -> None:
    """Store the list of procedure IDs in cache."""
    ids = [procedure["id"] for procedure in procedures]
    _cache_set_json(PROCEDURE_LIST_CACHE_KEY, ids, PROCEDURE_LIST_TTL)


def _serialise_procedure(procedure: models.Procedure) -> Dict[str, Any]:
    """Serialize procedure for audit logging."""
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
    """Serialize run for audit logging."""
    return {
        "id": run.id,
        "procedure_id": run.procedure_id,
        "user_id": run.user_id,
        "state": run.state,
        "created_at": run.created_at.isoformat(),
        "closed_at": run.closed_at.isoformat() if run.closed_at else None,
    }


def _actor(current_user: Optional[User]) -> str:
    """Extract actor name from current user."""
    return current_user.username if current_user else "system"


# ============================================================================
# Rate Limiting Configuration
# ============================================================================

THROTTLE_RESPONSE_TEMPLATE: Dict[int, Dict[str, object]] = {
    429: {
        "description": "Too Many Requests",
        "content": {
            "application/json": {
                "example": {"detail": "Rate limit exceeded"},
            }
        },
        "headers": {
            "Retry-After": {
                "description": "Time in seconds before a subsequent request will be accepted.",
                "schema": {"type": "string"},
            },
            "X-RateLimit-Limit": {
                "description": "Request limit for the current window.",
                "schema": {"type": "string"},
            },
            "X-RateLimit-Remaining": {
                "description": "Remaining number of allowed requests in the current window.",
                "schema": {"type": "string"},
            },
            "X-RateLimit-Reset": {
                "description": "Unix timestamp indicating when the window resets.",
                "schema": {"type": "string"},
            },
        },
    }
}


def throttle_responses() -> Dict[int, Dict[str, object]]:
    """Return response documentation for throttled endpoints."""
    return deepcopy(THROTTLE_RESPONSE_TEMPLATE)


def default_rate_limit() -> str:
    """Return the default rate limit string for slowapi decorators."""
    settings_obj = _active_settings or get_settings()
    return settings_obj.rate_limit_default


# ============================================================================
# App Factory and Configuration
# ============================================================================


def configure_cors(app: FastAPI, settings: Settings) -> None:
    """Configure CORS middleware."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def configure_rate_limiter(app: FastAPI, settings: Settings) -> None:
    """Configure rate limiting middleware."""
    global _active_settings
    _active_settings = settings
    limiter.enabled = settings.rate_limit_enabled
    limiter._headers_enabled = settings.rate_limit_headers_enabled  # type: ignore[attr-defined]
    app.state.settings = settings
    app.state.limiter = limiter
    
    if not getattr(app.state, "rate_limiter_configured", False):
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)
        app.state.rate_limiter_configured = True


def create_app(settings: Settings) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Réalisons API",
        description=(
            "API pour l'assistant procédural Réalisons. "
            "Les opérations d'écriture nécessitent un token Bearer issu de l'endpoint `/auth/token`. "
            "Les administrateurs peuvent créer des procédures tandis que les utilisateurs standard peuvent uniquement lancer des exécutions."
        ),
        version="0.2.0",
    )
    app.state.settings = settings
    configure_cors(app, settings)
    configure_rate_limiter(app, settings)
    app.add_middleware(CorrelationIdMiddleware)
    return app


settings = get_settings()
app = create_app(settings)

# In-memory placeholders kept for backward-compatible tests
procedures_db: Dict[str, Procedure] = {}
runs_db: Dict[str, ProcedureRun] = {}


# ============================================================================
# Exception Handlers
# ============================================================================


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Handle domain-specific errors."""
    logger.warning(
        "Domain error",
        extra={"path": request.url.path, "error": exc.__class__.__name__},
    )
    return JSONResponse(status_code=404, content={"detail": str(exc) or exc.__class__.__name__})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:  # pragma: no cover - wiring
    """Handle HTTP exceptions."""
    logger.warning(
        "HTTP exception raised",
        extra={"path": request.url.path, "detail": exc.detail, "status_code": exc.status_code},
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover - safety net
    """Handle unhandled exceptions."""
    logger.exception("Unhandled error", extra={"path": request.url.path})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ============================================================================
# Health and Auth Endpoints
# ============================================================================


@app.on_event("startup")
def ensure_environment() -> None:
    """Validate configuration as soon as the application starts."""
    validate_environment()


@app.get("/healthz")
def healthz() -> Dict[str, object]:
    """Return environment validation information for monitoring."""
    issues = analyse_environment()
    status_value = "ok" if not issues["missing"] and not issues["insecure"] else "degraded"
    return {"status": status_value, **issues}


@app.get("/", responses=throttle_responses())
@limiter.limit(default_rate_limit)
def read_root(request: Request, response: Response) -> Dict[str, str]:
    """Root endpoint."""
    logger.debug("Root endpoint accessed")
    return {"message": "Bienvenue sur l'API de l'assistant Réalisons v0.2"}


@app.get("/health", responses=throttle_responses())
@limiter.limit(default_rate_limit)
def health_check(request: Request, response: Response) -> Dict[str, str]:
    """Health check endpoint."""
    logger.debug("Health check requested")
    return {"status": "healthy", "version": app.version or "0.2.0"}


@app.post("/auth/token", response_model=Token, tags=["auth"], responses=throttle_responses())
@limiter.limit(default_rate_limit)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Token:
    """Authenticate user and return access token."""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"sub": user.username, "role": user.role})
    return Token(access_token=access_token)


# ============================================================================
# Procedure Endpoints
# ============================================================================


@app.get("/procedures", response_model=List[Procedure], responses=throttle_responses())
@limiter.limit(default_rate_limit)
def list_procedures(request: Request, response: Response, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """List all procedures."""
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
    responses=throttle_responses(),
)
@limiter.limit(default_rate_limit)
def create_procedure(
    request: Request,
    response: Response,
    payload: ProcedureCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> Dict[str, Any]:
    """Create a new procedure."""
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


@app.get("/procedures/{procedure_id}", response_model=Procedure, responses=throttle_responses())
@limiter.limit(default_rate_limit)
def get_procedure(request: Request, response: Response, procedure_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get a specific procedure by ID."""
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


@app.put("/procedures/{procedure_id}", response_model=Procedure, responses=throttle_responses())
@limiter.limit(default_rate_limit)
def update_procedure(
    request: Request,
    response: Response,
    procedure_id: str,
    payload: ProcedureCreateRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> Procedure:
    """Update an existing procedure."""
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
    
    _invalidate_procedure_cache(procedure_id)
    _invalidate_procedure_list_cache()
    
    return procedure


# ============================================================================
# Run Endpoints
# ============================================================================


@app.post(
    "/runs",
    response_model=ProcedureRun,
    status_code=status.HTTP_201_CREATED,
    responses=throttle_responses(),
)
@limiter.limit(default_rate_limit)
def start_procedure_run(
    request: Request,
    response: Response,
    payload: ProcedureRunCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user")),
) -> Dict[str, Any]:
    """Start a new procedure run."""
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


@app.get("/runs/{run_id}", response_model=ProcedureRun, responses=throttle_responses())
@limiter.limit(default_rate_limit)
def get_run(request: Request, response: Response, run_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get a specific run by ID."""
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


@app.patch("/runs/{run_id}", response_model=ProcedureRun, responses=throttle_responses())
@limiter.limit(default_rate_limit)
def update_procedure_run(
    request: Request,
    response: Response,
    run_id: str,
    payload: ProcedureRunUpdatePayload,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> ProcedureRun:
    """Update an existing run."""
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
    
    _cache_delete(run_cache_key(run_id))
    
    return run


@app.post(
    "/runs/{run_id}/steps/{step_key}/commit",
    response_model=RunStepStateResponse,
    status_code=status.HTTP_201_CREATED,
    responses=throttle_responses(),
)
@limiter.limit(default_rate_limit)
def commit_run_step(
    request: Request,
    response: Response,
    run_id: str,
    step_key: str,
    req_body: RunStepCommitRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> RunStepStateResponse:
    """Commit the state for a specific step in a run."""
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
            payload=req_body.payload,
        )
        db.add(state)
    else:
        before_payload = state.payload.copy()
        state.payload = req_body.payload
    
    state.committed_at = datetime.utcnow()
    db.commit()
    db.refresh(state)
    
    audit.step_committed(
        db,
        actor=_actor(current_user),
        run_id=run_id,
        step_key=step_key,
        before=before_payload,
        after=req_body.payload,
    )
    
    return state


# ============================================================================
# Audit Endpoints
# ============================================================================


@app.get("/audit-events", response_model=List[AuditEventResponse], responses=throttle_responses())
@limiter.limit(default_rate_limit)
def list_audit_events(
    request: Request,
    response: Response,
    actor: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("auditor")),
) -> List[AuditEventResponse]:
    """List audit events with optional filters."""
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


# ============================================================================
# Module Exports
# ============================================================================

__all__ = [
    "app",
    "procedures_db",
    "runs_db",
    "configure_rate_limiter",
    "create_app",
]


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    import uvicorn
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
