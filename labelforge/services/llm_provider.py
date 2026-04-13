"""LLM provider service — real OpenAI integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import openai

from labelforge.config import settings


TOKEN_PRICING = {
    "gpt-5.4": {"input": 5.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "gpt-4o": {"input": 5.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
}


@dataclass
class CompletionResult:
    content: str
    input_tokens: int
    output_tokens: int
    cost: float
    model_id: str
    cached: bool = False


class OpenAILLMProvider:
    """Real OpenAI LLM provider."""

    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None) -> None:
        if api_key is not None:
            key = api_key
        else:
            key = settings.openai_api_key
        if not key:
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY env var or pass api_key."
            )
        self._client = openai.AsyncOpenAI(api_key=key)
        self._default_model = default_model or settings.llm_default_model

    async def complete(self, prompt: str, model_id: Optional[str] = None, **kwargs) -> CompletionResult:
        model = model_id or self._default_model
        response = await self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        choice = response.choices[0]
        content = choice.message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = self.estimate_cost(input_tokens, output_tokens, model)
        return CompletionResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            model_id=model,
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int, model_id: Optional[str] = None) -> float:
        model = model_id or self._default_model
        pricing = TOKEN_PRICING.get(model, {"input": 0.001 / 1000, "output": 0.002 / 1000})
        return input_tokens * pricing["input"] + output_tokens * pricing["output"]


def get_llm_provider(api_key: Optional[str] = None) -> OpenAILLMProvider:
    """Factory to create an LLM provider from settings."""
    return OpenAILLMProvider(api_key=api_key)
