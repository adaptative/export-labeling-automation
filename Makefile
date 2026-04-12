.PHONY: install test lint format typecheck dev docker-up docker-down clean

# ── Install ──────────────────────────────────────────────────────────────────

install:
	python -m pip install --upgrade pip
	pip install -e ".[dev]"

# ── Quality ──────────────────────────────────────────────────────────────────

test:
	python -m pytest tests/ -v --tb=short

test-cov:
	python -m pytest tests/ -v --tb=short --cov=labelforge --cov-report=term-missing

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy labelforge/

# ── Run ──────────────────────────────────────────────────────────────────────

dev:
	uvicorn labelforge.app:app --reload --host 0.0.0.0 --port 8000

# ── Docker ───────────────────────────────────────────────────────────────────

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-build:
	docker compose build

# ── Cleanup ──────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	rm -rf dist/ build/ *.egg-info
