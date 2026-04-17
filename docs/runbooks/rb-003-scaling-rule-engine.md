# RB-003: Scaling the Rule Engine

**Task:** TASK-046
**Last updated:** 2026-04-17

---

The compliance rule engine (see `labelforge/services/rules/`) evaluates a
per-tenant rule set for every order item. Throughput is limited by two
resources: CPU (DSL parsing / matcher caches) and Postgres round-trips
(materialised view refresh + write-back). This runbook covers how to
detect saturation and the knobs to turn.

## Detecting saturation

Prometheus queries:

```promql
# p95 rule-eval latency over 5 minutes, per tenant
histogram_quantile(0.95, sum by (tenant_id, le)(rate(labelforge_rule_eval_duration_seconds_bucket[5m])))

# Queued evaluations
max_over_time(labelforge_rule_eval_queue_depth[5m])

# CPU saturation on the rule-worker pool
rate(container_cpu_usage_seconds_total{pod=~"worker-.*"}[5m])
```

Trigger thresholds (see `ops/prometheus/alerts.yml`):

| Alert                    | Condition                  | Severity |
|--------------------------|----------------------------|----------|
| `RuleEvalLatencyHigh`    | p95 > 100 ms for 5 min     | warning  |
| `RuleEvalQueueSpike`     | depth > 100 for 2 min      | critical |
| `RuleMatcherCacheThrash` | hit-rate < 50 % for 10 min | warning  |

## Scaling knobs

1. **Rule-worker replicas** — HPA targets 60 % CPU. To add headroom:

   ```bash
   kubectl -n labelforge scale deploy/worker --replicas=6
   ```

2. **Matcher cache size** — the in-process matcher cache is bounded by
   `LABELFORGE_MATCHER_CACHE_MAX` (default **10**). Increase when the
   rule catalogue grows past a handful, but budget ~2 MB per entry:

   ```bash
   kubectl -n labelforge set env deploy/worker LABELFORGE_MATCHER_CACHE_MAX=64
   ```

3. **Matview refresh cadence** — `automation_daily_mv` refreshes every 5
   min by default. Push to 10 min when intake volume is low, or enable
   concurrent refresh (Postgres 16):

   ```sql
   REFRESH MATERIALIZED VIEW CONCURRENTLY automation_daily_mv;
   ```

4. **Read-replica read-through** — the `LABELFORGE_READ_REPLICA_URL` env
   var, when set, routes rule-list and snapshot reads to a hot standby.
   Latency-critical writes continue to use the primary.

## Hot-path optimisations

* Pre-warm the matcher cache at worker boot by fetching the active rule
  set on startup (`rules_service.prewarm_cache()`). This is on by default
  — turn off with `LABELFORGE_RULES_PREWARM=0` only for debugging.
* Disable DSL validation in hot-path eval when the ruleset passed through
  the `/rules/*/dry-run` admin flow: `rule.dsl_validated = True` short-
  circuits the parser.
* Consider promoting rules to the `testing` state **before** flipping to
  `active` — the state machine transitions are non-blocking so that a
  bad rule can be shadowed until its behaviour is confirmed safe.

## Rolling back a bad rule

```bash
# Demote all rules promoted in the last hour to draft.
curl -fsS -X POST "${BASE}/api/v1/rules/rollback" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -d '{"since_minutes": 60}'
```

Or, via SQL if the API is unavailable:

```sql
UPDATE rules
   SET status = 'draft'
 WHERE promoted_at > NOW() - INTERVAL '60 minutes';
```

## Troubleshooting

| Symptom                                         | Action                                               |
|-------------------------------------------------|------------------------------------------------------|
| Eval queue growing unboundedly                  | Scale worker replicas; check matview refresh lock    |
| p95 latency spike, cache hit-rate normal        | Likely slow Postgres — inspect `pg_stat_activity`    |
| All evals fail for a tenant                     | Bad rule promoted — query `rules` for latest promote |
| `MatcherCompileError` in logs                   | DSL regression — roll back the offending commit      |
