"""Intake Classifier Agent (Agent 6.1)."""
from labelforge.agents.base import BaseAgent, AgentResult
from labelforge.config import settings

CONFIDENCE_HITL_THRESHOLD = 0.70


class IntakeClassifierAgent(BaseAgent):
    agent_id = "agent-6.1-intake-classifier"

    def __init__(self, llm_provider):
        self.llm = llm_provider

    async def execute(self, input_data: dict) -> AgentResult:
        doc_content = input_data.get("document_content", "")
        result = await self.llm.complete(
            f"Classify this document: {doc_content[:500]}",
            model_id=settings.llm_default_model,
        )
        classification = self._parse_classification(result.content)
        confidence = classification.get("confidence", 0.0)
        needs_hitl = confidence < CONFIDENCE_HITL_THRESHOLD
        return AgentResult(
            success=not needs_hitl,
            data=classification,
            confidence=confidence,
            needs_hitl=needs_hitl,
            hitl_reason="Low classification confidence" if needs_hitl else None,
            cost=result.cost,
        )

    def _parse_classification(self, content: str) -> dict:
        return {"doc_class": "PURCHASE_ORDER", "confidence": 0.95}
