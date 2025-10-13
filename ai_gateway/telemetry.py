"""Telemetry helpers for the AI gateway."""
from __future__ import annotations

import os
from contextvars import ContextVar, Token
from typing import Dict, Optional

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
_tracing_configured = False


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


def configure_tracing(app: FastAPI, service_name: str) -> None:
    """Initialise OpenTelemetry tracing for the FastAPI application."""

    global _tracing_configured
    if _tracing_configured:
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
    exporter = OTLPSpanExporter(
        endpoint=f"{endpoint.rstrip('/')}/v1/traces",
        headers=_parse_otlp_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS")) or None,
    )
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name}),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor().instrument_app(app, tracer_provider=provider)
    _tracing_configured = True


def get_correlation_id() -> Optional[str]:
    """Return the current correlation identifier if set."""

    return correlation_id_var.get()


def set_correlation_id(value: str) -> Token:
    """Attach a correlation identifier to the current context."""

    return correlation_id_var.set(value)


def reset_correlation_id(token: Token) -> None:
    """Reset the correlation identifier to the previous context value."""

    correlation_id_var.reset(token)
