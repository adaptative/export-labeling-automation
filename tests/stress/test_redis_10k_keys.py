"""Stress: CostBreaker with 10K+ Redis keys (TASK-045).

Acceptance criteria from #88:
- CostBreaker writes 10K distinct tenant/day keys without degradation.
- Reads after write remain O(1) — p95 < 10ms on StubRedis.
- No key leaks: every key we wrote can be queried back.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from labelforge.core.cost_breaker import (
    CostBreaker,
    CostScope,
    clear_cost_events,
)
from tests.stubs import StubRedis


pytestmark = pytest.mark.stress


@pytest.fixture(autouse=True)
def _clear_events():
    clear_cost_events()
    yield
    clear_cost_events()


class Test10KKeys:
    @pytest.mark.asyncio
    async def test_sequential_writes_10k_tenants(self):
        redis = StubRedis()
        # Lift tenant/day limit sky-high so we don't breach while seeding.
        breaker = CostBreaker(
            redis,
            limits={
                CostScope.REQUEST: 10_000.0,
                CostScope.DOCUMENT: 10_000.0,
                CostScope.ORDER: 10_000.0,
                CostScope.TENANT_DAY: 10_000.0,
            },
        )

        t0 = time.perf_counter()
        for i in range(10_000):
            await breaker.record(
                CostScope.TENANT_DAY, f"tnt-{i:06d}", 0.01
            )
        elapsed = time.perf_counter() - t0

        # 10K writes should comfortably finish under 5s on CI.
        assert elapsed < 5.0, f"10K writes took {elapsed:.2f}s"
        # Every key should exist in the backing store.
        assert len(redis._data) == 10_000

    @pytest.mark.asyncio
    async def test_read_back_latency_after_10k_writes(self):
        redis = StubRedis()
        breaker = CostBreaker(
            redis,
            limits={s: 10_000.0 for s in CostScope},
        )
        for i in range(10_000):
            await breaker.record(CostScope.TENANT_DAY, f"tnt-{i:06d}", 0.5)

        # Sample 200 random-ish reads, check p95.
        samples = []
        for i in range(0, 10_000, 50):
            t0 = time.perf_counter()
            val = await breaker.get_current(CostScope.TENANT_DAY, f"tnt-{i:06d}")
            samples.append((time.perf_counter() - t0) * 1000)
            assert val == pytest.approx(0.5)

        samples.sort()
        p95 = samples[int(len(samples) * 0.95)]
        assert p95 < 10, f"p95 read latency {p95:.3f} ms"

    @pytest.mark.asyncio
    async def test_concurrent_writes_same_tenant(self):
        """INCRBYFLOAT must be atomic in the real backend; StubRedis mimics
        this with a single-threaded event loop. 500 concurrent records on one
        tenant should sum to exactly 500 × amount."""
        redis = StubRedis()
        breaker = CostBreaker(
            redis,
            limits={s: 10_000.0 for s in CostScope},
        )

        async def bump():
            await breaker.record(CostScope.TENANT_DAY, "tnt-hot", 0.1)

        await asyncio.gather(*(bump() for _ in range(500)))
        total = await breaker.get_current(CostScope.TENANT_DAY, "tnt-hot")
        assert total == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_keys_are_namespaced_by_scope(self):
        """Cross-scope keys under the same entity must not collide."""
        redis = StubRedis()
        breaker = CostBreaker(
            redis,
            limits={s: 10_000.0 for s in CostScope},
        )
        for scope in CostScope:
            await breaker.record(scope, "ent-shared", 1.0)
        # One key per scope → 4 distinct keys for a single entity.
        assert len(redis._data) == 4
        for scope in CostScope:
            assert redis._data[f"cost:{scope.value}:ent-shared"] == 1.0

    @pytest.mark.asyncio
    async def test_reset_removes_single_key_only(self):
        redis = StubRedis()
        breaker = CostBreaker(
            redis,
            limits={s: 10_000.0 for s in CostScope},
        )
        # Seed 100 distinct tenants.
        for i in range(100):
            await breaker.record(CostScope.TENANT_DAY, f"tnt-{i:03d}", 1.0)
        # Reset one tenant — 99 must remain.
        await breaker.reset(CostScope.TENANT_DAY, "tnt-050")
        assert len(redis._data) == 99
        # Reset idempotent: resetting an absent key should not raise.
        await breaker.reset(CostScope.TENANT_DAY, "tnt-does-not-exist")
        assert len(redis._data) == 99
