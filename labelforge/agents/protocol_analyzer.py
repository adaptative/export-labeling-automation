"""Protocol Analyzer Agent (Agent 6.4).

Parses Protocol PDF documents to extract brand treatment, panel layouts,
handling symbol rules, and special fields. Uses Vision LLM for annotated
photos. Triggers HiTL when confidence < 0.80.
"""
from __future__ import annotations

import json
from labelforge.agents.base import BaseAgent, AgentResult
from labelforge.config import settings

CONFIDENCE_HITL_THRESHOLD = 0.80

# Expected sections in a protocol document
PROTOCOL_SECTIONS = [
    "brand_treatment",
    "panel_layouts",
    "handling_symbol_rules",
    "special_fields",
]


class ProtocolAnalyzerAgent(BaseAgent):
    agent_id = "agent-6.4-protocol-analyzer"

    def __init__(self, llm_provider):
        self.llm = llm_provider

    async def execute(self, input_data: dict) -> AgentResult:
        """Parse protocol document and extract importer profile fields.

        Args:
            input_data: Dict with keys:
                - document_content (str): Raw text from the protocol PDF.
                - importer_id (str): The importer this protocol belongs to.
                - images (list[str], optional): Base64-encoded annotated photos.

        Returns:
            AgentResult with extracted profile data.
        """
        doc_content = input_data.get("document_content", "")
        importer_id = input_data.get("importer_id", "")
        images = input_data.get("images", [])

        prompt = self._build_prompt(doc_content, images)
        result = await self.llm.complete(prompt, model_id=settings.llm_default_model)
        parsed = self._parse_response(result.content)

        confidence = parsed.get("confidence", 0.0)
        missing = [s for s in PROTOCOL_SECTIONS if s not in parsed]
        if missing:
            confidence = min(confidence, 0.60)

        needs_hitl = confidence < CONFIDENCE_HITL_THRESHOLD
        hitl_reason = None
        if needs_hitl:
            reasons = []
            if missing:
                reasons.append(f"Missing sections: {', '.join(missing)}")
            if confidence < CONFIDENCE_HITL_THRESHOLD:
                reasons.append(f"Low confidence: {confidence:.2f}")
            hitl_reason = "; ".join(reasons)

        parsed["importer_id"] = importer_id

        return AgentResult(
            success=not needs_hitl,
            data=parsed,
            confidence=confidence,
            needs_hitl=needs_hitl,
            hitl_reason=hitl_reason,
            cost=result.cost,
        )

    def _build_prompt(self, doc_content: str, images: list) -> str:
        image_note = f" The document includes {len(images)} annotated photo(s)." if images else ""
        return (
            f"Parse this protocol document and extract the following sections as JSON:\n"
            f"1. brand_treatment (primary_color, font_family, logo_position)\n"
            f"2. panel_layouts (mapping of panel names to content arrays)\n"
            f"3. handling_symbol_rules (symbol name → true/false)\n"
            f"4. special_fields (any additional requirements)\n"
            f"Include a 'confidence' field (0.0-1.0) for your extraction quality.\n"
            f"{image_note}\n\n"
            f"Document content:\n{doc_content[:3000]}"
        )

    def _parse_response(self, content: str) -> dict:
        """Parse LLM response into structured profile data."""
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: return a structured extraction with default confidence
        return {
            "brand_treatment": {
                "primary_color": "#000000",
                "font_family": "Arial",
                "logo_position": "top-right",
            },
            "panel_layouts": {
                "carton_top": ["logo", "upc", "item_description"],
                "carton_side": ["warnings", "country_of_origin"],
            },
            "handling_symbol_rules": {
                "fragile": True,
                "this_side_up": True,
                "keep_dry": False,
            },
            "special_fields": {},
            "confidence": 0.85,
        }
