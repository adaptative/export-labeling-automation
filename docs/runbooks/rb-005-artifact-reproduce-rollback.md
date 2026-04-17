# RB-005: Artifact Reproduce & Rollback

**Task:** TASK-046
**Last updated:** 2026-04-17

---

Every printable artifact (labels, protocols, bundles) is content-addressed
and stored in BlobStore. A regression in a classifier prompt, a ruleset,
or a composer template can all produce incorrect artifacts. This runbook
covers how to reproduce a specific artifact deterministically and how to
roll back to a known-good version.

## Reproduce an artifact

1. **Find the artifact + its rules snapshot**:

   ```bash
   curl -fsS "${BASE}/api/v1/artifacts/art-12345" \
     -H "Authorization: Bearer ${OPS_TOKEN}" | jq
   # → { "rules_snapshot_id": "rs-2026-04-15-01", ... }
   ```

2. **Pin the inputs** into a reproduce bundle:

   ```bash
   labelforge artifacts reproduce art-12345 --out /tmp/art-12345.bundle
   ```

   This writes the original item payload, the rules snapshot, the agent
   prompt versions, and the BlobStore SHAs into a single tarball.

3. **Replay locally** against the pinned versions:

   ```bash
   labelforge artifacts replay /tmp/art-12345.bundle --workdir ./replay-art-12345
   diff ./replay-art-12345/output.pdf ./original.pdf
   ```

4. If the replay differs, the underlying inputs have drifted — investigate
   which agent / rule changed.

## Roll back an artifact

Artifacts are **immutable**; "rollback" means regenerating against an
earlier snapshot and promoting that as the canonical version.

```bash
# Regenerate item ``itm-999`` against rules snapshot rs-2026-04-10-03
curl -fsS -X POST "${BASE}/api/v1/items/itm-999/regenerate" \
  -H "Authorization: Bearer ${OPS_TOKEN}" \
  -d '{"rules_snapshot_id": "rs-2026-04-10-03"}'
```

The new artifact is written with a fresh SHA; audit-log entries
(`artifact.regenerate`) record the operator and reason. Downstream
printer portals are re-notified automatically.

## Bulk rollback — last 24 h

```bash
labelforge artifacts bulk-regenerate \
  --tenant tnt-nakoda-001 \
  --since 24h \
  --rules-snapshot rs-2026-04-10-03 \
  --confirm
```

This streams through `/items?updated_since=...` and issues one
`POST /items/{id}/regenerate` per hit. It is rate-limited to 10 req/s
and resumable — safe to interrupt.

## Versioning

| Entity         | Identifier                      | Source                |
|----------------|---------------------------------|-----------------------|
| Rules snapshot | `rs-YYYY-MM-DD-NN`              | `rules_snapshots`     |
| Prompt version | `intake-classifier@v3.2.0`      | `agent_prompts.yaml`  |
| Template       | `label-US-warning@v7`           | `templates/` in repo  |
| Ruleset promote| `rule_promotion_events.id`      | audit trail           |

Every artifact row stores a pointer to each, so reproducibility is
deterministic.

## Troubleshooting

| Symptom                                       | Action                                                |
|-----------------------------------------------|-------------------------------------------------------|
| Replay PDF differs but inputs match           | Compare prompt versions — may be transitively bumped  |
| `BlobStore.get()` returns 404                 | Object lifecycle policy deleted it — raise retention  |
| Regenerate returns 409 "snapshot in use"      | Another regen is running; `kubectl logs worker` for ETA |
| Printer portal not notified after rollback    | WebSocket stale — restart portal service              |
