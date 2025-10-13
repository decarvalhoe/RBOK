from __future__ import annotations

"""FastAPI entry-point for the Réalisons backend."""

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from .api.webrtc import router as webrtc_router
from .cache import get_redis_client
from .config import Settings, get_settings
from .database import engine, get_db
from .env import analyse_environment, validate_environment

logger = logging.getLogger("rbok.api")
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class CorrelationIdFilter(logging.Filter):
    """Inject the correlation identifier into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging helper
        record.correlation_id = correlation_id_var.get() or "unknown"
        return True


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s [correlation_id=%(correlation_id)s] %(message)s",
    )
    logging.getLogger().addFilter(CorrelationIdFilter())
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):  # type: ignore[override]
        record = old_factory(*args, **kwargs)
        if not hasattr(record, "correlation_id"):
            record.correlation_id = correlation_id_var.get() or "unknown"
        return record

    logging.setLogRecordFactory(record_factory)


configure_logging()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach correlation identifiers and timing information to responses."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        token = correlation_id_var.set(correlation_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled exception during request", extra={"path": request.url.path})
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            correlation_id_var.reset(token)
            logger.info(
                "Request completed",
                extra={"path": request.url.path, "method": request.method, "duration_ms": round(duration_ms, 2)},
            )
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time-ms"] = f"{duration_ms:.2f}"
        return response


app = FastAPI(title="Réalisons API", version="0.3.0")


settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)
app.include_router(webrtc_router)


REQUEST_DURATION = Histogram(
    "backend_request_duration_seconds",
    "Time spent processing requests",
    labelnames=("method", "path", "status_code"),
)
REQUEST_COUNT = Counter(
    "backend_request_total",
    "Total number of processed requests",
    labelnames=("method", "path", "status_code"),
)
DATABASE_HEALTH = Gauge(
    "backend_database_up",
    "Database connectivity status (1=up, 0=down)",
)
CACHE_HEALTH = Gauge(
    "backend_cache_up",
    "Cache connectivity status (1=up, 0=down)",
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):  # type: ignore[override]
    if request.url.path == "/metrics":
        return await call_next(request)

    start_time = time.perf_counter()
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        elapsed = time.perf_counter() - start_time
        labels = {
            "method": request.method,
            "path": request.url.path,
            "status_code": str(status_code),
        }
        REQUEST_DURATION.labels(**labels).observe(elapsed)
        REQUEST_COUNT.labels(**labels).inc()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096)


class ChatResponse(BaseModel):
    role: str = "assistant"
    content: str


@app.get("/")
async def root() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    """Return missing or insecure configuration details."""

    analysis = analyse_environment()
    return {"status": "ok", "missing": analysis["missing"], "insecure": analysis["insecure"]}


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    """Return a canned assistant response for demo purposes."""

    reply = f"Message reçu: {payload.message.strip()}"
    logger.info("Chat message processed", extra={"length": len(payload.message)})
    return ChatResponse(content=reply)


@app.get("/config/webrtc", response_class=JSONResponse)
async def get_webrtc_public_config(settings: Settings = Depends(get_settings)) -> JSONResponse:
    """Expose ICE server configuration (alias for compatibility)."""

    if not settings.webrtc_stun_servers and not settings.webrtc_turn_servers:
        return JSONResponse({"ice_servers": []})

    ice_servers: List[Dict[str, Any]] = []
    if settings.webrtc_stun_servers:
        ice_servers.append({"urls": settings.webrtc_stun_servers})
    if settings.webrtc_turn_servers:
        ice_servers.append(
            {
                "urls": settings.webrtc_turn_servers,
                "username": settings.webrtc_turn_username,
                "credential": settings.webrtc_turn_password,
            }
        )
    return JSONResponse({"ice_servers": ice_servers})


def _refresh_dependency_metrics() -> None:
    """Update gauges describing database and cache health."""

    db_status = 0
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_status = 1
    except Exception as exc:  # pragma: no cover - defensive monitoring path
        logger.warning("Database health probe failed", exc_info=exc)
    DATABASE_HEALTH.set(db_status)

    cache_status = 0
    try:
        redis_client = get_redis_client()
        redis_client.ping()
        cache_status = 1
    except Exception as exc:  # pragma: no cover - defensive monitoring path
        logger.warning("Cache health probe failed", exc_info=exc)
    CACHE_HEALTH.set(cache_status)


@app.get("/metrics")
async def metrics() -> Response:
    _refresh_dependency_metrics()
    payload = generate_latest()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


__all__ = ["app", "get_db"]
