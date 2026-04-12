"""Root conftest — shared fixtures for all Labelforge tests.

When real APIs become available, update the imports below from
`tests.stubs` to point at the real implementations. All test files
that use these fixtures will automatically pick up the real classes.

Example swap:
    # Before (stubs):
    from tests.stubs import StubLLMProvider, StubRedis

    # After (real):
    from labelforge.services.llm_provider import AnthropicLLMProvider as StubLLMProvider
    import redis.asyncio as aioredis
    StubRedis = aioredis.Redis
"""
from __future__ import annotations

import pytest

from tests.stubs import (
    StubLLMProvider,
    StubRedis,
    StubDB,
    StubArtifactRecord,
    StubProvenance,
)


# ---------------------------------------------------------------------------
# LLM Provider
# ---------------------------------------------------------------------------


@pytest.fixture
def llm_provider():
    """LLM provider fixture. Swap to real provider by changing the import above."""
    return StubLLMProvider()


@pytest.fixture
def llm_provider_factory():
    """Factory fixture for LLM providers with custom config."""
    def _factory(default_content: str = "PURCHASE_ORDER", cost: float = 0.003):
        return StubLLMProvider(default_content=default_content, cost=cost)
    return _factory


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------


@pytest.fixture
def redis():
    """Redis fixture. Swap to real Redis by changing the import above."""
    return StubRedis()


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Database session fixture. Swap to real DB session factory."""
    return StubDB()


@pytest.fixture
def stub_artifact_record():
    """Factory for creating artifact records."""
    def _factory(artifact_id: str, s3_path: str, content_hash: str):
        return StubArtifactRecord(
            artifact_id=artifact_id,
            s3_path=s3_path,
            content_hash=content_hash,
        )
    return _factory


@pytest.fixture
def provenance():
    """Provenance emitter fixture. Swap to real emitter."""
    return StubProvenance()
