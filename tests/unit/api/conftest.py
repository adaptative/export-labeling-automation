"""Shared fixtures for API tests — provides auth helpers and DB setup."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from labelforge.api.v1.auth import _make_stub_jwt
from labelforge.app import app


@pytest.fixture(scope="session")
def client():
    """Test client with lifespan (creates tables + seeds data)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_token():
    """Valid JWT for the admin user."""
    return _make_stub_jwt("usr-admin-001", "tnt-nakoda-001", "ADMIN", "admin@nakodacraft.com")


@pytest.fixture
def ops_token():
    """Valid JWT for the ops user."""
    return _make_stub_jwt("usr-ops-001", "tnt-nakoda-001", "OPS", "ops@nakodacraft.com")


@pytest.fixture
def admin_headers(admin_token):
    """Authorization headers for admin user."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def ops_headers(ops_token):
    """Authorization headers for ops user."""
    return {"Authorization": f"Bearer {ops_token}"}
