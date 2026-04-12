"""Tests for labelforge.core.cost_breaker — TASK-006."""
import pytest
from unittest.mock import AsyncMock

from labelforge.core.cost_breaker import (
    CostBreaker,
    CostBreakerBreach,
    CostScope,
    DEFAULT_LIMITS,
    WARN_THRESHOLD,
)
from tests.stubs import Redis


@pytest.fixture
def breaker(redis):
    return CostBreaker(redis)


class TestCostScopes:
    def test_four_scopes_exist(self):
        assert len(CostScope) == 4

    def test_scope_values(self):
        assert CostScope.REQUEST.value == "request"
        assert CostScope.DOCUMENT.value == "document"
        assert CostScope.ORDER.value == "order"
        assert CostScope.TENANT_DAY.value == "tenant_day"


class TestDefaultLimits:
    def test_request_limit(self):
        assert DEFAULT_LIMITS[CostScope.REQUEST] == 0.50

    def test_document_limit(self):
        assert DEFAULT_LIMITS[CostScope.DOCUMENT] == 2.00

    def test_order_limit(self):
        assert DEFAULT_LIMITS[CostScope.ORDER] == 20.00

    def test_tenant_day_limit(self):
        assert DEFAULT_LIMITS[CostScope.TENANT_DAY] == 200.00


class TestCheck:
    @pytest.mark.asyncio
    async def test_raises_breach_on_exceed(self, breaker, redis):
        redis._data["cost:request:req-1"] = 0.40
        with pytest.raises(CostBreakerBreach) as exc_info:
            await breaker.check(CostScope.REQUEST, "req-1", 0.20)
        assert exc_info.value.scope == CostScope.REQUEST
        assert exc_info.value.current == pytest.approx(0.60)
        assert exc_info.value.limit == 0.50

    @pytest.mark.asyncio
    async def test_returns_true_at_warning_threshold(self, breaker, redis):
        # 80% of 0.50 = 0.40; set current to 0.35, add 0.06 = 0.41 > 0.40
        redis._data["cost:request:req-1"] = 0.35
        result = await breaker.check(CostScope.REQUEST, "req-1", 0.06)
        assert result is True  # warning

    @pytest.mark.asyncio
    async def test_returns_false_below_warning(self, breaker, redis):
        result = await breaker.check(CostScope.REQUEST, "req-1", 0.10)
        assert result is False

    @pytest.mark.asyncio
    async def test_independent_scopes(self, breaker, redis):
        # Breach request scope
        redis._data["cost:request:entity-1"] = 0.50
        with pytest.raises(CostBreakerBreach):
            await breaker.check(CostScope.REQUEST, "entity-1", 0.10)
        # Order scope for same entity should be fine
        result = await breaker.check(CostScope.ORDER, "entity-1", 0.10)
        assert result is False


class TestRecord:
    @pytest.mark.asyncio
    async def test_increments_cost(self, breaker, redis):
        total = await breaker.record(CostScope.REQUEST, "req-1", 0.15)
        assert total == pytest.approx(0.15)
        total = await breaker.record(CostScope.REQUEST, "req-1", 0.10)
        assert total == pytest.approx(0.25)

    @pytest.mark.asyncio
    async def test_sets_ttl_25h_on_first_write(self, breaker, redis):
        await breaker.record(CostScope.TENANT_DAY, "t-1", 1.00)
        key = "cost:tenant_day:t-1"
        assert redis._ttls[key] == 90000

    @pytest.mark.asyncio
    async def test_does_not_reset_ttl_on_subsequent_writes(self, breaker, redis):
        key = "cost:tenant_day:t-1"
        await breaker.record(CostScope.TENANT_DAY, "t-1", 1.00)
        # Simulate TTL already set (positive value)
        redis._ttls[key] = 80000
        await breaker.record(CostScope.TENANT_DAY, "t-1", 2.00)
        # TTL should not be reset
        assert redis._ttls[key] == 80000


class TestPerTenantOverrides:
    @pytest.mark.asyncio
    async def test_custom_limits(self, redis):
        custom_limits = {
            CostScope.REQUEST: 1.00,
            CostScope.DOCUMENT: 5.00,
            CostScope.ORDER: 50.00,
            CostScope.TENANT_DAY: 500.00,
        }
        breaker = CostBreaker(redis, limits=custom_limits)
        # Should not breach at 0.60 (default limit 0.50, custom 1.00)
        result = await breaker.check(CostScope.REQUEST, "req-1", 0.60)
        assert result is False

    @pytest.mark.asyncio
    async def test_custom_limits_still_breach(self, redis):
        custom_limits = dict(DEFAULT_LIMITS)
        custom_limits[CostScope.REQUEST] = 0.30
        breaker = CostBreaker(redis, limits=custom_limits)
        with pytest.raises(CostBreakerBreach):
            await breaker.check(CostScope.REQUEST, "req-1", 0.40)


class TestGetCurrent:
    @pytest.mark.asyncio
    async def test_returns_zero_for_new_entity(self, breaker):
        result = await breaker.get_current(CostScope.REQUEST, "new-entity")
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_returns_accumulated_cost(self, breaker, redis):
        redis._data["cost:order:ord-1"] = 15.50
        result = await breaker.get_current(CostScope.ORDER, "ord-1")
        assert result == pytest.approx(15.50)
