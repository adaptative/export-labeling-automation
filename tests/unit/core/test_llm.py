"""Tests for AI provider interface, cost estimation, caching, and fallback."""
from __future__ import annotations

import pytest

from labelforge.core.llm import (
    REDIS_CACHE_TTL,
    TOKEN_PRICING,
    CompletionCache,
    CompletionResult,
    FallbackProvider,
    LLMProvider,
    OpenAIProvider,
    RedisCompletionCache,
    StubProvider,
    cache_key,
    estimate_cost,
    get_default_cache,
    set_default_cache,
)
from tests.stubs import StubRedis


class TestTokenPricing:
    def test_pricing_table_has_entries(self):
        assert len(TOKEN_PRICING) >= 3

    def test_all_entries_have_input_output(self):
        for model, pricing in TOKEN_PRICING.items():
            assert "input" in pricing, f"{model} missing input pricing"
            assert "output" in pricing, f"{model} missing output pricing"
            assert pricing["input"] > 0
            assert pricing["output"] > 0

    def test_gpt54_pricing(self):
        p = TOKEN_PRICING["gpt-5.4"]
        assert p["input"] == 0.005
        assert p["output"] == 0.015


class TestEstimateCost:
    def test_basic_cost_calculation(self):
        cost = estimate_cost("gpt-5.4", 1000, 500)
        expected = (1000 / 1000 * 0.005) + (500 / 1000 * 0.015)
        assert cost == round(expected, 6)

    def test_zero_tokens(self):
        cost = estimate_cost("gpt-5.4", 0, 0)
        assert cost == 0.0

    def test_unknown_model_returns_zero(self):
        cost = estimate_cost("unknown-model", 1000, 500)
        assert cost == 0.0

    def test_cost_increases_with_tokens(self):
        c1 = estimate_cost("gpt-5.4", 100, 100)
        c2 = estimate_cost("gpt-5.4", 1000, 1000)
        assert c2 > c1

    def test_gpt4o_vs_mini_pricing(self):
        full = estimate_cost("gpt-4o", 1000, 1000)
        mini = estimate_cost("gpt-4o-mini", 1000, 1000)
        assert full > mini


class TestCompletionResult:
    def test_total_tokens(self):
        r = CompletionResult(
            content="hello", model="test", input_tokens=100,
            output_tokens=50, cost_usd=0.01, latency_ms=100.0,
        )
        assert r.total_tokens == 150

    def test_cached_flag_default_false(self):
        r = CompletionResult(
            content="", model="test", input_tokens=0,
            output_tokens=0, cost_usd=0.0, latency_ms=0.0,
        )
        assert r.cached is False

    def test_metadata_default_empty(self):
        r = CompletionResult(
            content="", model="test", input_tokens=0,
            output_tokens=0, cost_usd=0.0, latency_ms=0.0,
        )
        assert r.metadata == {}


class TestCacheKey:
    def test_deterministic(self):
        msgs = [{"role": "user", "content": "hello"}]
        k1 = cache_key("model-a", msgs)
        k2 = cache_key("model-a", msgs)
        assert k1 == k2

    def test_different_models_different_keys(self):
        msgs = [{"role": "user", "content": "hello"}]
        k1 = cache_key("model-a", msgs)
        k2 = cache_key("model-b", msgs)
        assert k1 != k2

    def test_different_messages_different_keys(self):
        k1 = cache_key("model", [{"role": "user", "content": "hello"}])
        k2 = cache_key("model", [{"role": "user", "content": "world"}])
        assert k1 != k2

    def test_key_is_sha256_hex(self):
        key = cache_key("model", [{"role": "user", "content": "test"}])
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


class TestCompletionCache:
    def test_put_and_get(self):
        cache = CompletionCache()
        result = CompletionResult(
            content="cached", model="m", input_tokens=10,
            output_tokens=5, cost_usd=0.01, latency_ms=50.0,
        )
        cache.put("key1", result)
        assert cache.get("key1") is result

    def test_miss_returns_none(self):
        cache = CompletionCache()
        assert cache.get("nonexistent") is None

    def test_hit_counter(self):
        cache = CompletionCache()
        result = CompletionResult(
            content="", model="m", input_tokens=0,
            output_tokens=0, cost_usd=0.0, latency_ms=0.0,
        )
        cache.put("k", result)
        cache.get("k")
        cache.get("k")
        assert cache.hits == 2

    def test_miss_counter(self):
        cache = CompletionCache()
        cache.get("x")
        cache.get("y")
        assert cache.misses == 2

    def test_clear(self):
        cache = CompletionCache()
        result = CompletionResult(
            content="", model="m", input_tokens=0,
            output_tokens=0, cost_usd=0.0, latency_ms=0.0,
        )
        cache.put("k", result)
        cache.get("k")
        cache.clear()
        assert cache.get("k") is None
        assert cache.hits == 0
        assert cache.misses == 1  # The get after clear

    def test_default_cache_singleton(self):
        c1 = get_default_cache()
        c2 = get_default_cache()
        assert c1 is c2


class TestRedisCompletionCache:
    """Tests for Redis-backed completion cache using StubRedis."""

    def _make_result(self, content="cached response") -> CompletionResult:
        return CompletionResult(
            content=content, model="gpt-5.4", input_tokens=100,
            output_tokens=50, cost_usd=0.01, latency_ms=120.0,
            provider="openai", metadata={"finish_reason": "stop"},
        )

    @pytest.mark.asyncio
    async def test_aput_and_aget(self):
        redis = StubRedis()
        cache = RedisCompletionCache(redis)
        result = self._make_result()
        await cache.aput("key1", result)
        cached = await cache.aget("key1")
        assert cached is not None
        assert cached.content == "cached response"
        assert cached.model == "gpt-5.4"
        assert cached.input_tokens == 100
        assert cached.output_tokens == 50
        assert cached.cached is True  # deserialized as cached
        assert cached.provider == "openai"

    @pytest.mark.asyncio
    async def test_aget_miss_returns_none(self):
        redis = StubRedis()
        cache = RedisCompletionCache(redis)
        assert await cache.aget("nonexistent") is None

    @pytest.mark.asyncio
    async def test_hit_counter(self):
        redis = StubRedis()
        cache = RedisCompletionCache(redis)
        await cache.aput("k", self._make_result())
        await cache.aget("k")
        await cache.aget("k")
        assert cache.hits == 2

    @pytest.mark.asyncio
    async def test_miss_counter(self):
        redis = StubRedis()
        cache = RedisCompletionCache(redis)
        await cache.aget("x")
        await cache.aget("y")
        assert cache.misses == 2

    @pytest.mark.asyncio
    async def test_ttl_set_on_put(self):
        redis = StubRedis()
        cache = RedisCompletionCache(redis, ttl=3600)
        await cache.aput("k", self._make_result())
        assert redis._ttls.get("llm:cache:k") == 3600

    @pytest.mark.asyncio
    async def test_default_ttl(self):
        redis = StubRedis()
        cache = RedisCompletionCache(redis)
        await cache.aput("k", self._make_result())
        assert redis._ttls.get("llm:cache:k") == REDIS_CACHE_TTL

    @pytest.mark.asyncio
    async def test_custom_prefix(self):
        redis = StubRedis()
        cache = RedisCompletionCache(redis, prefix="myapp:llm:")
        await cache.aput("k", self._make_result())
        assert "myapp:llm:k" in redis._data

    @pytest.mark.asyncio
    async def test_serialization_round_trip(self):
        """All CompletionResult fields survive serialize/deserialize."""
        redis = StubRedis()
        cache = RedisCompletionCache(redis)
        original = CompletionResult(
            content="hello world", model="gpt-4o", input_tokens=200,
            output_tokens=100, cost_usd=0.02, latency_ms=250.5,
            provider="openai", metadata={"finish_reason": "stop", "extra": 42},
        )
        await cache.aput("round_trip", original)
        cached = await cache.aget("round_trip")
        assert cached.content == original.content
        assert cached.model == original.model
        assert cached.input_tokens == original.input_tokens
        assert cached.output_tokens == original.output_tokens
        assert cached.cost_usd == original.cost_usd
        assert cached.latency_ms == original.latency_ms
        assert cached.provider == original.provider
        assert cached.metadata == original.metadata

    @pytest.mark.asyncio
    async def test_sync_get_returns_none(self):
        """Sync get() always misses for Redis cache — must use aget()."""
        redis = StubRedis()
        cache = RedisCompletionCache(redis)
        await cache.aput("k", self._make_result())
        assert cache.get("k") is None  # sync not supported

    @pytest.mark.asyncio
    async def test_redis_error_graceful_get(self):
        """Redis errors on get return None instead of crashing."""
        class BrokenRedis:
            async def get(self, key):
                raise ConnectionError("Redis down")
            async def set(self, key, value, ex=None):
                pass

        cache = RedisCompletionCache(BrokenRedis())
        result = await cache.aget("k")
        assert result is None
        assert cache.misses == 1

    @pytest.mark.asyncio
    async def test_redis_error_graceful_put(self):
        """Redis errors on put are logged but don't crash."""
        class BrokenRedis:
            async def set(self, key, value, ex=None):
                raise ConnectionError("Redis down")

        cache = RedisCompletionCache(BrokenRedis())
        # Should not raise
        await cache.aput("k", self._make_result())

    @pytest.mark.asyncio
    async def test_clear_resets_counters(self):
        redis = StubRedis()
        cache = RedisCompletionCache(redis)
        await cache.aput("k", self._make_result())
        await cache.aget("k")
        cache.clear()
        assert cache.hits == 0
        assert cache.misses == 0


class TestSetDefaultCache:
    def test_set_and_get(self):
        original = get_default_cache()
        redis = StubRedis()
        new_cache = RedisCompletionCache(redis)
        set_default_cache(new_cache)
        assert get_default_cache() is new_cache
        # Restore
        set_default_cache(original)


class TestCompleteWithCacheRedis:
    """Test complete_with_cache works with RedisCompletionCache."""

    @pytest.mark.asyncio
    async def test_redis_cache_with_provider(self):
        redis = StubRedis()
        cache = RedisCompletionCache(redis)
        provider = StubProvider()
        msgs = [{"role": "user", "content": "redis test"}]

        r1 = await provider.complete_with_cache("gpt-5.4", msgs, cache=cache)
        assert r1.cached is False
        assert cache.hits == 0
        assert cache.misses == 1

        r2 = await provider.complete_with_cache("gpt-5.4", msgs, cache=cache)
        assert r2.cached is True
        assert r2.cost_usd == 0.0
        assert cache.hits == 1


class TestOpenAIProvider:
    def test_requires_api_key(self):
        with pytest.raises(ValueError, match="API key is required"):
            OpenAIProvider(api_key="")

    def test_provider_name(self):
        provider = OpenAIProvider(api_key="sk-test-key")
        assert provider.name == "openai"

    def test_is_llm_provider(self):
        assert isinstance(OpenAIProvider(api_key="sk-test"), LLMProvider)


class TestStubProvider:
    @pytest.mark.asyncio
    async def test_complete_returns_result(self):
        provider = StubProvider()
        result = await provider.complete(
            model="gpt-5.4",
            messages=[{"role": "user", "content": "Hello world"}],
        )
        assert isinstance(result, CompletionResult)
        assert result.model == "gpt-5.4"
        assert result.provider == "stub"
        assert result.input_tokens > 0
        assert result.output_tokens > 0
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_complete_with_cache(self):
        provider = StubProvider()
        cache = CompletionCache()
        msgs = [{"role": "user", "content": "cached test"}]

        r1 = await provider.complete_with_cache("gpt-5.4", msgs, cache=cache)
        assert r1.cached is False
        assert cache.hits == 0

        r2 = await provider.complete_with_cache("gpt-5.4", msgs, cache=cache)
        assert r2.cached is True
        assert r2.cost_usd == 0.0
        assert cache.hits == 1

    @pytest.mark.asyncio
    async def test_set_response(self):
        provider = StubProvider()
        provider.set_response("classify", "PURCHASE_ORDER")
        result = await provider.complete(
            model="gpt-5.4",
            messages=[{"role": "user", "content": "classify this document"}],
        )
        assert result.content == "PURCHASE_ORDER"

    @pytest.mark.asyncio
    async def test_tracks_calls(self):
        provider = StubProvider()
        await provider.complete("gpt-5.4", [{"role": "user", "content": "test"}])
        assert len(provider.calls) == 1
        assert provider.calls[0]["model"] == "gpt-5.4"

    def test_provider_name(self):
        assert StubProvider().name == "stub"

    def test_is_llm_provider(self):
        assert isinstance(StubProvider(), LLMProvider)


class TestFallbackProvider:
    def test_requires_at_least_one_provider(self):
        with pytest.raises(ValueError):
            FallbackProvider(providers=[])

    def test_name(self):
        fb = FallbackProvider(providers=[StubProvider()])
        assert fb.name == "fallback"

    @pytest.mark.asyncio
    async def test_uses_first_provider(self):
        fb = FallbackProvider(providers=[StubProvider()])
        result = await fb.complete(
            "gpt-5.4",
            [{"role": "user", "content": "test"}],
        )
        assert result.provider == "stub"

    @pytest.mark.asyncio
    async def test_fallback_on_failure(self):
        class FailProvider(LLMProvider):
            @property
            def name(self):
                return "fail"

            async def complete(self, model, messages, **kwargs):
                raise RuntimeError("intentional failure")

        fb = FallbackProvider(providers=[FailProvider(), StubProvider()])
        result = await fb.complete(
            "gpt-5.4",
            [{"role": "user", "content": "test"}],
        )
        assert result.provider == "stub"

    @pytest.mark.asyncio
    async def test_all_fail_raises(self):
        class FailProvider(LLMProvider):
            @property
            def name(self):
                return "fail"

            async def complete(self, model, messages, **kwargs):
                raise RuntimeError("boom")

        fb = FallbackProvider(providers=[FailProvider()])
        with pytest.raises(RuntimeError, match="All 1 providers failed"):
            await fb.complete("model", [{"role": "user", "content": "test"}])
