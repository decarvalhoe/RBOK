"""Observability helpers used by the backend service."""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    CONTENT_TYPE_LATEST,
    generate_latest,
)
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace.status import Status, StatusCode


class Observability:
    """Set up Prometheus metrics and OpenTelemetry tracing for a FastAPI app."""

    def __init__(
        self,
        app: FastAPI,
        service_name: str,
        *,
        registry: Optional[CollectorRegistry] = None,
        exporter: Optional[SpanExporter] = None,
    ) -> None:
        self.app = app
        self.service_name = service_name
        self.registry = registry or CollectorRegistry()
        self._request_counter: Counter
        self._request_duration: Histogram
        self._in_progress: Gauge
        self._provider: TracerProvider | None = None
        self._processors: list[SimpleSpanProcessor] = []
        self._trace_records: List[Dict[str, object]] = []

        self._install_metrics()
        self.configure_tracer(exporter)

        # Register middleware once – FastAPI ensures middlewares are called in
        # the order of registration so we keep it near the top of the stack.
        self.app.middleware("http")(self._observe_request)

        if not any(route.path == "/metrics" for route in self.app.routes):
            self.app.add_api_route(
                "/metrics",
                self._metrics_endpoint,
                methods=["GET"],
                include_in_schema=False,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def configure_tracer(self, exporter: Optional[SpanExporter] = None) -> TracerProvider:
        """Attach a span exporter, creating the provider if necessary."""

        current = trace.get_tracer_provider()
        if not isinstance(current, TracerProvider) or getattr(current, "_rbok_service", None) != self.service_name:
            provider = TracerProvider(
                resource=Resource.create({"service.name": self.service_name})
            )
            setattr(provider, "_rbok_service", self.service_name)
            replaced = False
            try:
                trace.set_tracer_provider(provider)
                replaced = trace.get_tracer_provider() is provider
            except RuntimeError:
                replaced = False
            current_provider = trace.get_tracer_provider()
            if not isinstance(current_provider, TracerProvider):  # pragma: no cover - defensive
                raise RuntimeError("Tracer provider not available")
            provider = current_provider
            if replaced:
                self._processors.clear()
            setattr(provider, "_rbok_service", getattr(provider, "_rbok_service", self.service_name))
            self._provider = provider
        else:
            provider = current
            self._provider = provider

        processor_exporter: SpanExporter = exporter or ConsoleSpanExporter()
        processor = SimpleSpanProcessor(processor_exporter)
        self._processors.append(processor)
        provider.add_span_processor(processor)
        return provider

    def reset_metrics(self, registry: Optional[CollectorRegistry] = None) -> None:
        """Reset the Prometheus registry, useful for isolating tests."""

        self.registry = registry or CollectorRegistry()
        self._install_metrics()

    def reset_traces(self) -> None:
        """Clear recorded trace snapshots (used by tests)."""

        self._trace_records.clear()

    def get_trace_records(self) -> List[Dict[str, object]]:
        """Return a shallow copy of the collected trace summaries."""

        return list(self._trace_records)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _install_metrics(self) -> None:
        self._request_counter = Counter(
            "rbok_http_requests_total",
            "Total number of HTTP requests",
            labelnames=["service", "method", "route", "status_code"],
            registry=self.registry,
        )
        self._request_duration = Histogram(
            "rbok_http_request_duration_seconds",
            "Latency of HTTP requests",
            labelnames=["service", "method", "route"],
            registry=self.registry,
        )
        self._in_progress = Gauge(
            "rbok_http_requests_in_progress",
            "Number of in-flight HTTP requests",
            labelnames=["service", "method", "route"],
            registry=self.registry,
        )

    async def _observe_request(self, request: Request, call_next):  # type: ignore[override]
        tracer_provider = self._provider or trace.get_tracer_provider()
        tracer = tracer_provider.get_tracer(self.service_name)
        start = time.perf_counter()
        route = self._resolve_route(request)
        labels = {
            "service": self.service_name,
            "method": request.method,
            "route": route,
        }

        self._in_progress.labels(**labels).inc()
        status_code = 500
        try:
            with tracer.start_as_current_span(
                "http.request",
                attributes={
                    "http.method": request.method,
                    "http.target": route,
                    "service.name": self.service_name,
                },
            ) as span:
                try:
                    response = await call_next(request)
                except Exception as exc:  # pragma: no cover - exercised in tests indirectly
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR))
                    raise
                else:
                    status_code = response.status_code
                    span.set_attribute("http.status_code", status_code)
                    duration_ms = (time.perf_counter() - start) * 1000
                    span.set_attribute("http.server.duration_ms", duration_ms)
                    return response
        finally:
            duration = time.perf_counter() - start
            self._request_counter.labels(**labels, status_code=str(status_code)).inc()
            self._request_duration.labels(**labels).observe(duration)
            self._in_progress.labels(**labels).dec()
            self._trace_records.append(
                {
                    "service": self.service_name,
                    "method": request.method,
                    "route": route,
                    "status_code": status_code,
                    "duration": duration,
                }
            )
            if len(self._trace_records) > 50:
                self._trace_records.pop(0)

    def _metrics_endpoint(self) -> Response:
        payload = generate_latest(self.registry)
        return Response(payload, media_type=CONTENT_TYPE_LATEST)

    @staticmethod
    def _resolve_route(request: Request) -> str:
        route = request.scope.get("route")
        if route and getattr(route, "path", None):
            return route.path  # type: ignore[return-value]
        return request.url.path


__all__ = ["Observability"]
