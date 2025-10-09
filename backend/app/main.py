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
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.base import BaseHTTPMiddleware

from . import models
from .auth import (
    Token,
    TokenIntrospection,
    User,
    authorize_action,
    introspect_access_token,
    password_grant,
    refresh_access_token,
    require_role,
)
from .database import get_db


class DomainError(Exception):
    """Base class for domain-level errors."""


class NotFoundError(DomainError):
    """Raised when an entity cannot be located."""


class ProcedureNotFoundError(NotFoundError):
    """Raised when a procedure cannot be found."""


class RunNotFoundError(NotFoundError):
    """Raised when a run cannot be found."""


correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class CorrelationIdFilter(logging.Filter):
    """Inject the current correlation id into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 - FastAPI style
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
    """Attach correlation ids and simple timing information to each request."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        token = correlation_id_var.set(correlation_id)
        start_time = time.perf_counter()
        response = None
        try:
            logger.info("Handling request", extra={"path": request.url.path, "method": request.method})
            response = await call_next(request)
        except Exception:  # noqa: BLE001 - re-raised after logging
            logger.exception(
                "Unhandled exception during request",
                extra={"path": request.url.path, "method": request.method},
            )
            raise
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
    description=(
        "API pour l'assistant procédural Réalisons. "
        "Les opérations sensibles requièrent une authentification Keycloak et sont vérifiées via OPA."
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
    user_id: Optional[str] = Field(default="default_user")


# In-memory placeholders kept for backward-compatible tests
procedures_db: Dict[str, Procedure] = {}
runs_db: Dict[str, ProcedureRun] = {}


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
        "Domain error",
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
    return {"status": "healthy", "version": app.version}


@app.post("/auth/token", response_model=Token, tags=["auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        return password_grant(form_data.username, form_data.password)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive branch
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication upstream failed",
        ) from exc


@app.post("/auth/refresh", response_model=Token, tags=["auth"])
def refresh(token: str = Body(..., embed=True)):
    try:
        return refresh_access_token(token)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive branch
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Token refresh failed",
        ) from exc


@app.post("/auth/introspect", response_model=TokenIntrospection, tags=["auth"])
def introspect(token: str = Body(..., embed=True)):
    try:
        return introspect_access_token(token)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive branch
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Token introspection failed",
        ) from exc


@app.get("/procedures", response_model=List[Procedure])
def list_procedures(db: Session = Depends(get_db)):
    procedures = (
        db.query(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .all()
    )
    return procedures


@app.post("/procedures", response_model=Procedure, status_code=status.HTTP_201_CREATED)
def create_procedure(
    payload: ProcedureCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
    _: User = Depends(authorize_action("procedures:create")),
):
    logger.info("Creating procedure", extra={"name": payload.name, "user": current_user.username})
    procedure = models.Procedure(name=payload.name, description=payload.description)
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
    procedures_db[procedure.id] = Procedure.model_validate(procedure)
    return procedure


@app.get("/procedures/{procedure_id}", response_model=Procedure)
def get_procedure(procedure_id: str, db: Session = Depends(get_db)):
    procedure = (
        db.query(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .filter(models.Procedure.id == procedure_id)
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")
    return procedure


@app.post("/runs", response_model=ProcedureRun, status_code=status.HTTP_201_CREATED)
def start_procedure_run(
    payload: ProcedureRunCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user")),
    _: User = Depends(authorize_action("runs:start")),
):
    procedure_exists = db.query(models.Procedure.id).filter(models.Procedure.id == payload.procedure_id).first()
    if not procedure_exists:
        raise HTTPException(status_code=404, detail="Procedure not found")

    run = models.ProcedureRun(
        procedure_id=payload.procedure_id,
        user_id=payload.user_id or current_user.username,
        state="started",
        created_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    runs_db[run.id] = ProcedureRun.model_validate(run)
    return run


@app.get("/runs/{run_id}", response_model=ProcedureRun)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(models.ProcedureRun).filter(models.ProcedureRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/runs/{run_id}/status", response_model=ProcedureRun)
def get_run_status(run_id: str):
    try:
        return runs_db[run_id]
    except KeyError as exc:
        raise RunNotFoundError("Run not found") from exc