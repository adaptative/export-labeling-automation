# RB-002: Deploying Labelforge

**Task:** TASK-046
**Last updated:** 2026-04-17

---

This runbook covers deploying the API + worker + frontend to a production
environment. The canonical target is a Kubernetes cluster in front of a
managed Postgres; the same steps apply to ECS or a single-host Docker
Compose with minor substitutions.

## Pre-flight

Before tagging a release:

| Check                                             | Command / where                              |
|---------------------------------------------------|----------------------------------------------|
| CI green on `main` (unit + E2E)                   | GitHub Actions ✔️                            |
| `main` fast-forwards cleanly                      | `git log origin/main..HEAD --oneline`        |
| Alembic revisions applied locally                 | `alembic upgrade head`                       |
| `ops/prometheus/alerts.yml` parses                | `promtool check rules ops/prometheus/*.yml`  |
| No pending secrets rotation                       | `doc:/docs/security/secrets-rotation.md`     |

## Image build

```bash
# API + worker share one image. Tag with the commit SHA.
SHA=$(git rev-parse --short HEAD)
docker build -t ghcr.io/<org>/labelforge-api:${SHA} .
docker build -t ghcr.io/<org>/labelforge-frontend:${SHA} ./frontend
docker push ghcr.io/<org>/labelforge-api:${SHA}
docker push ghcr.io/<org>/labelforge-frontend:${SHA}
```

## Database migration

Always run migrations **before** rotating pods. Migrations are additive
and backward-compatible by convention (see `docs/alembic-conventions.md`).

```bash
kubectl -n labelforge run alembic-${SHA} \
  --rm -it --restart=Never \
  --image=ghcr.io/<org>/labelforge-api:${SHA} \
  -- alembic upgrade head
```

If a migration fails midway, the `alembic_version` row is **not** advanced
— rerun safely after fixing the issue.

## Rolling deploy

```bash
kubectl -n labelforge set image deploy/api api=ghcr.io/<org>/labelforge-api:${SHA}
kubectl -n labelforge set image deploy/worker worker=ghcr.io/<org>/labelforge-api:${SHA}
kubectl -n labelforge set image deploy/frontend frontend=ghcr.io/<org>/labelforge-frontend:${SHA}
kubectl -n labelforge rollout status deploy/api --timeout=5m
kubectl -n labelforge rollout status deploy/worker --timeout=5m
kubectl -n labelforge rollout status deploy/frontend --timeout=5m
```

Readiness is driven by `GET /health` (API) and by the Nginx `/` response
(frontend). `maxUnavailable` is kept at **0** for the API and **25 %** for
the worker deployment.

## Smoke tests

Once the rollout completes, exercise the critical path:

```bash
BASE=https://api.labelforge.example
curl -fsS ${BASE}/health | jq
curl -fsS ${BASE}/api/v1/agents | jq '.total'
curl -fsS ${BASE}/metrics | head -20
```

Then run the E2E smoke target from a local checkout:

```bash
PLAYWRIGHT_TEST_URL=https://app.labelforge.example \
PLAYWRIGHT_LIVE_BACKEND=1 \
  npm --prefix frontend run test:e2e -- --grep "login → create order"
```

## Rollback

Same mechanism, previous SHA:

```bash
PREV=$(kubectl -n labelforge rollout history deploy/api | awk 'END{print $1}')
kubectl -n labelforge rollout undo deploy/api --to-revision=${PREV}
kubectl -n labelforge rollout undo deploy/worker --to-revision=${PREV}
kubectl -n labelforge rollout undo deploy/frontend --to-revision=${PREV}
```

Schema rollbacks are handled via `alembic downgrade -1` — **only** for
migrations flagged `reversible=True`. Always confirm in staging first.

## Troubleshooting

| Symptom                                   | Likely cause                                   | Action                                     |
|-------------------------------------------|------------------------------------------------|--------------------------------------------|
| Pods stuck `CrashLoopBackOff`             | Bad env var / missing secret                   | `kubectl logs -p` + check `external-secrets` |
| `/health` returns 503                     | DB not reachable or Temporal down              | See [rb-006](./rb-006-db-backup-restore.md) |
| Frontend shows 503 after deploy           | Nginx container missed `COPY --from=build`     | Rebuild image, re-push                     |
| Alembic says "Can't locate revision"      | Two branches produced conflicting heads        | `alembic merge heads` then redeploy        |
| Metrics scrape empty                      | Service selector changed                       | `kubectl describe svc api` + Prometheus UI |
