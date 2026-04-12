"""Four-level cost circuit breakers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class CostScope(str, Enum):
    REQUEST = "request"
    DOCUMENT = "document"
    ORDER = "order"
    TENANT_DAY = "tenant_day"


DEFAULT_LIMITS = {
    CostScope.REQUEST: 0.50,
    CostScope.DOCUMENT: 2.00,
    CostScope.ORDER: 20.00,
    CostScope.TENANT_DAY: 200.00,
}

WARN_THRESHOLD = 0.80  # 80%


class CostBreakerBreach(Exception):
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


class CostBreaker:
    def __init__(self, redis_client, limits: Optional[Dict] = None):
        self.redis = redis_client
        self.limits = limits or dict(DEFAULT_LIMITS)

    def _key(self, scope: CostScope, entity_id: str) -> str:
        return f"cost:{scope.value}:{entity_id}"

    async def check(
        self, scope: CostScope, entity_id: str, estimated_cost: float
    ) -> bool:
        key = self._key(scope, entity_id)
        current = float(await self.redis.get(key) or 0)
        limit = self.limits[scope]
        if current + estimated_cost > limit:
            raise CostBreakerBreach(scope, current + estimated_cost, limit)
        if current + estimated_cost > limit * WARN_THRESHOLD:
            return True  # Warning threshold
        return False

    async def record(
        self, scope: CostScope, entity_id: str, actual_cost: float
    ) -> float:
        key = self._key(scope, entity_id)
        new_total = await self.redis.incrbyfloat(key, actual_cost)
        ttl = await self.redis.ttl(key)
        if ttl < 0:
            await self.redis.expire(key, 90000)  # 25 hours
        return float(new_total)

    async def get_current(self, scope: CostScope, entity_id: str) -> float:
        key = self._key(scope, entity_id)
        return float(await self.redis.get(key) or 0)
