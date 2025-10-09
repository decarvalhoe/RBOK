from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.base import BaseHTTPMiddleware

from . import models
from .auth import Token, authenticate_user, create_access_token, require_role
from .database import get_db
from .env import analyse_environment, validate_environment

load_dotenv()

logger = logging.getLogger("realisons.backend")
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach correlation identifiers to every request."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        token = correlation_id_var.set(correlation_id)
        start_time = time.perf_counter()
        response = None
        try:
            logger.info("Handling request", extra={"path": request.url.path, "method": request.method})
            response = await call_next(request)
            return response
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


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s [correlation_id=%(correlation_id)s] %(message)s",
    )
    logging.getLogger().addFilter(lambda record: setattr(record, "correlation_id", correlation_id_var.get()) or True)


configure_logging()


class ProcedureStep(BaseModel):
    key: str
    title: str
    prompt: str
    slots: List[dict] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class Procedure(BaseModel):
    id: Optional[str] = None
    name: str
    description: str
    steps: List[ProcedureStep] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ProcedureCreateRequest(Procedure):
    pass


class ProcedureRun(BaseModel):
    id: str
    procedure_id: str
    user_id: str
    state: str
    created_at: datetime
    closed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ProcedureRunCreateRequest(BaseModel):
    procedure_id: str
    user_id: Optional[str] = None


procedures_db: Dict[str, Procedure] = {}
runs_db: Dict[str, ProcedureRun] = {}

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


@app.on_event("startup")
def ensure_environment() -> None:
    """Validate configuration as soon as the application starts."""

    validate_environment()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover - safety net
    logger.exception("Unhandled error", extra={"path": request.url.path})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/healthz")
def health_check() -> Dict[str, object]:
    """Return environment validation information for monitoring."""

    issues = analyse_environment()
    status_value = "ok" if not issues["missing"] and not issues["insecure"] else "degraded"
    return {"status": status_value, **issues}


@app.get("/health")
def legacy_health() -> Dict[str, str]:
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/")
def read_root() -> Dict[str, str]:
    return {"message": "Bienvenue sur l'API de l'assistant Réalisons v0.1"}


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


@app.get("/procedures", response_model=List[Procedure])
def list_procedures(db: Session = Depends(get_db)) -> List[Procedure]:
    procedures = (
        db.query(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .all()
    )
    return procedures


@app.post("/procedures", response_model=Procedure)
def create_procedure(payload: ProcedureCreateRequest, db: Session = Depends(get_db)) -> Procedure:
    procedure_id = payload.id or str(uuid.uuid4())
    db_procedure = models.Procedure(
        id=procedure_id,
        name=payload.name,
        description=payload.description,
    )
    for index, step in enumerate(payload.steps):
        db_procedure.steps.append(
            models.ProcedureStep(
                key=step.key,
                title=step.title,
                prompt=step.prompt,
                slots=step.slots,
                position=index,
            )
        )
    db.add(db_procedure)
    db.commit()
    db.refresh(db_procedure)

    procedures_db[procedure_id] = Procedure.model_validate(db_procedure)
    return db_procedure


@app.get("/procedures/{procedure_id}", response_model=Procedure)
def get_procedure(procedure_id: str, db: Session = Depends(get_db)) -> Procedure:
    procedure = (
        db.query(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .filter(models.Procedure.id == procedure_id)
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")
    procedures_db[procedure_id] = Procedure.model_validate(procedure)
    return procedure


@app.post("/runs", response_model=ProcedureRun)
def start_procedure_run(
    procedure_id: Optional[str] = None,
    user_id: Optional[str] = None,
    payload: ProcedureRunCreateRequest | None = Body(default=None),
    db: Session = Depends(get_db),
):
    procedure_id = procedure_id or (payload.procedure_id if payload else None)
    user_id = user_id or (payload.user_id if payload else None) or "default_user"

    if not procedure_id:
        raise HTTPException(status_code=422, detail="procedure_id is required")

    exists_in_cache = procedure_id in procedures_db
    exists_in_db = False
    try:
        exists_in_db = bool(
            db.query(models.Procedure.id).filter(models.Procedure.id == procedure_id).first()
        )
    except OperationalError:
        exists_in_db = False

    if not exists_in_cache and not exists_in_db:
        raise HTTPException(status_code=404, detail="Procedure not found")

    run = models.ProcedureRun(
        id=str(uuid.uuid4()),
        procedure_id=procedure_id,
        user_id=user_id,
        state="started",
        created_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    run_payload = ProcedureRun.model_validate(run)
    runs_db[run.id] = run_payload
    return run


@app.get("/runs/{run_id}", response_model=ProcedureRun)
def get_run(run_id: str, db: Session = Depends(get_db)) -> ProcedureRun:
    run = db.get(models.ProcedureRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    runs_db[run_id] = ProcedureRun.model_validate(run)
    return run


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
