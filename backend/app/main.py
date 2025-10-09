from datetime import datetime
import uuid
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from .auth import (
    Token,
    authenticate_user,
    create_access_token,
    require_role,
)

app = FastAPI(
    title="Réalisons API",
    description=(
        "API pour l'assistant procédural Réalisons. "
        "Les opérations d'écriture nécessitent un token Bearer issu de l'endpoint ``/auth/token``. "
        "Les administrateurs peuvent créer des procédures tandis que les utilisateurs standard peuvent uniquement lancer des exécutions."
    ),
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session, selectinload

from . import models
from .database import get_db
from typing import Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware


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

    async def dispatch(self, request: Request, call_next):
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
    slots: List[dict] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
    slots: List[Dict[str, str]] = Field(default_factory=list)


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


# Stockage temporaire en mémoire (à remplacer par une vraie DB)
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
        "Domain error raised",
        extra={"path": request.url.path, "detail": str(exc) or exc.__class__.__name__},
    )
    return JSONResponse(status_code=400, content={"detail": str(exc) or "Bad request"})


@app.get("/")
def read_root():
    logger.debug("Root endpoint accessed")
    return {"message": "Bienvenue sur l'API de l'assistant Réalisons v0.1"}


@app.get("/health")
def health_check():
    logger.debug("Health check requested")
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/procedures", response_model=List[Procedure])
def list_procedures(db: Session = Depends(get_db)):
    procedures = (
        db.query(models.Procedure)
        .options(selectinload(models.Procedure.steps))
        .all()
    )
    return procedures


@app.post("/procedures", response_model=Procedure)
def create_procedure(procedure: Procedure, db: Session = Depends(get_db)):
    procedure_id = procedure.id or str(uuid.uuid4())
    db_procedure = models.Procedure(
        id=procedure_id,
        name=procedure.name,
        description=procedure.description,
    )
    for index, step in enumerate(procedure.steps):
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
    return db_procedure

def list_procedures():
    logger.info("Listing procedures", extra={"total": len(procedures_db)})
    return list(procedures_db.values())

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

@app.post("/procedures", response_model=Procedure, status_code=status.HTTP_201_CREATED)
def create_procedure(
    procedure: Procedure,
    current_user=Depends(require_role("admin")),
):
    procedure.id = str(uuid.uuid4())

@app.post("/procedures", response_model=Procedure)
def create_procedure(payload: ProcedureCreateRequest):
    logger.info("Creating procedure", extra={"name": payload.name})
    procedure = Procedure(
        id=str(uuid.uuid4()),
        name=payload.name,
        description=payload.description,
        steps=payload.steps,
    )
    procedures_db[procedure.id] = procedure
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


@app.post("/runs", response_model=ProcedureRun)
def start_procedure_run(
    procedure_id: str,
    user_id: str = "default_user",
    db: Session = Depends(get_db),
):
    procedure_exists = db.query(models.Procedure.id).filter(models.Procedure.id == procedure_id).first()
    if not procedure_exists:
        raise HTTPException(status_code=404, detail="Procedure not found")

    run = models.ProcedureRun(
def get_procedure(procedure_id: str):
    logger.info("Fetching procedure", extra={"procedure_id": procedure_id})
    try:
        return procedures_db[procedure_id]
    except KeyError as exc:
        raise ProcedureNotFoundError("Procedure not found") from exc


@app.post("/runs", response_model=ProcedureRun, status_code=status.HTTP_201_CREATED)
def start_procedure_run(
    procedure_id: str,
    current_user=Depends(require_role("user")),
):
    if procedure_id not in procedures_db:
        raise HTTPException(status_code=404, detail="Procedure not found")

    run = ProcedureRun(
        id=str(uuid.uuid4()),
        procedure_id=procedure_id,
        user_id=current_user.username,
@app.post("/runs", response_model=ProcedureRun)
def start_procedure_run(payload: ProcedureRunCreateRequest):
    logger.info(
        "Starting procedure run",
        extra={"procedure_id": payload.procedure_id, "user_id": payload.user_id},
    )
    if payload.procedure_id not in procedures_db:
        raise ProcedureNotFoundError("Procedure not found")

    run = ProcedureRun(
        id=str(uuid.uuid4()),
        procedure_id=payload.procedure_id,
        user_id=payload.user_id or "default_user",
        state="started",
        created_at=datetime.now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@app.get("/runs/{run_id}", response_model=ProcedureRun)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(models.ProcedureRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
def get_run(run_id: str):
    logger.info("Fetching run", extra={"run_id": run_id})
    try:
        return runs_db[run_id]
    except KeyError as exc:
        raise RunNotFoundError("Run not found") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
