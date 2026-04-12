"""Tests for LLMProvider, MockLLMProvider, and cost estimation."""
import asyncio

import pytest

from labelforge.services.llm_provider import (
    CompletionResult,
    MockLLMProvider,
    TOKEN_PRICING,
)


class TestCompletionResult:
    def test_fields_required(self):
        r = CompletionResult(
            content="hello",
            input_tokens=10,
            output_tokens=5,
            cost=0.001,
            model_id="test-model",
        )
        assert r.content == "hello"
        assert r.input_tokens == 10
        assert r.output_tokens == 5
        assert r.cost == 0.001
        assert r.model_id == "test-model"
        assert r.cached is False

    def test_cached_default_false(self):
        r = CompletionResult("x", 1, 1, 0.0, "m")
        assert r.cached is False

    def test_cached_explicit_true(self):
        r = CompletionResult("x", 1, 1, 0.0, "m", cached=True)
        assert r.cached is True


class TestTokenPricing:
    def test_sonnet_model_present(self):
        assert "claude-sonnet-4-20250514" in TOKEN_PRICING

    def test_haiku_model_present(self):
        assert "claude-haiku-4-5-20251001" in TOKEN_PRICING

    def test_pricing_keys(self):
        for model, pricing in TOKEN_PRICING.items():
            assert "input" in pricing
            assert "output" in pricing
            assert pricing["input"] > 0
            assert pricing["output"] > 0


class TestMockLLMProvider:
    def _run(self, coro):
        return asyncio.run(coro)

    def test_records_calls(self):
        provider = MockLLMProvider()
        self._run(provider.complete("hello", "claude-sonnet-4-20250514"))
        assert len(provider.calls) == 1
        assert provider.calls[0]["prompt"] == "hello"
        assert provider.calls[0]["model_id"] == "claude-sonnet-4-20250514"

    def test_records_multiple_calls(self):
        provider = MockLLMProvider()
        self._run(provider.complete("a", "m1"))
        self._run(provider.complete("b", "m2"))
        assert len(provider.calls) == 2

    def test_default_response(self):
        provider = MockLLMProvider()
        result = self._run(provider.complete("anything", "model"))
        assert result.content == "mock response"

    def test_configured_response(self):
        provider = MockLLMProvider()
        provider.set_response("translate", "translated text")
        result = self._run(provider.complete("please translate this", "model"))
        assert result.content == "translated text"

    def test_configured_response_no_match_uses_default(self):
        provider = MockLLMProvider()
        provider.set_response("translate", "translated text")
        result = self._run(provider.complete("summarize this", "model"))
        assert result.content == "mock response"

    def test_result_has_token_counts(self):
        provider = MockLLMProvider()
        result = self._run(provider.complete("one two three", "model"))
        assert result.input_tokens > 0
        assert result.output_tokens > 0

    def test_result_has_model_id(self):
        provider = MockLLMProvider()
        result = self._run(provider.complete("x", "my-model"))
        assert result.model_id == "my-model"

    def test_kwargs_recorded(self):
        provider = MockLLMProvider()
        self._run(provider.complete("x", "m", temperature=0.5, max_tokens=100))
        assert provider.calls[0]["temperature"] == 0.5
        assert provider.calls[0]["max_tokens"] == 100


class TestEstimateCost:
    def test_known_model_cost(self):
        provider = MockLLMProvider()
        model = "claude-sonnet-4-20250514"
        pricing = TOKEN_PRICING[model]
        cost = provider.estimate_cost(1000, 500, model)
        expected = 1000 * pricing["input"] + 500 * pricing["output"]
        assert cost == pytest.approx(expected)

    def test_unknown_model_uses_fallback(self):
        provider = MockLLMProvider()
        cost = provider.estimate_cost(1000, 500, "unknown-model")
        expected = 1000 * 0.001 + 500 * 0.002
        assert cost == pytest.approx(expected)

    def test_zero_tokens_zero_cost(self):
        provider = MockLLMProvider()
        assert provider.estimate_cost(0, 0, "claude-sonnet-4-20250514") == 0.0

    def test_cost_included_in_completion_result(self):
        provider = MockLLMProvider()
        result = asyncio.run(provider.complete("test", "claude-sonnet-4-20250514"))
        assert result.cost > 0
