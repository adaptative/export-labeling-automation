"""Tests for OpenAI LLM provider service and cost estimation."""
from __future__ import annotations

import pytest

from labelforge.services.llm_provider import (
    CompletionResult,
    OpenAILLMProvider,
    TOKEN_PRICING,
    get_llm_provider,
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
    def test_gpt54_model_present(self):
        assert "gpt-5.4" in TOKEN_PRICING

    def test_gpt4o_model_present(self):
        assert "gpt-4o" in TOKEN_PRICING

    def test_gpt4o_mini_present(self):
        assert "gpt-4o-mini" in TOKEN_PRICING

    def test_pricing_keys(self):
        for model, pricing in TOKEN_PRICING.items():
            assert "input" in pricing
            assert "output" in pricing
            assert pricing["input"] > 0
            assert pricing["output"] > 0


class TestOpenAILLMProvider:
    def test_requires_api_key(self):
        with pytest.raises(ValueError, match="API key is required"):
            OpenAILLMProvider(api_key="")

    def test_creates_with_api_key(self):
        provider = OpenAILLMProvider(api_key="sk-test-key")
        assert provider is not None

    def test_estimate_cost_known_model(self):
        provider = OpenAILLMProvider(api_key="sk-test-key")
        pricing = TOKEN_PRICING["gpt-5.4"]
        cost = provider.estimate_cost(1000, 500, "gpt-5.4")
        expected = 1000 * pricing["input"] + 500 * pricing["output"]
        assert cost == pytest.approx(expected)

    def test_estimate_cost_unknown_model_fallback(self):
        provider = OpenAILLMProvider(api_key="sk-test-key")
        cost = provider.estimate_cost(1000, 500, "unknown-model")
        assert cost > 0

    def test_estimate_cost_zero_tokens(self):
        provider = OpenAILLMProvider(api_key="sk-test-key")
        assert provider.estimate_cost(0, 0, "gpt-5.4") == 0.0

    def test_estimate_cost_default_model(self):
        provider = OpenAILLMProvider(api_key="sk-test-key", default_model="gpt-5.4")
        cost = provider.estimate_cost(1000, 500)
        assert cost > 0


class TestGetLLMProvider:
    def test_factory_creates_provider(self):
        provider = get_llm_provider(api_key="sk-test-key")
        assert isinstance(provider, OpenAILLMProvider)

    def test_factory_requires_key(self):
        # When no key in env and none passed, should fail
        import os
        orig = os.environ.get("OPENAI_API_KEY")
        os.environ.pop("OPENAI_API_KEY", None)
        try:
            with pytest.raises(ValueError):
                get_llm_provider(api_key="")
        finally:
            if orig:
                os.environ["OPENAI_API_KEY"] = orig
