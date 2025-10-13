from __future__ import annotations

"""FastAPI entry-point for the Réalisons backend."""

import logging
import os
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings, get_settings
from .database import get_db
from .env import analyse_environment, validate_environment
from .api.webrtc import router as webrtc_router
from .observability import Observability

logger = logging.getLogger("rbok.api")
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
_tracing_configured = False


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


def _parse_otlp_headers(raw_value: Optional[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if not raw_value:
        return headers
    for item in raw_value.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            continue
        headers[key] = value.strip()
    return headers


def configure_tracing(app: FastAPI) -> None:
    """Initialise OpenTelemetry tracing for the service."""

    global _tracing_configured
    if _tracing_configured:
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
    exporter = OTLPSpanExporter(
        endpoint=f"{endpoint.rstrip('/')}/v1/traces",
        headers=_parse_otlp_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS")) or None,
    )
    provider = TracerProvider(
        resource=Resource.create({"service.name": "rbok-backend"}),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor().instrument_app(app, tracer_provider=provider)
    _tracing_configured = True


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
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            current_span.set_attribute("correlation.id", correlation_id)
            current_span.set_attribute("http.server_duration_ms", round(duration_ms, 2))
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time-ms"] = f"{duration_ms:.2f}"
        return response


app = FastAPI(title="Réalisons API", version="0.3.0")
configure_tracing(app)

telemetry = Observability(app, service_name="rbok-backend")
app.state.telemetry = telemetry


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


__all__ = ["app", "get_db"]
