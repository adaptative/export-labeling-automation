"""PI Parser Agent (Agent 6.3) — deterministic, no LLM.

Reads tabular PI data using ImporterProfile.pi_template_mapping.
Type coercion, CBM auto-computation, per-item confidence.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from labelforge.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"item_no", "box_L", "box_W", "box_H", "total_cartons"}
FLOAT_FIELDS = {"box_L", "box_W", "box_H", "cbm"}
INT_FIELDS = {"total_cartons", "inner_pack"}
STRING_FIELDS = {"item_no", "hs_code"}


def _coerce(value: Any, target_type: str) -> Any:
    """Coerce a value to the target type, returning None on failure."""
    if value is None:
        return None
    try:
        if target_type == "float":
            return float(value)
        elif target_type == "int":
            return int(float(value))  # "50.0" -> 50
        else:
            return str(value)
    except (TypeError, ValueError):
        return None


class PIParserAgent(BaseAgent):
    """PI Parser Agent — deterministic extraction, NO LLM used."""

    agent_id = "agent-6.3-pi-parser"

    async def execute(self, input_data: dict) -> AgentResult:
        """Parse proforma invoice rows using template mapping.

        Input:
            rows: list of dicts (each row from the spreadsheet)
            template_mapping: dict mapping target fields to source column names
        """
        rows = input_data.get("rows", [])
        template_mapping = input_data.get("template_mapping", {})
        parsed: list[dict] = []
        warnings: list[dict] = []

        for idx, row in enumerate(rows):
            item: dict[str, Any] = {}

            # Apply template mapping with type coercion
            for target_field, source_col in template_mapping.items():
                raw_value = row.get(source_col)

                if target_field in FLOAT_FIELDS:
                    item[target_field] = _coerce(raw_value, "float")
                elif target_field in INT_FIELDS:
                    item[target_field] = _coerce(raw_value, "int")
                else:
                    item[target_field] = _coerce(raw_value, "str")

            # Check for missing item_no
            if not item.get("item_no"):
                warnings.append({
                    "row": idx,
                    "field": "item_no",
                    "message": f"Row {idx}: missing item_no",
                })

            # Auto-compute CBM if not provided but all box dims exist
            if item.get("box_L") and item.get("box_W") and item.get("box_H"):
                if not item.get("cbm") and "cbm" not in template_mapping:
                    item["cbm"] = round(
                        item["box_L"] * item["box_W"] * item["box_H"] / 1_000_000, 6
                    )

            # Track missing required fields
            missing = [f for f in REQUIRED_FIELDS if not item.get(f)]
            if missing:
                warnings.append({
                    "row": idx,
                    "item_no": item.get("item_no", f"row-{idx}"),
                    "field": "required",
                    "message": f"Missing required fields: {', '.join(sorted(missing))}",
                })

            parsed.append(item)

        # Compute per-item confidence
        mapped_fields = set(template_mapping.keys())
        confidences = []
        for item in parsed:
            missing_req = sum(1 for f in REQUIRED_FIELDS if f in mapped_fields and not item.get(f))
            unmapped_req = sum(1 for f in REQUIRED_FIELDS if f not in mapped_fields)
            total_missing_req = missing_req + unmapped_req
            if total_missing_req > 0:
                conf = max(0.5, 1.0 - 0.1 * total_missing_req)
            else:
                # Only penalize optional fields that were in the mapping but returned null
                optional_missing = sum(
                    1 for f in ("inner_pack", "hs_code")
                    if f in mapped_fields and not item.get(f)
                )
                conf = max(0.8, 1.0 - 0.05 * optional_missing)
            confidences.append(conf)

        overall_confidence = (
            round(sum(confidences) / len(confidences), 2) if confidences else 1.0
        )

        logger.info(
            "PI parsed: %d items, %d warnings, confidence=%.2f",
            len(parsed), len(warnings), overall_confidence,
        )

        return AgentResult(
            success=True,
            data={
                "items": parsed,
                "warnings": warnings,
                "row_count": len(rows),
            },
            confidence=overall_confidence,
        )
