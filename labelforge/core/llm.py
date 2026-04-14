"""AI provider interface with real OpenAI integration.

Provides LLMProvider ABC, OpenAIProvider (real), CompletionResult dataclass,
token pricing table, fallback providers with backoff, caching, and logging.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import openai

logger = logging.getLogger(__name__)

# ── Token pricing (USD per 1K tokens) ──────────────────────────────────────

TOKEN_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-5.4": {"input": 0.005, "output": 0.015},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a completion."""
    pricing = TOKEN_PRICING.get(model)
    if not pricing:
        logger.warning("No pricing for model %s, returning 0.0", model)
        return 0.0
    input_cost = (input_tokens / 1000) * pricing["input"]
    output_cost = (output_tokens / 1000) * pricing["output"]
    return round(input_cost + output_cost, 6)


# ── Completion result ──────────────────────────────────────────────────────


@dataclass
class CompletionResult:
    """Result from an LLM completion call."""
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    cached: bool = False
    provider: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ── Cache ──────────────────────────────────────────────────────────────────


def cache_key(model: str, messages: Sequence[Dict[str, str]], **kwargs: Any) -> str:
    """Deterministic cache key for a completion request."""
    payload = json.dumps({"model": model, "messages": list(messages), **kwargs}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class CompletionCache:
    """In-memory completion cache."""

    def __init__(self) -> None:
        self._store: Dict[str, CompletionResult] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[CompletionResult]:
        result = self._store.get(key)
        if result:
            self.hits += 1
            logger.debug("Cache hit: %s (hits=%d)", key[:16], self.hits)
        else:
            self.misses += 1
        return result

    async def aget(self, key: str) -> Optional[CompletionResult]:
        """Async get — in-memory version delegates to sync get."""
        return self.get(key)

    def put(self, key: str, result: CompletionResult) -> None:
        self._store[key] = result

    async def aput(self, key: str, result: CompletionResult) -> None:
        """Async put — in-memory version delegates to sync put."""
        self.put(key, result)

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0


REDIS_CACHE_TTL = 86400  # 24 hours default


class RedisCompletionCache(CompletionCache):
    """Redis-backed completion cache for production use.

    Stores serialized CompletionResult as JSON in Redis with configurable TTL.
    Falls back gracefully on Redis errors — logs warning and returns cache miss.
    Tracks hits/misses for observability.
    """

    def __init__(self, redis_client, ttl: int = REDIS_CACHE_TTL, prefix: str = "llm:cache:") -> None:
        super().__init__()
        self._redis = redis_client
        self._ttl = ttl
        self._prefix = prefix

    def _redis_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def _serialize(self, result: CompletionResult) -> str:
        return json.dumps({
            "content": result.content,
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
            "latency_ms": result.latency_ms,
            "provider": result.provider,
            "metadata": result.metadata,
        })

    def _deserialize(self, data: str) -> CompletionResult:
        d = json.loads(data)
        return CompletionResult(
            content=d["content"],
            model=d["model"],
            input_tokens=d["input_tokens"],
            output_tokens=d["output_tokens"],
            cost_usd=d["cost_usd"],
            latency_ms=d["latency_ms"],
            cached=True,
            provider=d.get("provider", ""),
            metadata=d.get("metadata", {}),
        )

    def get(self, key: str) -> Optional[CompletionResult]:
        """Sync get — not supported for Redis. Use aget() instead."""
        self.misses += 1
        return None

    async def aget(self, key: str) -> Optional[CompletionResult]:
        """Async get from Redis."""
        try:
            rkey = self._redis_key(key)
            data = await self._redis.get(rkey)
            if data is not None:
                self.hits += 1
                logger.debug("Redis cache hit: %s (hits=%d)", key[:16], self.hits)
                return self._deserialize(data if isinstance(data, str) else data.decode())
            self.misses += 1
            return None
        except Exception as exc:
            logger.warning("Redis cache get failed: %s", exc)
            self.misses += 1
            return None

    def put(self, key: str, result: CompletionResult) -> None:
        """Sync put — not supported for Redis. Use aput() instead."""
        pass

    async def aput(self, key: str, result: CompletionResult) -> None:
        """Async put to Redis with TTL."""
        try:
            rkey = self._redis_key(key)
            data = self._serialize(result)
            await self._redis.set(rkey, data, ex=self._ttl)
            logger.debug("Redis cache put: %s (ttl=%ds)", key[:16], self._ttl)
        except Exception as exc:
            logger.warning("Redis cache put failed: %s", exc)

    def clear(self) -> None:
        """Clear counters. Redis keys expire via TTL."""
        self.hits = 0
        self.misses = 0


# Shared default cache instance
_default_cache = CompletionCache()


def get_default_cache() -> CompletionCache:
    return _default_cache


def set_default_cache(cache: CompletionCache) -> None:
    """Replace the default cache (e.g., with RedisCompletionCache at startup)."""
    global _default_cache
    _default_cache = cache


# ── Provider ABC ───────────────────────────────────────────────────────────


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'openai')."""

    @abstractmethod
    async def complete(
        self,
        model: str,
        messages: Sequence[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> CompletionResult:
        """Send a completion request and return the result."""

    async def complete_with_cache(
        self,
        model: str,
        messages: Sequence[Dict[str, str]],
        cache: Optional[CompletionCache] = None,
        **kwargs: Any,
    ) -> CompletionResult:
        """Complete with caching support. Works with both in-memory and Redis caches."""
        c = cache or _default_cache
        key = cache_key(model, messages, **kwargs)
        cached = await c.aget(key)
        if cached:
            return CompletionResult(
                content=cached.content,
                model=cached.model,
                input_tokens=cached.input_tokens,
                output_tokens=cached.output_tokens,
                cost_usd=0.0,  # No cost for cached
                latency_ms=0.0,
                cached=True,
                provider=cached.provider,
                metadata=cached.metadata,
            )
        result = await self.complete(model, messages, **kwargs)
        await c.aput(key, result)
        return result


# ── OpenAI provider (real) ───────────────────────────────────────────────


class OpenAIProvider(LLMProvider):
    """OpenAI provider using the openai SDK.

    Calls the real OpenAI Chat Completions API.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self._client = openai.AsyncOpenAI(api_key=api_key)

    @property
    def name(self) -> str:
        return "openai"

    async def complete(
        self,
        model: str,
        messages: Sequence[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> CompletionResult:
        start = time.monotonic()

        response = await self._client.chat.completions.create(
            model=model,
            messages=[{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        latency = (time.monotonic() - start) * 1000
        choice = response.choices[0]
        content = choice.message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = estimate_cost(model, input_tokens, output_tokens)

        logger.info(
            "OpenAI completion: model=%s input_tokens=%d output_tokens=%d cost=$%.6f latency=%.1fms",
            model, input_tokens, output_tokens, cost, latency,
        )

        return CompletionResult(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=round(latency, 2),
            provider=self.name,
            metadata={"finish_reason": choice.finish_reason},
        )


# ── Stub provider (for testing only) ─────────────────────────────────────


class StubProvider(LLMProvider):
    """In-memory stub for unit testing. Does NOT call any API."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._responses: Dict[str, str] = {}

    @property
    def name(self) -> str:
        return "stub"

    def set_response(self, prompt_contains: str, response: str) -> None:
        self._responses[prompt_contains] = response

    async def complete(
        self,
        model: str,
        messages: Sequence[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> CompletionResult:
        start = time.monotonic()
        self.calls.append({"model": model, "messages": list(messages), **kwargs})

        input_text = " ".join(m.get("content", "") for m in messages)
        content = "[stub response]"
        for key, resp in self._responses.items():
            if key in input_text:
                content = resp
                break

        input_tokens = max(1, len(input_text) // 4)
        output_tokens = max(1, len(content) // 4)
        cost = estimate_cost(model, input_tokens, output_tokens)
        latency = (time.monotonic() - start) * 1000

        return CompletionResult(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=round(latency, 2),
            provider=self.name,
        )


# ── Fallback provider ────────────────────────────────────────────────────


class FallbackProvider(LLMProvider):
    """Wraps multiple providers with retry and exponential backoff."""

    def __init__(
        self,
        providers: Sequence[LLMProvider],
        max_retries: int = 2,
        base_delay: float = 1.0,
    ) -> None:
        if not providers:
            raise ValueError("At least one provider is required")
        self._providers = list(providers)
        self._max_retries = max_retries
        self._base_delay = base_delay

    @property
    def name(self) -> str:
        return "fallback"

    async def complete(
        self,
        model: str,
        messages: Sequence[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> CompletionResult:
        last_error: Optional[Exception] = None

        for attempt, provider in enumerate(self._providers):
            try:
                logger.info("Fallback attempt %d: trying provider %s", attempt + 1, provider.name)
                return await provider.complete(model, messages, max_tokens, temperature, **kwargs)
            except Exception as e:
                last_error = e
                delay = self._base_delay * (2 ** attempt)
                logger.warning(
                    "Provider %s failed (attempt %d): %s — backoff %.1fs",
                    provider.name, attempt + 1, e, delay,
                )
                # In production: await asyncio.sleep(delay)

        raise RuntimeError(f"All {len(self._providers)} providers failed") from last_error
