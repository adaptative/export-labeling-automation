"""Shared fixtures for API tests — provides auth helpers and DB setup.

Each test gets a **fresh in-memory SQLite database** so that mutations
(password changes, profile updates, MFA toggles) never leak between tests.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from labelforge.api.v1.auth import _make_stub_jwt
from labelforge.app import app


@pytest.fixture
def client():
    """Test client backed by a disposable in-memory SQLite DB.

    Monkey-patches the DB engine/session-factory in both ``session`` and
    ``seed`` modules so that ``create_all_tables()`` and ``seed_if_empty()``
    (called during the FastAPI lifespan) operate on the ephemeral database.
    The original objects are restored after the test completes.
    """
    from labelforge.db import session as session_mod, seed as seed_mod

    # ── Save originals ──────────────────────────────────────────────────
    orig_engine = session_mod.engine
    orig_factory = session_mod.async_session_factory
    orig_seed_factory = seed_mod.async_session_factory

    # ── In-memory engine (StaticPool keeps one connection alive) ─────────
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False,
    )

    # ── Patch module globals so lifespan + routes use the test DB ────────
    session_mod.engine = test_engine
    session_mod.async_session_factory = test_factory
    seed_mod.async_session_factory = test_factory

    with TestClient(app) as c:
        yield c

    # ── Restore originals ───────────────────────────────────────────────
    session_mod.engine = orig_engine
    session_mod.async_session_factory = orig_factory
    seed_mod.async_session_factory = orig_seed_factory


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
