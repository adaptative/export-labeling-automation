"""PO Parser Agent (Agent 6.2) — rewritten with correct schema.

Supports structured and raw-text input modes. Multi-page extraction.
UPC Luhn validation. Dimension/weight extraction. Per-item confidence.
HiTL on Luhn failures or missing critical fields.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from labelforge.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"item_no", "upc", "description", "case_qty", "total_qty"}
OPTIONAL_FIELDS = {"gtin", "product_dims", "net_weight", "product_image_refs"}


def validate_upc_luhn(upc: str) -> bool:
    """Validate a 12-digit UPC-A using the Luhn-like check digit algorithm."""
    if len(upc) != 12 or not upc.isdigit():
        return False
    digits = [int(d) for d in upc]
    odd_sum = sum(digits[i] for i in range(0, 11, 2))
    even_sum = sum(digits[i] for i in range(1, 11, 2))
    check = (10 - (odd_sum * 3 + even_sum) % 10) % 10
    return check == digits[11]


def _compute_item_confidence(item: dict) -> float:
    """Compute per-item confidence based on field completeness."""
    present_required = sum(1 for f in REQUIRED_FIELDS if item.get(f))
    required_ratio = present_required / len(REQUIRED_FIELDS) if REQUIRED_FIELDS else 1.0

    # Base confidence from required fields
    confidence = 0.6 + (0.3 * required_ratio)  # 0.6 to 0.9

    # Bonus for optional fields
    optional_count = sum(1 for f in OPTIONAL_FIELDS if item.get(f))
    confidence += 0.025 * optional_count  # up to +0.10

    return min(1.0, round(confidence, 2))


def _validate_dimensions(item: dict, item_no: str, issues: list[dict]) -> None:
    """Validate product dimensions if present."""
    dims = item.get("product_dims")
    if not dims or not isinstance(dims, dict):
        return
    for key in ("length", "width", "height"):
        val = dims.get(key)
        if val is not None:
            try:
                float(val)
            except (TypeError, ValueError):
                issues.append({
                    "item_no": item_no,
                    "issue": f"Invalid dimension '{key}': {val}",
                })


def _validate_weight(item: dict, item_no: str, issues: list[dict]) -> None:
    """Validate net_weight if present."""
    weight = item.get("net_weight")
    if weight is None:
        return
    try:
        w = float(weight)
        if w <= 0:
            issues.append({
                "item_no": item_no,
                "issue": f"Net weight must be positive, got {w}",
            })
    except (TypeError, ValueError):
        issues.append({
            "item_no": item_no,
            "issue": f"Invalid net_weight: {weight}",
        })


_EXTRACTION_PROMPT = """Extract all line items from this Purchase Order document.
Return a JSON array of objects, each with these fields:
- item_no (string)
- upc (string, 12 digits)
- gtin (string or null)
- description (string)
- product_dims (object with length/width/height/unit, or null)
- net_weight (number or null)
- case_qty (string)
- total_qty (integer)
- product_image_refs (list of strings, or empty list)

Return ONLY the JSON array, no markdown fences.

Document text:
{document_text}
"""


class POParserAgent(BaseAgent):
    """PO Parser Agent — extracts and validates Purchase Order line items."""

    agent_id = "agent-6.2-po-parser"

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    async def execute(self, input_data: dict) -> AgentResult:
        """Parse PO data from structured items or raw text.

        Input modes:
            1. Structured: input_data["items"] — list of pre-parsed dicts
            2. Raw text:   input_data["document_content"] — raw PO text
            3. Multi-page: input_data["pages"] — list of page texts
        """
        cost = 0.0
        page_count = 1

        # Determine input mode
        if "items" in input_data:
            items = input_data["items"]
        elif "pages" in input_data:
            pages = input_data["pages"]
            page_count = len(pages)
            document_text = "\n\n--- PAGE BREAK ---\n\n".join(pages)
            items, cost = await self._extract_from_text(document_text)
        elif "document_content" in input_data:
            items, cost = await self._extract_from_text(input_data["document_content"])
        else:
            items = []

        # Validate all items
        parsed_items = []
        issues: list[dict] = []

        for item in items:
            item_no = item.get("item_no", "UNKNOWN")

            # Check required fields
            missing = [f for f in REQUIRED_FIELDS if not item.get(f)]
            if missing:
                issues.append({
                    "item_no": item_no,
                    "issue": f"Missing required fields: {', '.join(sorted(missing))}",
                })

            # UPC Luhn validation
            upc = str(item.get("upc", ""))
            if upc and not validate_upc_luhn(upc):
                issues.append({
                    "item_no": item_no,
                    "issue": "UPC Luhn check failed",
                })

            # Validate dimensions and weight
            _validate_dimensions(item, item_no, issues)
            _validate_weight(item, item_no, issues)

            # Compute per-item confidence
            item["confidence"] = _compute_item_confidence(item)
            parsed_items.append(item)

        # Compute overall confidence
        if parsed_items:
            avg_confidence = sum(i.get("confidence", 0.5) for i in parsed_items) / len(parsed_items)
        else:
            avg_confidence = 0.0

        # Degrade confidence based on issues
        upc_failures = sum(1 for i in issues if "UPC Luhn" in i.get("issue", ""))
        missing_field_issues = sum(1 for i in issues if "Missing required" in i.get("issue", ""))

        if upc_failures > 0:
            avg_confidence = min(avg_confidence, 0.60)
        if missing_field_issues > 0:
            avg_confidence = min(avg_confidence, 0.70)

        avg_confidence = max(0.0, min(1.0, round(avg_confidence, 2)))

        needs_hitl = upc_failures > 0 or missing_field_issues > 0
        hitl_reasons = []
        if upc_failures:
            hitl_reasons.append(f"{upc_failures} UPC validation failures")
        if missing_field_issues:
            hitl_reasons.append(f"{missing_field_issues} items with missing fields")

        logger.info(
            "PO parsed: %d items, %d issues, confidence=%.2f, hitl=%s",
            len(parsed_items), len(issues), avg_confidence, needs_hitl,
        )

        return AgentResult(
            success=not needs_hitl,
            data={
                "items": parsed_items,
                "issues": issues,
                "page_count": page_count,
            },
            confidence=avg_confidence,
            needs_hitl=needs_hitl,
            hitl_reason="; ".join(hitl_reasons) if hitl_reasons else None,
            cost=cost,
        )

    async def _extract_from_text(self, document_text: str) -> tuple[list[dict], float]:
        """Use LLM to extract items from raw PO text."""
        if not self.llm:
            return [], 0.0

        prompt = _EXTRACTION_PROMPT.format(document_text=document_text)

        try:
            result = await self.llm.complete(prompt, model_id="default")
            content = result.content.strip()
            # Try to parse JSON
            items = json.loads(content)
            if not isinstance(items, list):
                items = [items] if isinstance(items, dict) else []
            return items, getattr(result, "cost_usd", 0.0)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("LLM extraction failed: %s", exc)
            return [], 0.0
