"""Smoke tests ensuring telemetry endpoints produce expected signals."""
from __future__ import annotations

from typing import Dict, List

from prometheus_client.parser import text_string_to_metric_families
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def _metrics_by_sample(metrics_text: str) -> Dict[str, List]:
    samples: Dict[str, List] = {}
    for family in text_string_to_metric_families(metrics_text):
        for sample in family.samples:
            samples.setdefault(sample.name, []).append(sample)
    return samples


def test_metrics_and_traces_exposed(client) -> None:
    telemetry = client.app.state.telemetry
    telemetry.reset_metrics()

    exporter = InMemorySpanExporter()
    telemetry.configure_tracer(exporter)
    exporter.clear()

    response = client.get("/healthz")
    assert response.status_code == 200

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200

    samples = _metrics_by_sample(metrics_response.text)

    request_sample = next(
        sample
        for sample in samples["rbok_http_requests_total"]
        if sample.labels["service"] == "rbok-backend"
        and sample.labels["route"] == "/healthz"
        and sample.labels["method"] == "GET"
    )
    assert request_sample.value >= 1

    assert any(
        sample.labels["route"] == "/healthz" and sample.labels["service"] == "rbok-backend"
        for sample in samples["rbok_http_request_duration_seconds_bucket"]
    )

    gauge_sample = next(
        sample
        for sample in samples["rbok_http_requests_in_progress"]
        if sample.labels["route"] == "/healthz"
        and sample.labels["service"] == "rbok-backend"
        and sample.labels["method"] == "GET"
    )
    assert gauge_sample.value == 0.0

    spans = exporter.get_finished_spans()
    assert any(span.attributes.get("http.target") == "/healthz" for span in spans)

    telemetry.configure_tracer()
