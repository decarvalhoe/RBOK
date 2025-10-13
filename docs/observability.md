# Observability and Telemetry Operations

This document explains how the RBOK observability stack is composed, how to deploy and configure it, and how to operate the dashboards and alerting that keep the platform healthy. The stack is designed around OpenTelemetry (OTel) for signal collection and Grafana for visualization, with alerting routed through Grafana Alerting / Alertmanager integrations.

## Stack Overview

| Layer | Component | Purpose |
| --- | --- | --- |
| Instrumentation | OpenTelemetry SDKs in each service | Emit traces, metrics, and logs via OTLP/HTTP. |
| Signal routing | OpenTelemetry Collector (gateway mode) | Centralize OTLP ingestion, transform/export to Prometheus, Loki, and Tempo. |
| Metrics storage | Prometheus (via OTel Collector export) | Retain time-series metrics for dashboards and alerts. |
| Logs storage | Loki | Store structured application and infrastructure logs. |
| Traces storage | Tempo | Persist distributed traces emitted by services. |
| Visualization | Grafana | Unified dashboards for metrics/logs/traces; alert rule authoring. |
| Alerting | Grafana Alerting (Alertmanager-compatible) | Evaluate rules and notify on-call channels. |

### Network layout

All workloads send OTLP traffic to the collector endpoint `http://otel-collector:4318`. The collector forwards:

- Metrics → Prometheus remote-write endpoint (`http://prometheus:9090/api/v1/write`).
- Logs → Loki push API (`http://loki:3100/loki/api/v1/push`).
- Traces → Tempo distributor (`http://tempo:3200`).

The Grafana server connects to Prometheus/Loki/Tempo via internal service discovery (`http://prometheus:9090`, `http://loki:3100`, `http://tempo:3100`).

## Deployment and Configuration

### 1. Prepare environment variables

Create an `.env.observability` file to make endpoints reusable across services:

```bash
cat > .env.observability <<'ENV'
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_EXPORTER_OTLP_HEADERS=""
PROMETHEUS_RETENTION=15d
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=change-me
GRAFANA_PROVISIONING_PATH=/etc/grafana/provisioning
GRAFANA_ALERT_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ
ENV
```

Load the file before launching services:

```bash
set -a
source .env.observability
set +a
```

### 2. Deploy the observability foundation

Create `observability/docker-compose.observability.yml` with the following content:

```yaml
services:
  otel-collector:
    image: otel/opentelemetry-collector:0.91.0
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./observability/otel-collector-config.yaml:/etc/otel-collector-config.yaml:ro
    ports:
      - "4317:4317"
      - "4318:4318"

  prometheus:
    image: prom/prometheus:v2.51.0
    volumes:
      - ./observability/prometheus.yaml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.retention.time=${PROMETHEUS_RETENTION}"
    ports:
      - "9090:9090"

  loki:
    image: grafana/loki:2.9.5
    command: ["-config.file=/etc/loki/local-config.yaml"]
    volumes:
      - ./observability/loki-config.yaml:/etc/loki/local-config.yaml:ro
      - loki-data:/loki
    ports:
      - "3100:3100"

  tempo:
    image: grafana/tempo:2.3.1
    command: ["-config.file=/etc/tempo/tempo.yaml"]
    volumes:
      - ./observability/tempo.yaml:/etc/tempo/tempo.yaml:ro
      - tempo-data:/var/tempo
    ports:
      - "3200:3200"

  grafana:
    image: grafana/grafana:10.4.3
    environment:
      - GF_SECURITY_ADMIN_USER=${GRAFANA_ADMIN_USER}
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
    volumes:
      - ./observability/grafana/provisioning:${GRAFANA_PROVISIONING_PATH}
      - grafana-data:/var/lib/grafana
    ports:
      - "3001:3000"

volumes:
  prometheus-data:
  loki-data:
  tempo-data:
  grafana-data:
```

Launch the stack:

```bash
docker compose -f observability/docker-compose.observability.yml up -d
```

> **Tip:** Keep the observability compose file separate from the core application compose files so you can restart telemetry components without impacting production traffic.

### 3. Configure the OpenTelemetry Collector

Save `observability/otel-collector-config.yaml` with a gateway pipeline that receives all three signals:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
      http:

exporters:
  prometheusremotewrite:
    endpoint: http://prometheus:9090/api/v1/write
  loki:
    endpoint: http://loki:3100/loki/api/v1/push
    labels:
      job: rbok
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true

processors:
  batch:
    send_batch_size: 8192
    timeout: 5s
  memory_limiter:
    limit_mib: 512
    spike_limit_mib: 128
    check_interval: 5s
  resource:
    attributes:
      - key: deployment.environment
        value: ${ENVIRONMENT}
        action: upsert

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [prometheusremotewrite]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [loki]
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/tempo]
```

Make sure every RBOK service exports OTLP data to `http://otel-collector:4318` by setting the following environment variables (already supported by OpenTelemetry SDK defaults):

```env
OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT}
OTEL_METRICS_EXPORTER=otlp
OTEL_TRACES_EXPORTER=otlp
OTEL_LOGS_EXPORTER=otlp
OTEL_RESOURCE_ATTRIBUTES=service.name=<service>,deployment.environment=${ENVIRONMENT}
```

### 4. Grafana provisioning

Provision data sources and dashboards so Grafana starts configured automatically.

```
observability/grafana/provisioning/
├── dashboards/
│   ├── backend-api.json
│   ├── ai-gateway.json
│   ├── webapp-ux.json
│   ├── platform-overview.json
├── datasources/
│   └── datasources.yaml
└── alerting/
    └── policies.yaml
```

- **Data sources** – `datasources.yaml` should register Prometheus, Loki, and Tempo endpoints.
- **Dashboards** – export Grafana dashboards as JSON and place them under `dashboards/`. Grafana auto-imports them on startup.
- **Alert policies** – define the default contact points and routing, including escalation chains and maintenance silences.

Example `datasources.yaml` snippet:

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
  - name: Tempo
    type: tempo
    access: proxy
    url: http://tempo:3100
```

### 5. Alert channel configuration

Create `observability/grafana/provisioning/alerting/contact-points.yaml` with the desired notification targets:

```yaml
apiVersion: 1
contactPoints:
  - orgId: 1
    name: slack-oncall
    receivers:
      - uid: slack
        type: slack
        settings:
          url: ${GRAFANA_ALERT_WEBHOOK}
  - orgId: 1
    name: email-sre
    receivers:
      - uid: email
        type: email
        settings:
          addresses: sre@example.com
```

Reference the contact points from `policies.yaml` to control routing (for instance, send critical alerts to Slack with SMS fallback and warnings to email only).

## Grafana Dashboards

| Dashboard | Purpose | Key Panels |
| --- | --- | --- |
| **Platform Overview** | Executive summary of uptime and latency across all services. | Error rate (5xx), p95 latency, queue depth, uptime SLO gauges. |
| **Backend API Health** | Focused on FastAPI performance and background jobs. | Request rate, duration histograms, database query timings, Redis cache hit ratio. |
| **AI Gateway Operations** | Tracks inference requests and external provider behavior. | Token usage, upstream latency, throttling events, provider error breakdown. |
| **Webapp UX** | Front-end web vitals and client errors. | LCP/FID/CLS trends, GraphQL/REST failure rates, WebSocket message stats. |
| **Infrastructure** | Hosts, containers, collector pipeline metrics. | CPU/memory for nodes, collector queue length, Prometheus scrape success. |

Dashboards should use consistent template variables:

- `environment` – e.g., `prod`, `staging`.
- `service` – `backend`, `ai-gateway`, `webapp`.
- `namespace` – Kubernetes namespace or Compose project name.

Export dashboard JSONs into `observability/grafana/provisioning/dashboards` whenever modifications are made so the stack remains reproducible.

## Alert Rules

| Alert | Signal Source | Condition | Suggested Severity | Default Channel |
| --- | --- | --- | --- | --- |
| **BackendHighErrorRate** | Prometheus `http_server_requests_total` | `rate(5xx[5m]) > 0.02` | Critical | slack-oncall |
| **BackendLatencyP95** | Prometheus histogram | `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1.5` seconds | High | slack-oncall |
| **AIProviderFailures** | Prometheus counter from AI gateway | `increase(ai_gateway_provider_errors_total[10m]) > 10` | High | slack-oncall |
| **CollectorQueueBacklog** | Collector self-metrics | `otelcol_exporter_queue_size > 5000` for 10 minutes | High | email-sre |
| **GrafanaDatasourceDown** | Grafana synthetic check | Datasource health check failing for >5 minutes | Medium | email-sre |
| **WebappJSExceptions** | Loki log query | `sum(count_over_time({app="webapp", level="error"}[15m])) > 20` | Medium | slack-oncall |

### Authoring and version control

1. Define alert rules in Grafana (Alerting → Alert rules) using the data sources above.
2. Export rules as JSON via the Grafana API (`/api/ruler/grafana/api/v1/rules/{namespace}`) and save them under `observability/grafana/provisioning/alerting/rules/`.
3. Commit changes so alert logic is tracked alongside code.

### Maintenance windows

- Add maintenance windows through Grafana Alerting → Silences. Document recurring maintenance (patch Tuesdays) in the `policies.yaml` file so on-call engineers are not paged.

## Operational Playbooks

### 1. Backend high error rate

1. Confirm alert details and affected endpoints via the **Backend API Health** dashboard.
2. Inspect recent deploys (CI/CD, feature flags). Roll back if a new release correlates with the alert.
3. Check Loki logs filtered by `service=backend` and `level=error` to identify stack traces.
4. If database errors surface, verify PostgreSQL availability and connection limits. Consider scaling DB or clearing long-running queries.
5. If issue persists, escalate to backend lead within 15 minutes and capture remediation steps in the incident ticket.

### 2. Collector queue backlog

1. Review collector self-metrics panel to see which exporter is back-pressuring.
2. Inspect downstream services:
   - Prometheus: evaluate scrape duration and remote write success.
   - Loki: check ingestion rate and disk utilization.
   - Tempo: verify distributor status.
3. Increase collector CPU/memory or add additional replicas using the `otel-collector` service scaling settings.
4. If downstream unavailable, enable local file storage (add `filelog` exporter temporarily) to avoid data loss.

### 3. Webapp JavaScript exception surge

1. Open **Webapp UX** dashboard to confirm the spike and identify browsers/regions affected.
2. Drill into Loki logs with `app=webapp` to inspect stack traces. Cross-reference Sentry events for exact error messages.
3. Toggle feature flags or revert the latest frontend deployment if the regression is introduced recently.
4. Notify product support and publish a status page update if user impact is severe.

### 4. AI provider failures

1. Verify upstream provider status pages.
2. Check the **AI Gateway Operations** dashboard for rate-limiting and token usage spikes.
3. If the provider is degraded, switch to backup providers configured in the AI gateway or reduce traffic (e.g., disable optional AI features).
4. Communicate with stakeholders and update incident tickets hourly until resolved.

## Reproducing the Setup in New Environments

1. Provision the observability infrastructure using the compose file above (or translate into Kubernetes manifests/Helm charts for production).
2. Inject the `.env.observability` variables into the target environment.
3. Roll out RBOK services with OTEL exporters enabled. Validate connectivity with `otelcol` logs (`otelcol` in debug mode shows exported spans/metrics).
4. Import Grafana dashboards, data sources, and alert rules from version control. Grafana will apply provisioning files on startup.
5. Execute synthetic checks (e.g., `curl` health endpoints, emit test spans with `otel-cli`) to verify metrics, logs, and traces arrive and dashboards populate.
6. Trigger alert test notifications from Grafana (Alerting → Contact points → Test) to confirm on-call channels receive messages.

## Backup and Disaster Recovery

- Configure persistent volumes for Prometheus, Loki, Tempo, and Grafana (as shown in the compose file) to survive restarts.
- Schedule snapshots of `prometheus-data`, `loki-data`, and `tempo-data` volumes to object storage.
- Export Grafana dashboards and alert rules into git on every change to maintain an auditable history.
- Document recovery steps: redeploy the compose file, restore volumes from snapshots, and restart services.

## Security Considerations

- Restrict Grafana admin credentials and configure SSO (e.g., Keycloak) for operator access.
- Enable HTTPS termination (reverse proxy or Grafana config) for external access.
- Use network policies or Docker networks to ensure only trusted services can reach the collector endpoint.
- Scrub sensitive fields in logs using collector processors (e.g., `attributes` processor) before exporting to Loki.

## Further Reading

- [OpenTelemetry Collector documentation](https://opentelemetry.io/docs/collector/)
- [Grafana provisioning reference](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [Grafana Alerting and Contact points](https://grafana.com/docs/grafana/latest/alerting/)

Keep this document updated whenever dashboards, alerts, or runbooks evolve so the next operator can reproduce and operate the observability stack with confidence.
