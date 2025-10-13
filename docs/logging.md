# Logging and Observability

The backend API and the AI Gateway now emit JSON logs through [`structlog`](https://www.structlog.org/) and can optionally forward them to an OpenTelemetry (OTLP) collector. Structured logging is configured in `backend/app/main.py` and `ai_gateway/main.py` with the following behaviour:

- **JSON payloads** – Log records are rendered as JSON and include the timestamp (`timestamp`), level (`level`), logger name (`logger`), message (`event`) and any keyword context.
- **Correlation IDs everywhere** – The `CorrelationIdMiddleware` on both services reads the optional `X-Correlation-ID` header (generating a UUID when absent), stores it in a context variable and returns it in the response headers. The middleware also binds the value into Structlog's context so all downstream log calls – including the AI Gateway's HTTP client when it talks to the backend – inherit the same `correlation_id` field.
- **Request timing** – Each request produces a `Request completed` entry with the HTTP method, path and duration in milliseconds alongside the correlation identifier. The same latency value is exposed in the `X-Process-Time-ms` response header.
- **Error reporting** – Unhandled exceptions are logged with stack traces. Domain-specific errors remain mapped to appropriate HTTP responses, ensuring failure details are visible in observability tooling.

## Shipping logs via OTLP

Both services look for standard OTLP environment variables and, when set, attach an OpenTelemetry log handler. The most important settings are:

| Variable | Purpose |
| --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | URL of the collector (e.g. `https://otel.example.com:4318`). Set one of them to enable exporting. |
| `OTEL_EXPORTER_OTLP_HEADERS` / `OTEL_EXPORTER_OTLP_LOGS_HEADERS` | Optional authentication headers, expressed as `key=value` pairs separated by commas. |
| `OTEL_SERVICE_NAME` | Friendly identifier for the emitting service. Defaults to `rbok-backend` for the API and `rbok-ai-gateway` for the gateway when unset. |

When none of the OTLP endpoints are provided, the applications continue to write JSON logs to standard output only.

## Verifying correlation across services

1. Export the OTLP configuration (or run a local collector) and start both services. For example:

   ```bash
   export OTEL_EXPORTER_OTLP_ENDPOINT="https://otel.example.com:4318"
   export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer <token>"
   ```

2. Issue a request to the AI Gateway that triggers a backend call while forcing a known correlation identifier:

   ```bash
   curl -X POST \
     -H "Content-Type: application/json" \
     -H "X-Correlation-ID: demo-correlation" \
     -d '{"procedure_id": "demo", "step_key": "intro"}' \
     http://localhost:8100/tools/get_required_slots
   ```

3. Inspect your log sink (or stdout when no collector is configured). You should see two JSON entries sharing `"correlation_id": "demo-correlation"`: one emitted by the AI Gateway for the incoming request and another from the backend for the delegated request. The shared identifier confirms end-to-end propagation and allows dashboards to pivot across services.

4. Repeat with additional endpoints to trace complex flows. Any log processors (e.g. Loki, Grafana, Elastic) can parse the JSON payloads directly.
