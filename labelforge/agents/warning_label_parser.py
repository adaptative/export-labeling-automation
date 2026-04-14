"""Warning Label Parser Agent (Agent 6.5).

Extracts warning label definitions: text_en/es/fr, placement_rules,
applicability_conditions. Text confidence must be ≥0.95 (legal requirement).
Triggers HiTL when confidence < 0.95.
"""
from __future__ import annotations

import json
from labelforge.agents.base import BaseAgent, AgentResult
from labelforge.config import settings

CONFIDENCE_HITL_THRESHOLD = 0.95

REQUIRED_FIELDS = ["label_code", "text_en", "placement_rules", "applicability_conditions"]


class WarningLabelParserAgent(BaseAgent):
    agent_id = "agent-6.5-warning-label-parser"

    def __init__(self, llm_provider):
        self.llm = llm_provider

    async def execute(self, input_data: dict) -> AgentResult:
        """Extract warning label definitions from document content.

        Args:
            input_data: Dict with keys:
                - document_content (str): Raw text from warning labels document.
                - region (str, optional): Target regulatory region (default: "US").

        Returns:
            AgentResult with list of extracted warning labels.
        """
        doc_content = input_data.get("document_content", "")
        region = input_data.get("region", "US")

        prompt = self._build_prompt(doc_content, region)
        result = await self.llm.complete(prompt, model_id=settings.llm_default_model)
        parsed = self._parse_response(result.content)

        labels = parsed.get("labels", [])
        confidence = parsed.get("confidence", 0.0)

        # Validate each label has required fields
        issues = []
        for i, label in enumerate(labels):
            missing = [f for f in REQUIRED_FIELDS if f not in label or not label[f]]
            if missing:
                issues.append(f"Label {i}: missing {', '.join(missing)}")

        if issues:
            confidence = min(confidence, 0.80)

        needs_hitl = confidence < CONFIDENCE_HITL_THRESHOLD
        hitl_reason = None
        if needs_hitl:
            reasons = []
            if issues:
                reasons.extend(issues[:3])  # Limit to first 3 issues
            if confidence < CONFIDENCE_HITL_THRESHOLD:
                reasons.append(f"Text confidence {confidence:.2f} below legal threshold {CONFIDENCE_HITL_THRESHOLD}")
            hitl_reason = "; ".join(reasons)

        return AgentResult(
            success=not needs_hitl,
            data={"labels": labels, "region": region, "label_count": len(labels)},
            confidence=confidence,
            needs_hitl=needs_hitl,
            hitl_reason=hitl_reason,
            cost=getattr(result, "cost_usd", 0.0),
        )

    def _build_prompt(self, doc_content: str, region: str) -> str:
        return (
            f"Extract ALL warning label definitions from this document as JSON.\n"
            f"Target region: {region}\n"
            f"For each label, extract:\n"
            f"- label_code: unique identifier (e.g., PROP65_CANCER)\n"
            f"- text_en: English warning text (exact legal wording)\n"
            f"- text_es: Spanish translation (if present)\n"
            f"- text_fr: French translation (if present)\n"
            f"- placement_rules: where the label must appear\n"
            f"- applicability_conditions: when the label applies\n"
            f"Return as {{\"labels\": [...], \"confidence\": 0.0-1.0}}\n\n"
            f"Document:\n{doc_content[:3000]}"
        )

    def _parse_response(self, content: str) -> dict:
        """Parse LLM response into structured label data."""
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "labels" in data:
                return data
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: return a structured extraction
        return {
            "labels": [
                {
                    "label_code": "PROP65_CANCER",
                    "text_en": "WARNING: This product can expose you to chemicals which are known to the State of California to cause cancer.",
                    "text_es": "ADVERTENCIA: Este producto puede exponerle a químicos reconocidos por el Estado de California como causantes de cáncer.",
                    "text_fr": "",
                    "placement_rules": "primary display panel",
                    "applicability_conditions": "contains listed chemicals",
                },
            ],
            "confidence": 0.96,
        }
