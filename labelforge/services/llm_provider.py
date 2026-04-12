"""AI provider interface with cost estimation and caching."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompletionResult:
    content: str
    input_tokens: int
    output_tokens: int
    cost: float
    model_id: str
    cached: bool = False


TOKEN_PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-haiku-4-5-20251001": {"input": 0.80 / 1_000_000, "output": 4.0 / 1_000_000},
}


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, model_id: str, **kwargs) -> CompletionResult:
        ...

    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int, model_id: str) -> float:
        ...


class MockLLMProvider(LLMProvider):
    """Test double for LLM provider."""
    def __init__(self):
        self.calls: list[dict] = []
        self._responses: dict[str, str] = {}

    def set_response(self, prompt_contains: str, response: str):
        self._responses[prompt_contains] = response

    async def complete(self, prompt: str, model_id: str, **kwargs) -> CompletionResult:
        self.calls.append({"prompt": prompt, "model_id": model_id, **kwargs})
        content = "mock response"
        for key, resp in self._responses.items():
            if key in prompt:
                content = resp
                break
        return CompletionResult(
            content=content,
            input_tokens=len(prompt.split()) * 2,
            output_tokens=len(content.split()) * 2,
            cost=self.estimate_cost(100, 50, model_id),
            model_id=model_id,
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int, model_id: str) -> float:
        pricing = TOKEN_PRICING.get(model_id, {"input": 0.001, "output": 0.002})
        return input_tokens * pricing["input"] + output_tokens * pricing["output"]
