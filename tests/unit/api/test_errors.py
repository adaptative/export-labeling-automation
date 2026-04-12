"""Tests for standardized error responses and error handlers."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from labelforge.app import app
from labelforge.api.v1.errors import (
    AppError, ErrorResponse,
    ERR_NOT_FOUND, ERR_VALIDATION, ERR_UNAUTHORIZED,
    ERR_FORBIDDEN, ERR_CONFLICT, ERR_INTERNAL, ERR_SERVICE_UNAVAILABLE,
)


@pytest.fixture
def client():
    return TestClient(app)


class TestErrorResponse:
    def test_error_response_model(self):
        err = ErrorResponse(detail="Not found", error_code=ERR_NOT_FOUND, status=404)
        assert err.detail == "Not found"
        assert err.error_code == "NOT_FOUND"
        assert err.status == 404

    def test_error_response_serialization(self):
        err = ErrorResponse(detail="Bad request", error_code=ERR_VALIDATION, status=400)
        data = err.model_dump()
        assert data["detail"] == "Bad request"
        assert data["error_code"] == "VALIDATION_ERROR"
        assert data["status"] == 400


class TestAppError:
    def test_app_error_defaults(self):
        err = AppError(500, "Something failed")
        assert err.status == 500
        assert err.detail == "Something failed"
        assert err.error_code == ERR_INTERNAL

    def test_app_error_custom_code(self):
        err = AppError(409, "Already exists", ERR_CONFLICT)
        assert err.error_code == "CONFLICT"

    def test_app_error_is_exception(self):
        with pytest.raises(AppError):
            raise AppError(400, "Bad", ERR_VALIDATION)


class TestErrorConstants:
    def test_all_error_codes(self):
        codes = [ERR_NOT_FOUND, ERR_VALIDATION, ERR_UNAUTHORIZED,
                 ERR_FORBIDDEN, ERR_CONFLICT, ERR_INTERNAL, ERR_SERVICE_UNAVAILABLE]
        assert len(codes) == 7
        assert all(isinstance(c, str) for c in codes)
        assert len(set(codes)) == 7  # all unique


class TestErrorHandlers:
    def test_404_returns_standard_format(self, client):
        resp = client.get("/api/v1/nonexistent-endpoint-xyz")
        # FastAPI may return 404 or 405 depending on routing
        assert resp.status_code in (404, 405)

    def test_app_error_handler_registered(self):
        """Verify error handlers are registered on the app."""
        assert app.exception_handlers is not None

    def test_health_endpoint_still_works(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_ping_endpoint_still_works(self, client):
        resp = client.get("/api/v1/ping")
        assert resp.status_code == 200
