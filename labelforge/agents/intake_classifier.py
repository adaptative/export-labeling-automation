"""Intake Classifier Agent (Agent 6.1).

Classifies uploaded documents into one of the known DocumentClass types
using a Vision LLM. Returns confidence 0-1; scores below the HiTL threshold
trigger human review.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from labelforge.agents.base import BaseAgent, AgentResult
from labelforge.config import settings
from labelforge.contracts.models import DocumentClass

logger = logging.getLogger(__name__)

CONFIDENCE_HITL_THRESHOLD = 0.70

VALID_CLASSES = {dc.value for dc in DocumentClass if dc != DocumentClass.UNKNOWN}

CLASSIFICATION_SYSTEM_PROMPT = """You are a document classification agent for an export labeling automation system.

Classify the given document into exactly ONE of these types:
- PURCHASE_ORDER: A purchase order from a buyer/importer listing items, quantities, UPCs
- PROFORMA_INVOICE: A proforma invoice with shipping dimensions, weights, carton counts
- PROTOCOL: A labeling protocol specifying label requirements, placement rules
- WARNING_LABELS: Warning label guidelines (Prop 65, choking hazard, care instructions)
- CHECKLIST: A QA or compliance checklist

Respond with ONLY valid JSON in this exact format:
{"doc_class": "<TYPE>", "confidence": <0.0-1.0>, "reasoning": "<brief explanation>"}

Rules:
- confidence should reflect how certain you are (0.0 = no idea, 1.0 = absolutely certain)
- If the document doesn't clearly match any type, use the closest match with low confidence
- Consider filename, content structure, and keywords when classifying"""


class IntakeClassifierAgent(BaseAgent):
    agent_id = "agent-6.1-intake-classifier"

    def __init__(self, llm_provider) -> None:
        self.llm = llm_provider

    async def execute(self, input_data: dict) -> AgentResult:
        doc_content = input_data.get("document_content", "")
        filename = input_data.get("filename", "")

        user_prompt = f"Filename: {filename}\n\nDocument content (first 2000 chars):\n{doc_content[:2000]}"

        messages = [
            {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        result = await self.llm.complete(
            model=settings.llm_default_model,
            messages=messages,
            temperature=0.0,
            max_tokens=256,
        )

        classification = self._parse_classification(result.content, filename)
        confidence = classification.get("confidence", 0.0)
        needs_hitl = confidence < CONFIDENCE_HITL_THRESHOLD

        logger.info(
            "IntakeClassifier: file=%s class=%s confidence=%.2f needs_hitl=%s cost=$%.6f",
            filename,
            classification.get("doc_class", "UNKNOWN"),
            confidence,
            needs_hitl,
            result.cost_usd,
        )

        return AgentResult(
            success=not needs_hitl,
            data=classification,
            confidence=confidence,
            needs_hitl=needs_hitl,
            hitl_reason="Low classification confidence" if needs_hitl else None,
            cost=result.cost_usd,
        )

    def _parse_classification(self, content: str, filename: str = "") -> dict:
        """Parse LLM JSON response into a classification dict.

        Falls back to filename-based heuristic if LLM output is unparseable.
        """
        # Try to extract JSON from the response
        try:
            parsed = json.loads(content.strip())
            doc_class = parsed.get("doc_class", "UNKNOWN")
            confidence = float(parsed.get("confidence", 0.0))
            reasoning = parsed.get("reasoning", "")

            # Validate doc_class
            if doc_class not in VALID_CLASSES:
                doc_class = "UNKNOWN"
                confidence = min(confidence, 0.3)

            # Clamp confidence
            confidence = max(0.0, min(1.0, confidence))

            return {
                "doc_class": doc_class,
                "confidence": confidence,
                "reasoning": reasoning,
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning("Failed to parse LLM classification response, falling back to filename heuristic")

        return self._classify_by_filename(filename)

    @staticmethod
    def _classify_by_filename(filename: str) -> dict:
        """Fallback: classify based on filename patterns."""
        lower = filename.lower()
        if "po" in lower or "purchase" in lower:
            return {"doc_class": "PURCHASE_ORDER", "confidence": 0.60, "reasoning": "Filename contains PO keyword"}
        if "pi" in lower or "proforma" in lower or "invoice" in lower:
            return {"doc_class": "PROFORMA_INVOICE", "confidence": 0.60, "reasoning": "Filename contains PI keyword"}
        if "protocol" in lower:
            return {"doc_class": "PROTOCOL", "confidence": 0.60, "reasoning": "Filename contains protocol keyword"}
        if "warning" in lower or "label" in lower:
            return {"doc_class": "WARNING_LABELS", "confidence": 0.55, "reasoning": "Filename contains warning keyword"}
        if "checklist" in lower or "check" in lower:
            return {"doc_class": "CHECKLIST", "confidence": 0.55, "reasoning": "Filename contains checklist keyword"}
        return {"doc_class": "UNKNOWN", "confidence": 0.0, "reasoning": "Could not classify document"}
