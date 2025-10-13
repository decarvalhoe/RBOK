# Metrics and Observability

Both the backend API and the AI Gateway expose Prometheus-compatible metrics so that infrastructure operators can monitor latency and dependency health.

## Endpoints

| Service       | Endpoint            | Description |
| ------------- | ------------------- | ----------- |
| Backend API   | `http://<host>:8000/metrics`    | Prometheus exposition format with request counters, latency histograms, and database/cache health. |
| AI Gateway    | `http://<host>:8010/metrics`    | Prometheus exposition format with gateway request telemetry and backend dependency health mirrored from the backend service. |

You can inspect the raw metrics locally with curl:

```bash
curl http://localhost:8000/metrics
curl http://localhost:8010/metrics
```

## Key metrics

Backend specific metrics:

- `backend_request_total{method, path, status_code}` – counter of handled requests.
- `backend_request_duration_seconds{method, path, status_code}` – histogram of request processing time in seconds.
- `backend_database_up` – gauge set to `1` when the SQL database answers a `SELECT 1` probe.
- `backend_cache_up` – gauge set to `1` when the Redis cache responds to a `PING`.

AI Gateway metrics:

- `ai_gateway_request_total{method, path, status_code}` – counter of handled gateway requests.
- `ai_gateway_request_duration_seconds{method, path, status_code}` – histogram of request latency in seconds.
- `ai_gateway_backend_database_up` – gauge derived from the backend's `backend_database_up` metric.
- `ai_gateway_backend_cache_up` – gauge derived from the backend's `backend_cache_up` metric.

## Prometheus configuration

Add scrape jobs for each service in your Prometheus configuration. The example below works for Docker Compose deployments:

```yaml
scrape_configs:
  - job_name: "rbok-backend"
    static_configs:
      - targets: ["backend:8000"]
  - job_name: "rbok-ai-gateway"
    static_configs:
      - targets: ["ai_gateway:8010"]
```

Both `docker-compose.yml` and `docker-compose.prod.yml` include `prometheus.io/*` labels for the backend and AI Gateway containers. When running in environments that honour these labels (for example, cAdvisor + Prometheus label discovery), no additional configuration is necessary beyond enabling label-based discovery.

For Kubernetes or other orchestrators, configure the associated ServiceMonitor/PodMonitor to scrape `/metrics` on the exposed service port.
