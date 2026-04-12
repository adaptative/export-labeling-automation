"""Base agent interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class AgentResult:
    success: bool
    data: Any
    confidence: float = 1.0
    needs_hitl: bool = False
    hitl_reason: Optional[str] = None
    cost: float = 0.0


class BaseAgent(ABC):
    agent_id: str

    @abstractmethod
    async def execute(self, input_data: dict) -> AgentResult:
        ...
