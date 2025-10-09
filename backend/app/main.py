"""FastAPI application for the Réalisons backend."""
from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.middleware.base import BaseHTTPMiddleware

from . import models
from .auth import Token, authenticate_user, create_access_token, require_role
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

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging plumbing
        record.correlation_id = correlation_id_var.get() or "unknown"
        return True


def configure_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s [correlation_id=%(correlation_id)s] %(message)s",
    )
    previous_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):  # type: ignore[override]
        record = previous_factory(*args, **kwargs)
        if not hasattr(record, "correlation_id"):
            record.correlation_id = "unknown"
        return record

    logging.setLogRecordFactory(record_factory)
    logger = logging.getLogger("realison.api")
    logger.addFilter(CorrelationIdFilter())
    logging.getLogger().addFilter(CorrelationIdFilter())
    return logger


logger = configure_logging()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach correlation ids and timing information to each request."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        token = correlation_id_var.set(correlation_id)
        start_time = time.perf_counter()
        response = None
        try:
            logger.info("Handling request", extra={"path": request.url.path, "method": request.method})
            response = await call_next(request)
        except Exception:  # pragma: no cover - defensive logging
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
    user_id: Optional[str] = Field(default=None)


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
async def read_root() -> Dict[str, str]:
    logger.debug("Root endpoint accessed")
    return {"message": "Bienvenue sur l'API de l'assistant Réalisons v0.1"}


@app.get("/health")
async def health_check() -> Dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "healthy", "version": "0.1.0"}


@app.post("/auth/token", response_model=Token, tags=["auth"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
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
async def list_procedures(db: AsyncSession = Depends(get_db)) -> List[models.Procedure]:
    result = await db.execute(
        select(models.Procedure).options(selectinload(models.Procedure.steps))
    )
    procedures = result.scalars().unique().all()
    return procedures


@app.post("/procedures", response_model=Procedure, status_code=status.HTTP_201_CREATED)
async def create_procedure(
    payload: ProcedureCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role("admin")),
) -> models.Procedure:
    procedure = models.Procedure(
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
    await db.commit()
    result = await db.execute(
        select(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .where(models.Procedure.id == procedure.id)
    )
    created = result.scalars().unique().one()
    return created


@app.get("/procedures/{procedure_id}", response_model=Procedure)
async def get_procedure(procedure_id: str, db: AsyncSession = Depends(get_db)) -> models.Procedure:
    result = await db.execute(
        select(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .where(models.Procedure.id == procedure_id)
    )
    try:
        procedure = result.scalars().unique().one()
    except NoResultFound as exc:
        raise HTTPException(status_code=404, detail="Procedure not found") from exc
    return procedure


@app.post("/runs", response_model=ProcedureRun, status_code=status.HTTP_201_CREATED)
async def start_procedure_run(
    payload: ProcedureRunCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role("user")),
) -> models.ProcedureRun:
    procedure = await db.get(models.Procedure, payload.procedure_id)
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    run = models.ProcedureRun(
        procedure_id=payload.procedure_id,
        user_id=payload.user_id or current_user.username,
        state="started",
        created_at=datetime.utcnow(),
    )

    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


@app.get("/runs/{run_id}", response_model=ProcedureRun)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)) -> models.ProcedureRun:
    run = await db.get(models.ProcedureRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
