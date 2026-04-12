# RB-001: Getting Started

**Task:** TASK-044
**Last updated:** 2026-04-12

---

## Prerequisites

Ensure the following are installed before proceeding:

| Tool            | Minimum Version |
|-----------------|-----------------|
| Python          | 3.11+           |
| Docker          | 24+             |
| Docker Compose  | 2.20+           |
| Git             | 2.40+           |

## Clone the Repo

```bash
git clone git@github.com:<org>/export-labeling-automation.git
cd export-labeling-automation
```

## Environment Setup

Copy the example env file and fill in any required values:

```bash
cp .env.example .env
```

Review `.env` and set database credentials, API keys, and MinIO secrets as needed.

## Install Dependencies

```bash
make install
```

This creates a virtual environment and installs all Python dependencies from `requirements.txt` (and dev extras).

## Start Infrastructure

Bring up the backing services with Docker Compose:

```bash
docker compose up -d
```

This starts:

| Service    | Port(s)       | Purpose                        |
|------------|---------------|--------------------------------|
| Postgres 16| 5432          | Primary database               |
| Redis 7    | 6379          | Caching and task queues        |
| MinIO      | 9000 / 9001   | S3-compatible object storage   |
| Temporal   | 7233 / 8088   | Workflow orchestration         |

Verify all containers are healthy:

```bash
docker compose ps
```

## Run the Dev Server

```bash
make dev
```

The API will be available at `http://localhost:8000`. Interactive docs are served at `/api/v1/docs`.

## Run Tests

```bash
make test
```

## Run Linting

```bash
make lint
```

---

## Code Structure Overview

All application code lives under the `labelforge/` directory:

```
labelforge/
  api/v1/        # FastAPI route modules (versioned API)
  agents/        # Autonomous labeling agents
  compliance/    # Regulatory rule engines and validation
  contracts/     # Pydantic schemas / data contracts
  core/          # App config, settings, shared utilities
  db/            # SQLAlchemy models, migrations, session management
  services/      # Business logic layer (called by routes / agents)
  workflows/     # Temporal workflow definitions
  workers/       # Temporal worker entry points and activity implementations
```

---

## Adding a New API Route

1. Create a new file in `labelforge/api/v1/` (e.g., `shipments.py`).
2. Define a FastAPI `APIRouter`:
   ```python
   from fastapi import APIRouter

   router = APIRouter(prefix="/shipments", tags=["shipments"])

   @router.get("/")
   async def list_shipments():
       return []
   ```
3. Register the router in `labelforge/api/v1/__init__.py` (or wherever routers are aggregated):
   ```python
   from labelforge.api.v1.shipments import router as shipments_router
   app.include_router(shipments_router)
   ```
4. Add request/response schemas in `labelforge/contracts/`.
5. Add business logic in `labelforge/services/`.
6. Write tests and run `make test`.

## Adding a New Agent

1. Create a new module in `labelforge/agents/` (e.g., `hazmat_agent.py`).
2. Implement the agent class, inheriting from the base agent if one exists:
   ```python
   class HazmatAgent:
       async def run(self, context):
           # agent logic here
           ...
   ```
3. If the agent needs to be orchestrated, create a corresponding Temporal workflow in `labelforge/workflows/` and register activities in `labelforge/workers/`.
4. Wire the agent into the relevant service layer in `labelforge/services/`.
5. Add tests and run `make test`.

## Debugging Tips

- **FastAPI interactive docs** -- browse to `http://localhost:8000/api/v1/docs` to explore and test endpoints directly.
- **Temporal UI** -- open `http://localhost:8088` to inspect running workflows, view event histories, and retry failed activities.
- **MinIO console** -- open `http://localhost:9001` to browse uploaded label files and manage buckets.
- Use `docker compose logs -f <service>` to tail logs for any backing service.
- Set `LOG_LEVEL=DEBUG` in `.env` for verbose application logging.

---

## Cross-References

- [Architecture Decision Records](../adr/) -- design rationale and key decisions
- [API Reference](../api/) -- detailed endpoint documentation
- [Compliance Rules](../compliance/) -- regulatory rule definitions
- [Deployment Guide](../deployment/) -- production deployment procedures
