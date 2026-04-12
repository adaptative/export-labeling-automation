"""Tests for labelforge.core.cost_breaker — TASK-006."""
import pytest
from unittest.mock import MagicMock

from labelforge.core.cost_breaker import (
    CostBreaker,
    CostBreakerBreach,
    CostEvent,
    CostScope,
    DEFAULT_LIMITS,
    REDIS_TTL_SECONDS,
    WARN_THRESHOLD,
    clear_cost_events,
    get_cost_events,
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

    def test_warn_threshold_is_80_pct(self):
        assert WARN_THRESHOLD == 0.80

    def test_redis_ttl_is_25h(self):
        assert REDIS_TTL_SECONDS == 90000


class TestCheck:
    def setup_method(self):
        clear_cost_events()

    @pytest.mark.asyncio
    async def test_raises_breach_on_exceed(self, breaker, redis):
        redis._data["cost:request:req-1"] = 0.40
        with pytest.raises(CostBreakerBreach) as exc_info:
            await breaker.check(CostScope.REQUEST, "req-1", 0.20)
        assert exc_info.value.scope == CostScope.REQUEST
        assert exc_info.value.current == pytest.approx(0.60)
        assert exc_info.value.limit == 0.50

    @pytest.mark.asyncio
    async def test_breach_creates_cost_event(self, breaker, redis):
        redis._data["cost:request:req-1"] = 0.40
        with pytest.raises(CostBreakerBreach):
            await breaker.check(CostScope.REQUEST, "req-1", 0.20)
        events = get_cost_events()
        assert len(events) == 1
        assert events[0].event_type == "breach"
        assert events[0].scope == CostScope.REQUEST

    @pytest.mark.asyncio
    async def test_returns_true_at_warning_threshold(self, breaker, redis):
        redis._data["cost:request:req-1"] = 0.35
        result = await breaker.check(CostScope.REQUEST, "req-1", 0.06)
        assert result is True

    @pytest.mark.asyncio
    async def test_warning_creates_cost_event(self, breaker, redis):
        redis._data["cost:request:req-1"] = 0.35
        await breaker.check(CostScope.REQUEST, "req-1", 0.06)
        events = get_cost_events()
        assert any(e.event_type == "warning" for e in events)

    @pytest.mark.asyncio
    async def test_warning_callback_called(self, redis):
        callback = MagicMock()
        breaker = CostBreaker(redis, on_warn=callback)
        redis._data["cost:request:req-1"] = 0.35
        await breaker.check(CostScope.REQUEST, "req-1", 0.06)
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_below_warning(self, breaker, redis):
        result = await breaker.check(CostScope.REQUEST, "req-1", 0.10)
        assert result is False

    @pytest.mark.asyncio
    async def test_independent_scopes(self, breaker, redis):
        redis._data["cost:request:entity-1"] = 0.50
        with pytest.raises(CostBreakerBreach):
            await breaker.check(CostScope.REQUEST, "entity-1", 0.10)
        result = await breaker.check(CostScope.ORDER, "entity-1", 0.10)
        assert result is False


class TestRecord:
    def setup_method(self):
        clear_cost_events()

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
        assert redis._ttls[key] == REDIS_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_does_not_reset_ttl_on_subsequent_writes(self, breaker, redis):
        key = "cost:tenant_day:t-1"
        await breaker.record(CostScope.TENANT_DAY, "t-1", 1.00)
        redis._ttls[key] = 80000
        await breaker.record(CostScope.TENANT_DAY, "t-1", 2.00)
        assert redis._ttls[key] == 80000

    @pytest.mark.asyncio
    async def test_record_creates_charge_event(self, breaker, redis):
        await breaker.record(CostScope.ORDER, "ord-1", 5.00)
        events = get_cost_events()
        assert any(e.event_type == "charge" for e in events)


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


class TestGetUsagePct:
    @pytest.mark.asyncio
    async def test_zero_when_no_usage(self, breaker):
        result = await breaker.get_usage_pct(CostScope.REQUEST, "new")
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_50_pct(self, breaker, redis):
        redis._data["cost:request:req-1"] = 0.25
        result = await breaker.get_usage_pct(CostScope.REQUEST, "req-1")
        assert result == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_100_pct(self, breaker, redis):
        redis._data["cost:request:req-1"] = 0.50
        result = await breaker.get_usage_pct(CostScope.REQUEST, "req-1")
        assert result == pytest.approx(100.0)


class TestReset:
    @pytest.mark.asyncio
    async def test_resets_counter(self, breaker, redis):
        redis._data["cost:request:req-1"] = 0.40
        await breaker.reset(CostScope.REQUEST, "req-1")
        result = await breaker.get_current(CostScope.REQUEST, "req-1")
        assert result == 0.0


class TestCostEventModel:
    def test_to_dict(self):
        event = CostEvent(
            scope=CostScope.REQUEST,
            entity_id="req-1",
            amount=0.15,
            current_total=0.30,
            limit=0.50,
            event_type="charge",
        )
        d = event.to_dict()
        assert d["scope"] == "request"
        assert d["entity_id"] == "req-1"
        assert d["amount"] == 0.15
        assert "timestamp" in d
