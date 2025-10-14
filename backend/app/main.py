from __future__ import annotations

"""FastAPI entry-point for the Réalisons backend."""

import logging
import os
import time
import uuid
from contextvars import ContextVar
from typing import Any, Callable, Dict, List, Optional

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, REGISTRY, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, unbind_contextvars
from structlog.stdlib import ProcessorFormatter

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk._logs import LoggingHandler, LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from .api.procedures import router as procedures_router
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk._logs import LoggingHandler, LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .api.auth import router as auth_router
from .api.procedures import router as procedures_router
from .api.runs import router as runs_router
from .api.webrtc import router as webrtc_router
from .cache import get_redis_client
from .config import Settings, get_settings
from .database import engine, get_db
from .env import analyse_environment, validate_environment
from .observability import Observability

logger = logging.getLogger("rbok.api")
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
_tracing_configured = False


class CorrelationIdFilter(logging.Filter):
    """Inject the correlation identifier into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging helper
        record.correlation_id = correlation_id_var.get() or "unknown"
        return True


def _add_correlation_id(
    _: Any,
    __: str,
    event_dict: Dict[str, Any],
) -> Dict[str, Any]:  # pragma: no cover - logging helper
    event_dict.setdefault("correlation_id", correlation_id_var.get() or "unknown")
    return event_dict


def _configure_otlp_logging(service_name: str) -> None:
    """Attach an OTLP handler when OTLP environment variables are provided."""

    if not (
        os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        or os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
    ):
        return

    root_logger = logging.getLogger()
    try:
        resource = Resource.create(
            {"service.name": os.getenv("OTEL_SERVICE_NAME", service_name)}
        )
        logger_provider = LoggerProvider(resource=resource)
        exporter = OTLPLogExporter()
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
        set_logger_provider(logger_provider)
        otlp_handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
        root_logger.addHandler(otlp_handler)
        root_logger.debug(
            "OTLP log exporter configured",
            extra={"service_name": resource.attributes.get("service.name")},
        )
    except Exception:  # pragma: no cover - defensive
        root_logger.exception("Failed to configure OTLP log exporter")


def configure_logging(service_name: str = "rbok-backend") -> None:
    """Configure structured logging with correlation identifiers."""

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _add_correlation_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.format_exc_info,
    ]

    formatter = ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(CorrelationIdFilter())

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):  # type: ignore[override]
        record = old_factory(*args, **kwargs)
        if not hasattr(record, "correlation_id"):
            record.correlation_id = correlation_id_var.get() or "unknown"
        return record

    logging.setLogRecordFactory(record_factory)

    structlog.configure(
        processors=shared_processors + [ProcessorFormatter.wrap_for_formatter],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    _configure_otlp_logging(service_name)


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

    current_provider = trace.get_tracer_provider()
    if isinstance(current_provider, TracerProvider) and getattr(
        current_provider, "_rbok_service", None
    ) == "rbok-backend":
        _tracing_configured = True
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        _tracing_configured = True
        return

    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider) and getattr(current, "_rbok_service", None) == "rbok-backend":
        _tracing_configured = True
    if not (
        os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    ):
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
    exporter = OTLPSpanExporter(
        endpoint=f"{endpoint.rstrip('/')}/v1/traces",
        headers=_parse_otlp_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS")) or None,
    )
    provider = TracerProvider(
        resource=Resource.create({"service.name": "rbok-backend"}),
    )
    setattr(provider, "_rbok_service", "rbok-backend")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor().instrument_app(app, tracer_provider=provider)
    _tracing_configured = True


def configure_rate_limiter(app: FastAPI, settings: Settings) -> None:
    """Configure SlowAPI rate limiting according to runtime settings."""

    default_limits: List[str] = []
    if settings.rate_limit_default:
        default_limits = [settings.rate_limit_default]

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=default_limits,
        headers_enabled=settings.rate_limit_headers_enabled,
        enabled=settings.rate_limit_enabled,
    )
    app.state.limiter = limiter

    if not any(middleware.cls is SlowAPIMiddleware for middleware in app.user_middleware):
        app.add_middleware(SlowAPIMiddleware)

    async def rate_limit_exceeded_handler(
        request: Request, exc: RateLimitExceeded
    ) -> JSONResponse:
        response = JSONResponse(
            {"error": f"Rate limit exceeded: {exc.detail}"},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

        if settings.rate_limit_headers_enabled:
            current_limit = getattr(request.state, "view_rate_limit", None)
            if current_limit is not None:
                response = limiter._inject_headers(response, current_limit)
            elif exc.limit is not None and exc.limit.limit is not None:
                response.headers.setdefault(
                    "X-RateLimit-Limit", str(exc.limit.limit.amount)
                )
                retry_after = exc.limit.limit.get_expiry()
                response.headers.setdefault("Retry-After", str(retry_after))

        return response

    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach correlation identifiers and timing information to responses."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        token = correlation_id_var.set(correlation_id)
        bind_contextvars(correlation_id=correlation_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled exception during request", extra={"path": request.url.path})
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            correlation_id_var.reset(token)
            unbind_contextvars("correlation_id")
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
configure_rate_limiter(app, settings)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)
app.include_router(auth_router)
app.include_router(procedures_router)
app.include_router(runs_router)
app.include_router(webrtc_router)


def _get_or_create_metric(name: str, factory: Callable[[], Any]):
    try:
        return factory()
    except ValueError as exc:  # pragma: no cover - defensive for reloads
        if "Duplicated timeseries" in str(exc):
            existing = REGISTRY._names_to_collectors.get(name)
            if existing is not None:
                return existing
        raise


REQUEST_DURATION = _get_or_create_metric(
    "backend_request_duration_seconds",
    lambda: Histogram(
        "backend_request_duration_seconds",
        "Time spent processing requests",
        labelnames=("method", "path", "status_code"),
    ),
)
REQUEST_COUNT = _get_or_create_metric(
    "backend_request_total",
    lambda: Counter(
        "backend_request_total",
        "Total number of processed requests",
        labelnames=("method", "path", "status_code"),
    ),
)
DATABASE_HEALTH = _get_or_create_metric(
    "backend_database_up",
    lambda: Gauge(
        "backend_database_up",
        "Database connectivity status (1=up, 0=down)",
    ),
)
CACHE_HEALTH = _get_or_create_metric(
    "backend_cache_up",
    lambda: Gauge(
        "backend_cache_up",
        "Cache connectivity status (1=up, 0=down)",
    ),
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


@app.get(
    "/",
    tags=["Monitoring"],
    summary="Lightweight heartbeat endpoint",
    response_model=Dict[str, str],
    description="""Simple probe that confirms the API process is running.""",
)
async def root() -> Dict[str, str]:
    """Return a minimal payload to indicate service availability."""

    return {"status": "ok"}


@app.get(
    "/health",
    include_in_schema=False,
    tags=["Monitoring"],
    summary="Legacy health endpoint",
)
async def health() -> Dict[str, Any]:
    """Backward compatible alias for :func:`healthz`."""

    return await healthz()


@app.get(
    "/healthz",
    tags=["Monitoring"],
    summary="Comprehensive service diagnostics",
    response_model=Dict[str, Any],
    description="""Report missing environment variables and insecure defaults.""",
)
async def healthz() -> Dict[str, Any]:
    """Return missing or insecure configuration details."""

    analysis = analyse_environment()
    return {"status": "ok", "missing": analysis["missing"], "insecure": analysis["insecure"]}


@app.post(
    "/chat",
    response_model=ChatResponse,
    tags=["Chat"],
    summary="Send a prompt to the demo assistant",
    description="""Echo the received message to validate the chat pipeline.""",
)
async def chat(payload: ChatRequest) -> ChatResponse:
    """Return a canned assistant response for demo purposes."""

    reply = f"Message reçu: {payload.message.strip()}"
    logger.info("Chat message processed", extra={"length": len(payload.message)})
    return ChatResponse(content=reply)


@app.get(
    "/config/webrtc",
    response_class=JSONResponse,
    tags=["WebRTC"],
    summary="Retrieve public WebRTC configuration",
    description="""Expose ICE server configuration consumed by the front-end.""",
)
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


@app.get(
    "/metrics",
    tags=["Monitoring"],
    summary="Prometheus scrape target",
    description="""Expose service metrics in the Prometheus text format.""",
)
async def metrics() -> Response:
    _refresh_dependency_metrics()
    payload = generate_latest()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


__all__ = ["app", "configure_rate_limiter", "get_db"]
