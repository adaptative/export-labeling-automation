# RB-004: Cost Breaker Response

**Task:** TASK-046
**Last updated:** 2026-04-17

---

The cost breaker is a four-tier guard that halts LLM spend when usage
crosses per-tenant caps. A breaker event raises
`labelforge_cost_breaker_breached_total` and routes a PagerDuty page
via `ops/alertmanager.yml`.

## Breaker tiers

| Tier            | Default cap       | Scope                                        |
|-----------------|-------------------|----------------------------------------------|
| Monthly budget  | $1 000 / tenant   | Cumulative LLM + HiTL cost this month        |
| Daily burn      | $75  / tenant     | Rolling 24 h window                          |
| Per-agent cap   | $25  / agent      | Rolling 1 h window per agent                 |
| HiTL routing    | $5   / tenant     | Rolling 24 h for human-escalated items       |

Operators can override caps at `/admin/cost` — backed by
`PUT /api/v1/budgets/tenant/{id}/caps`.

## When a breaker trips

1. **Confirm the breach is genuine.** Inspect the cost dashboard
   (`/cost`): is the trend consistent with recent traffic?
2. **Identify the blast radius.** Which tenant(s) and which agent(s)?

   ```bash
   curl -fsS "${BASE}/api/v1/cost/overview" \
     -H "Authorization: Bearer ${OPS_TOKEN}" | jq
   ```

3. **Pause agent execution** if the breach is driven by a regression.
   Draining Temporal activity is preferable to a hard kill:

   ```bash
   kubectl -n labelforge exec deploy/temporal-worker -- \
     labelforge workflows pause --tenant tnt-offending-001
   ```

4. **Raise the cap** (if the breach reflects legitimate growth). Prefer
   a time-limited bump rather than a permanent raise:

   ```bash
   curl -fsS -X PUT "${BASE}/api/v1/budgets/tenant/tnt-offending-001/caps" \
     -H "Authorization: Bearer ${ADMIN_TOKEN}" \
     -d '{"monthly": 1500, "daily": 100, "valid_until": "2026-04-25T00:00:00Z"}'
   ```

5. **Or quarantine a runaway agent**:

   ```bash
   curl -fsS -X POST "${BASE}/api/v1/agents/intake-classifier/disable" \
     -H "Authorization: Bearer ${ADMIN_TOKEN}"
   ```

## Post-incident

* Capture the breaker event in `/audit` for compliance.
* Note the root cause (prompt regression, traffic spike, bad rule) in
  the post-mortem template at `docs/postmortems/TEMPLATE.md`.
* If spend is recurring, re-tune the caps via the admin UI rather than
  relying on ad-hoc overrides.

## Troubleshooting

| Symptom                                    | Action                                           |
|--------------------------------------------|--------------------------------------------------|
| Breaker fires but cost dashboard is low    | Redis `cost:*` keys drifted — reconcile via CLI  |
| Breach every night at 00:00 UTC            | Matview refresh window — adjust to 01:00 UTC     |
| PagerDuty ack loop                         | Confirm `routing_key` is current; re-issue token |
| Breakers never fire                        | Prometheus scrape broken — see [rb-007](./rb-007-monitoring-setup.md) |
