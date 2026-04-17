# RB-007: Monitoring Setup

**Task:** TASK-046
**Last updated:** 2026-04-17

---

Labelforge exports Prometheus metrics from the API, distributed traces
via OTLP-HTTP, and structured JSON logs from every service. This runbook
walks through bringing up the full observability stack and validating
that each signal reaches its destination.

## Components

| Signal  | Source                       | Exporter / endpoint                     | Store              |
|---------|------------------------------|-----------------------------------------|--------------------|
| Metrics | FastAPI + worker + frontend  | `GET /metrics`                          | Prometheus         |
| Traces  | OpenTelemetry SDK            | `OTEL_EXPORTER_OTLP_ENDPOINT`           | Tempo / Jaeger     |
| Logs    | structlog JSON → stdout      | fluent-bit sidecar                      | Loki               |
| Events  | Alertmanager → PagerDuty     | `ops/alertmanager.yml`                  | PagerDuty          |

## Bring-up order

1. **Prometheus** — point at the in-repo config:

   ```bash
   kubectl -n monitoring create configmap prometheus-config \
     --from-file=prometheus.yml=ops/prometheus/prometheus.yml \
     --from-file=alerts.yml=ops/prometheus/alerts.yml
   kubectl -n monitoring rollout restart deploy/prometheus
   ```

   Scrape targets are labelled `service=labelforge-api`, `role=worker`,
   `role=frontend-nginx`.

2. **Grafana** — import `ops/grafana/dashboards/labelforge-overview.json`
   via the Grafana API:

   ```bash
   curl -fsS -X POST "${GRAFANA}/api/dashboards/import" \
     -H "Authorization: Bearer ${GF_TOKEN}" \
     -H "Content-Type: application/json" \
     -d @ops/grafana/dashboards/labelforge-overview.json
   ```

3. **Alertmanager** — wire PagerDuty routing:

   ```bash
   kubectl -n monitoring create secret generic pagerduty-key \
     --from-literal=routing_key=<prod-key>
   kubectl -n monitoring apply -f ops/alertmanager.yml
   ```

4. **OpenTelemetry Collector** — the API ships spans only when
   `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Point it at the collector:

   ```bash
   kubectl -n labelforge set env deploy/api deploy/worker \
     OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.monitoring:4318
   ```

5. **Fluent-bit** — the sidecar tails stdout and forwards to Loki.
   No config change is needed; the image reads `fluent-bit.conf` from
   ConfigMap `labelforge-logging`.

## Validating end-to-end

```bash
# 1. Generate a traced request.
curl -fsS ${BASE}/api/v1/agents -o /dev/null

# 2. Confirm Prometheus scraped it.
curl -fsS ${PROM}/api/v1/query?query=labelforge_http_requests_total \
  | jq '.data.result | length'

# 3. Confirm the trace landed in Jaeger / Tempo.
curl -fsS "${JAEGER}/api/traces?service=labelforge-api&limit=1" \
  | jq '.data[0].spans | length'

# 4. Confirm the log line made it to Loki.
logcli query '{service="labelforge-api"}' --limit 5
```

## Required alert rules

The alert pack in `ops/prometheus/alerts.yml` has eight rules that must
stay green:

| Alert                         | Trigger                             |
|-------------------------------|-------------------------------------|
| `APIErrorRateHigh`            | 5xx rate > 5 % for 5 min            |
| `APILatencyP95High`           | p95 > 1 s for 10 min                |
| `WorkerQueueDepthHigh`        | queue > 100 for 2 min               |
| `CostBreakerBreached`         | any tier breached                   |
| `SLABreach`                   | order older than SLA and open       |
| `RuleEvalLatencyHigh`         | rule p95 > 100 ms                   |
| `PostgresReplicationLag`      | lag > 30 s                          |
| `TraceExporterDropping`       | `otelcol_exporter_send_failed_spans_total` > 0 |

## Runbook links

Each alert in `alerts.yml` includes `annotations.runbook_url` pointing to
the relevant `rb-*` doc in this folder. Keep them in sync when renaming.

## Troubleshooting

| Symptom                                       | Action                                                  |
|-----------------------------------------------|---------------------------------------------------------|
| `/metrics` returns 404                        | `enable_prometheus_endpoint=True` missing from env      |
| Grafana dashboard all-empty                   | Scrape target has wrong label — check Prometheus UI     |
| Traces in Jaeger missing `trace_id` in logs   | `LoggingInstrumentor` not installed — redeploy with fix |
| PagerDuty not paging                          | Routing key wrong / severity not mapped to service      |
| Loki "too many lines" rejections              | Bump `max_line_size` in Loki config                     |
