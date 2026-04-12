"""Centralized test stubs for Labelforge backend.

All fake/stub implementations live here so they can be swapped to real
implementations in one place when production APIs become available.

To swap a stub for a real implementation:
  1. Replace the class assignment below with the real import.
     For example, change:
         LLMProvider = StubLLMProvider
     to:
         from labelforge.services.llm_provider import OpenAILLMProvider as LLMProvider
  2. Update any fixture defaults in tests/conftest.py if the real class
     needs different constructor arguments (e.g., connection strings).
  3. Re-run: python -m pytest tests/ -v
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# LLM Provider stubs
# ---------------------------------------------------------------------------


@dataclass
class StubLLMResult:
    """Minimal LLM completion result for testing."""
    content: str
    cost: float = 0.003


class StubLLMProvider:
    """In-memory fake LLM provider.

    Swap with real provider:
        from labelforge.services.llm_provider import AnthropicLLMProvider as RealLLMProvider
    """

    def __init__(self, default_content: str = "PURCHASE_ORDER", cost: float = 0.003):
        self._default_content = default_content
        self._cost = cost
        self.calls: list[dict] = []

    async def complete(self, prompt: str, model_id: str = "", **kwargs):
        self.calls.append({"prompt": prompt, "model_id": model_id, **kwargs})
        return StubLLMResult(content=self._default_content, cost=self._cost)


# ---------------------------------------------------------------------------
# Redis stub
# ---------------------------------------------------------------------------


class StubRedis:
    """In-memory fake Redis for testing without a real Redis instance.

    Swap with real Redis:
        import redis.asyncio as aioredis
        RealRedis = aioredis.Redis
    """

    def __init__(self):
        self._data: dict[str, float] = {}
        self._ttls: dict[str, int] = {}
        self._sets: dict[str, set] = {}

    async def get(self, key: str):
        return self._data.get(key)

    async def incrbyfloat(self, key: str, amount: float) -> float:
        current = self._data.get(key, 0.0)
        new_val = current + amount
        self._data[key] = new_val
        return new_val

    async def ttl(self, key: str) -> int:
        return self._ttls.get(key, -1)

    async def expire(self, key: str, seconds: int):
        self._ttls[key] = seconds

    async def exists(self, key: str) -> bool:
        return key in self._data or key in self._sets

    async def set(self, key: str, value, **kwargs):
        self._data[key] = value

    async def delete(self, key: str):
        self._data.pop(key, None)
        self._sets.pop(key, None)


# ---------------------------------------------------------------------------
# Database / artifact stubs
# ---------------------------------------------------------------------------


@dataclass
class StubArtifactRecord:
    """Fake artifact record for reproduce/provenance tests.

    Swap with real ORM model:
        from labelforge.models.artifact import ArtifactRecord as RealArtifactRecord
    """
    artifact_id: str
    s3_path: str
    content_hash: str


class StubDB:
    """Minimal async DB stub for services that need database access.

    Swap with real database session:
        from labelforge.db.session import AsyncSessionFactory as RealDB
    """

    def __init__(self):
        self._artifacts: dict[str, StubArtifactRecord] = {}
        self._incidents: list[dict] = []

    def add_artifact(self, record: StubArtifactRecord):
        self._artifacts[record.artifact_id] = record

    async def get_artifact(self, artifact_id: str) -> Optional[StubArtifactRecord]:
        return self._artifacts.get(artifact_id)

    async def create_incident(self, incident_id, artifact_id, expected, actual):
        self._incidents.append({
            "incident_id": incident_id,
            "artifact_id": artifact_id,
            "expected": expected,
            "actual": actual,
        })


class StubProvenance:
    """Provenance emitter stub that computes sha256 without storage.

    Swap with real provenance:
        from labelforge.core.provenance import ProvenanceEmitter as RealProvenance
    """

    def compute_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Convenience aliases — change THESE when swapping to real implementations
# ---------------------------------------------------------------------------

# LLM
LLMProvider = StubLLMProvider
LLMResult = StubLLMResult

# Redis
Redis = StubRedis

# Database
DB = StubDB
ArtifactRecord = StubArtifactRecord
Provenance = StubProvenance
