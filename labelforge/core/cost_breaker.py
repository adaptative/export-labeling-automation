"""Four-level cost circuit breakers.

Four independent scopes: request ($0.50), document ($2), order ($20),
tenant/day ($200). Uses Redis INCRBYFLOAT for atomic cost tracking.

Pattern: estimate-before → LLM call → reconcile-after with actual cost.
Breach at 100% triggers CostBreakerBreach (HTTP 402).
Warning at 80% threshold for proactive alerting.
Redis TTL 25h (90000s) for daily tenant scope.
Per-tenant overrides supported via custom limits dict.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional


class CostScope(str, Enum):
    REQUEST = "request"
    DOCUMENT = "document"
    ORDER = "order"
    TENANT_DAY = "tenant_day"


DEFAULT_LIMITS: Dict[CostScope, float] = {
    CostScope.REQUEST: 0.50,
    CostScope.DOCUMENT: 2.00,
    CostScope.ORDER: 20.00,
    CostScope.TENANT_DAY: 200.00,
}

WARN_THRESHOLD = 0.80  # 80%
REDIS_TTL_SECONDS = 90000  # 25 hours


class CostBreakerBreach(Exception):
    """Raised when a cost limit is exceeded. Maps to HTTP 402."""

    def __init__(self, scope: CostScope, current: float, limit: float):
        self.scope = scope
        self.current = current
        self.limit = limit
        super().__init__(
            f"Cost breaker tripped: {scope.value} at ${current:.2f} "
            f"(limit ${limit:.2f})"
        )


@dataclass
class CostEstimate:
    scope: CostScope
    estimated_cost: float


@dataclass
class CostEvent:
    """Record of a cost event (breach, warning, or normal charge)."""
    scope: CostScope
    entity_id: str
    amount: float
    current_total: float
    limit: float
    event_type: str  # "breach", "warning", "charge"
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "scope": self.scope.value,
            "entity_id": self.entity_id,
            "amount": self.amount,
            "current_total": self.current_total,
            "limit": self.limit,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
        }


# In-memory event store for testing — in production, writes to cost_events table
_cost_events: List[CostEvent] = []


def get_cost_events() -> List[CostEvent]:
    return list(_cost_events)


def clear_cost_events() -> None:
    _cost_events.clear()


class CostBreaker:
    """Four-level cost circuit breaker with Redis backend."""

    def __init__(
        self,
        redis_client,
        limits: Optional[Dict[CostScope, float]] = None,
        on_warn: Optional[Callable[[CostEvent], None]] = None,
    ):
        self.redis = redis_client
        self.limits = limits or dict(DEFAULT_LIMITS)
        self.on_warn = on_warn

    def _key(self, scope: CostScope, entity_id: str) -> str:
        return f"cost:{scope.value}:{entity_id}"

    async def check(
        self, scope: CostScope, entity_id: str, estimated_cost: float
    ) -> bool:
        """Check if estimated cost would exceed limit.

        Returns True if warning threshold (80%) is exceeded.
        Raises CostBreakerBreach if limit would be exceeded.
        """
        key = self._key(scope, entity_id)
        current = float(await self.redis.get(key) or 0)
        limit = self.limits[scope]
        projected = current + estimated_cost

        if projected > limit:
            event = CostEvent(
                scope=scope,
                entity_id=entity_id,
                amount=estimated_cost,
                current_total=projected,
                limit=limit,
                event_type="breach",
            )
            _cost_events.append(event)
            raise CostBreakerBreach(scope, projected, limit)

        if projected > limit * WARN_THRESHOLD:
            event = CostEvent(
                scope=scope,
                entity_id=entity_id,
                amount=estimated_cost,
                current_total=projected,
                limit=limit,
                event_type="warning",
            )
            _cost_events.append(event)
            if self.on_warn:
                self.on_warn(event)
            return True

        return False

    async def record(
        self, scope: CostScope, entity_id: str, actual_cost: float
    ) -> float:
        """Record actual cost after LLM call (reconcile-after).

        Returns new total for the scope/entity.
        """
        key = self._key(scope, entity_id)
        new_total = await self.redis.incrbyfloat(key, actual_cost)
        ttl = await self.redis.ttl(key)
        if ttl < 0:
            await self.redis.expire(key, REDIS_TTL_SECONDS)

        event = CostEvent(
            scope=scope,
            entity_id=entity_id,
            amount=actual_cost,
            current_total=float(new_total),
            limit=self.limits[scope],
            event_type="charge",
        )
        _cost_events.append(event)
        return float(new_total)

    async def get_current(self, scope: CostScope, entity_id: str) -> float:
        """Get current accumulated cost for a scope/entity."""
        key = self._key(scope, entity_id)
        return float(await self.redis.get(key) or 0)

    async def get_usage_pct(self, scope: CostScope, entity_id: str) -> float:
        """Get current usage as a percentage of the limit."""
        current = await self.get_current(scope, entity_id)
        limit = self.limits[scope]
        if limit <= 0:
            return 0.0
        return (current / limit) * 100.0

    async def reset(self, scope: CostScope, entity_id: str) -> None:
        """Reset cost counter for a scope/entity (admin action)."""
        key = self._key(scope, entity_id)
        await self.redis.delete(key)
