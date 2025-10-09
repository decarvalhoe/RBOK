"""Main FastAPI application for the Réalisons backend."""
from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import Token, authenticate_user, create_access_token, require_role
from .config import Settings, get_settings

limiter = Limiter(key_func=get_remote_address)
_active_settings: Optional[Settings] = None

class CorrelationIdFilter(logging.Filter):
    """Inject the current correlation identifier into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging utility
        record.correlation_id = correlation_id_var.get() or "unknown"
        return True


correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def configure_logging() -> logging.Logger:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("realison.api")
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [correlation_id=%(correlation_id)s] %(message)s"
        )
    )
    handler.addFilter(CorrelationIdFilter())
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


logger = configure_logging()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation identifier and processing time to each response."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        token = correlation_id_var.set(correlation_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            correlation_id_var.reset(token)
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        correlation_id_var.reset(token)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time-ms"] = f"{duration_ms:.2f}"
        return response


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


class DomainError(Exception):
    """Base class for domain specific errors."""


class NotFoundError(DomainError):
    """Raised when an entity cannot be located."""


class ProcedureNotFoundError(NotFoundError):
    """Raised when a procedure cannot be found."""


class RunNotFoundError(NotFoundError):
    """Raised when a run cannot be found."""


class ProcedureStep(BaseModel):
    key: str
    title: str
    prompt: str
    slots: List[Dict[str, str]] = Field(default_factory=list)

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
    steps: List[ProcedureStep] = Field(default_factory=list)


class ProcedureRun(BaseModel):
    id: Optional[str] = None
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


procedures_db: Dict[str, Procedure] = {}
runs_db: Dict[str, ProcedureRun] = {}


async def parse_procedure_request(request: Request) -> ProcedureCreateRequest:
    """Parse and validate a procedure creation payload from the request body."""

    data = await request.json()
    try:
        return ProcedureCreateRequest.model_validate(data)
    except ValidationError as exc:  # pragma: no cover - FastAPI surfaces as 422
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.errors()) from exc


def configure_cors(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def configure_rate_limiter(app: FastAPI, settings: Settings) -> None:
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
    app = FastAPI(
        title="Réalisons API",
        description=(
            "API pour l'assistant procédural Réalisons. "
            "Les opérations d'écriture nécessitent un token Bearer issu de l'endpoint `/auth/token`. "
            "Les administrateurs peuvent créer des procédures tandis que les utilisateurs standard peuvent uniquement lancer des exécutions."
        ),
        version="0.1.0",
    )
    app.state.settings = settings
    configure_cors(app, settings)
    configure_rate_limiter(app, settings)
    app.add_middleware(CorrelationIdMiddleware)
    return app


settings = get_settings()
app = create_app(settings)


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


@app.get("/", responses=throttle_responses())
@limiter.limit(default_rate_limit)
def read_root(request: Request, response: Response) -> Dict[str, str]:  # noqa: D401 - simple handler
    logger.debug("Root endpoint accessed")
    return {"message": "Bienvenue sur l'API de l'assistant Réalisons v0.1"}


@app.get("/health", responses=throttle_responses())
@limiter.limit(default_rate_limit)
def health_check(request: Request, response: Response) -> Dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "healthy", "version": "0.1.0"}


@app.post("/auth/token", response_model=Token, tags=["auth"], responses=throttle_responses())
@limiter.limit(default_rate_limit)
def login(
    request: Request,
    response: Response,
    form_data=Depends(OAuth2PasswordRequestForm),
) -> Token:
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"sub": user.username, "role": user.role})
    return Token(access_token=access_token)


@app.get("/procedures", response_model=List[Procedure], responses=throttle_responses())
@limiter.limit(default_rate_limit)
def list_procedures(request: Request, response: Response) -> List[Procedure]:
    logger.info("Listing procedures", extra={"total": len(procedures_db)})
    return list(procedures_db.values())


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
    payload: ProcedureCreateRequest = Depends(parse_procedure_request),
    current_user=Depends(require_role("admin")),
) -> Procedure:
    logger.info(
        "Creating procedure",
        extra={"procedure_name": payload.name, "username": current_user.username},
    )
    procedure = Procedure(
        id=str(uuid.uuid4()),
        name=payload.name,
        description=payload.description,
        steps=payload.steps,
    )
    procedures_db[procedure.id] = procedure
    return procedure


@app.get(
    "/procedures/{procedure_id}",
    response_model=Procedure,
    responses=throttle_responses(),
)
@limiter.limit(default_rate_limit)
def get_procedure(request: Request, response: Response, procedure_id: str) -> Procedure:
    logger.info("Fetching procedure", extra={"procedure_id": procedure_id})
    try:
        return procedures_db[procedure_id]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ProcedureNotFoundError("Procedure not found") from exc


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
    procedure_id: str,
    current_user=Depends(require_role("user")),
) -> ProcedureRun:
    if procedure_id not in procedures_db:
        raise HTTPException(status_code=404, detail="Procedure not found")

    run = ProcedureRun(
        id=str(uuid.uuid4()),
        procedure_id=procedure_id,
        user_id=current_user.username,
        state="started",
        created_at=datetime.utcnow(),
    )
    runs_db[run.id] = run
    logger.info(
        "Starting procedure run",
        extra={"procedure_id": procedure_id, "run_id": run.id, "username": current_user.username},
    )
    return run


@app.get("/runs/{run_id}", response_model=ProcedureRun, responses=throttle_responses())
@limiter.limit(default_rate_limit)
def get_run(request: Request, response: Response, run_id: str) -> ProcedureRun:
    logger.info("Fetching run", extra={"run_id": run_id})
    try:
        return runs_db[run_id]
    except KeyError as exc:  # pragma: no cover - defensive
        raise RunNotFoundError("Run not found") from exc


__all__ = [
    "app",
    "procedures_db",
    "runs_db",
    "configure_rate_limiter",
    "create_app",
]
