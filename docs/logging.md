# Backend Logging and Observability

The FastAPI backend exposes structured, correlation-aware logs to aid debugging and tracing. Logging is configured in `app/main.py` via Python's standard `logging` module with the following characteristics:

- **Format** – Logs follow the pattern `timestamp level logger [correlation_id=<value>] message` so downstream processors can parse the correlation ID.
- **Correlation IDs** – `CorrelationIdMiddleware` reads the optional `X-Correlation-ID` header, falling back to a generated UUID. The ID is stored in a context variable, injected into each log record, and returned on the response headers (`X-Correlation-ID`).
- **Request timing** – The middleware measures request latency and emits a `Request completed` log with the method, path, duration (milliseconds), and status code. The latency is also surfaced in the `X-Process-Time-ms` response header when a response is generated.
- **Error reporting** – Application-specific `DomainError` subclasses are translated into HTTP responses with meaningful status codes while logging warning-level entries that include the failing path and error detail. Unhandled exceptions are logged at the error level with full stack traces.

## Local usage

No additional setup is required to capture the structured logs locally—running the FastAPI application (for example via `uvicorn app.main:app --reload`) prints the enriched log records to standard output. Downstream log shippers can be configured to parse the correlation-id field for distributed tracing.

## Distributed tracing

Both the procedural backend (`rbok-backend`) and the AI gateway (`rbok-ai-gateway`) now initialise an OpenTelemetry tracer provider on startup. Incoming FastAPI requests are wrapped in spans, correlation IDs are attached as span attributes, and outbound dependencies (SQLAlchemy sessions, Redis connections, OpenAI API calls, and HTTP calls to the backend) are wrapped in child spans that record latency and status.

Traces are exported over OTLP/HTTP. By default the services target `http://otel-collector:4318`, but you can override the destination and headers via the standard environment variables:

- `OTEL_EXPORTER_OTLP_ENDPOINT` – base URL of the collector (for local stacks this is typically `http://localhost:4318`).
- `OTEL_EXPORTER_OTLP_HEADERS` – optional comma-separated list of `key=value` pairs for authentication.

The platform's shared observability stack exposes a Jaeger UI from the central collector. Once the collector is reachable, open `http://otel-collector:16686` (replace `otel-collector` with the actual host name when running remotely) and search for the `service.name` of interest (`rbok-backend` or `rbok-ai-gateway`) to inspect distributed traces end-to-end. The propagated `X-Correlation-ID` header allows correlating traces and logs across service boundaries.
