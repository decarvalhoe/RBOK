# Backend Logging and Observability

The FastAPI backend exposes structured, correlation-aware logs to aid debugging and tracing. Logging is configured in `app/main.py` via Python's standard `logging` module with the following characteristics:

- **Format** – Logs follow the pattern `timestamp level logger [correlation_id=<value>] message` so downstream processors can parse the correlation ID.
- **Correlation IDs** – `CorrelationIdMiddleware` reads the optional `X-Correlation-ID` header, falling back to a generated UUID. The ID is stored in a context variable, injected into each log record, and returned on the response headers (`X-Correlation-ID`).
- **Request timing** – The middleware measures request latency and emits a `Request completed` log with the method, path, duration (milliseconds), and status code. The latency is also surfaced in the `X-Process-Time-ms` response header when a response is generated.
- **Error reporting** – Application-specific `DomainError` subclasses are translated into HTTP responses with meaningful status codes while logging warning-level entries that include the failing path and error detail. Unhandled exceptions are logged at the error level with full stack traces.

## Local usage

No additional setup is required to capture the structured logs locally—running the FastAPI application (for example via `uvicorn app.main:app --reload`) prints the enriched log records to standard output. Downstream log shippers can be configured to parse the correlation-id field for distributed tracing.
