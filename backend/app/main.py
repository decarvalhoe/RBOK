from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import Token, User, authenticate_user, create_access_token, require_role

logger = logging.getLogger("rbok.api")
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class CorrelationIdFilter(logging.Filter):
    """Inject the correlation id into structured log records."""

    def filter(self, record: logging.LogRecord) -> bool:
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
    """Attach a correlation id and timing information to each request."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
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


class ProcedureStep(BaseModel):
    key: str
    title: str
    prompt: str
    slots: List[Dict[str, str]] = Field(default_factory=list)


class Procedure(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    steps: List[ProcedureStep] = Field(default_factory=list)


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


class ProcedureRunCreateRequest(BaseModel):
    procedure_id: str
    user_id: Optional[str] = None


procedures_db: Dict[str, Procedure] = {}
runs_db: Dict[str, ProcedureRun] = {}


class DomainError(Exception):
    """Base domain exception."""


class ProcedureNotFoundError(DomainError):
    """Raised when the requested procedure does not exist."""


class RunNotFoundError(DomainError):
    """Raised when the requested run does not exist."""


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    logger.warning(
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
    logger.debug("Root endpoint accessed")
    return {"message": "Bienvenue sur l'API de l'assistant Réalisons v0.1"}


@app.get("/health")
def health_check() -> Dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "healthy", "version": app.version or "0.1.0"}


@app.get("/procedures", response_model=List[Procedure])
def list_procedures() -> List[Procedure]:
    logger.info("Listing procedures", extra={"count": len(procedures_db)})
    return list(procedures_db.values())


@app.post("/procedures", response_model=Procedure, status_code=status.HTTP_201_CREATED)
def create_procedure(
    payload: ProcedureCreateRequest,
    current_user: User = Depends(require_role("admin")),
) -> Procedure:
    _ = current_user  # used for dependency side-effects only
    procedure_id = str(uuid.uuid4())
    procedure = Procedure(
        id=procedure_id,
        name=payload.name,
        description=payload.description,
        steps=payload.steps,
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


@app.post("/runs", response_model=ProcedureRun, status_code=status.HTTP_201_CREATED)
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
