"""Tests for the FastAPI application scaffolding — TASK-001."""
from __future__ import annotations

from fastapi.testclient import TestClient

from labelforge.app import app

client = TestClient(app)


class TestHealthCheck:
    def test_health_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestApiV1Prefix:
    def test_ping_under_api_v1(self):
        resp = client.get("/api/v1/ping")
        assert resp.status_code == 200
        assert resp.json() == {"ping": "pong"}

    def test_openapi_under_api_v1(self):
        resp = client.get("/api/v1/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "Labelforge API"
        assert schema["info"]["version"] == "0.1.0"

    def test_docs_under_api_v1(self):
        resp = client.get("/api/v1/docs")
        assert resp.status_code == 200


class TestCorsHeaders:
    def test_cors_allows_configured_origins(self):
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


class TestConfig:
    def test_settings_load(self):
        from labelforge.config import settings
        assert settings.app_env == "development"
        assert settings.jwt_algorithm == "HS256"
        assert settings.s3_bucket == "labelforge-artifacts"
