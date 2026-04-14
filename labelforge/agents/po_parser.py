"""PO Parser Agent (Agent 6.2) — AI-driven extraction and validation.

Uses LLM for:
  - Adaptive extraction from any PO document format (PDF/XLSX/text)
  - Field validation and enrichment (infer missing fields from description)
  - UPC correction suggestions when Luhn check fails
  - Confidence scoring informed by LLM assessment

Deterministic fallbacks when no LLM is available.
Per v1.0 spec: Model = GPT-4o (vision + long context, high quality).
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

    confidence = 0.6 + (0.3 * required_ratio)

    optional_count = sum(1 for f in OPTIONAL_FIELDS if item.get(f))
    confidence += 0.025 * optional_count

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


# ── LLM Prompts ──────────────────────────────────────────────────────────────

_EXTRACTION_PROMPT = """You are a purchase-order parser for an export labeling system.
Extract every line item from this document regardless of its layout or format.

For each item, return:
- item_no (string) — the SKU or item number
- upc (string, 12 digits) — UPC-A code
- gtin (string or null) — 14-digit GTIN if present
- description (string) — full product description
- product_dims (object with length/width/height/unit, or null)
- net_weight (number in kg, or null)
- case_qty (string) — units per case/carton
- total_qty (integer) — total quantity ordered
- product_image_refs (list of strings, or empty list)

If a field is missing, set it to null and lower the confidence.
Flag ambiguities (e.g., two possible UPCs for one SKU) in a "notes" field.

Return ONLY a JSON array of objects. No markdown fences, no extra text.

Document text:
{document_text}
"""

_VALIDATION_PROMPT = """You are a purchase-order validation agent. Review these extracted PO line items
and validate/enrich them. For each item:

1. Check if the description is consistent with other fields (dims, weight, material hints)
2. If any required fields are missing (item_no, upc, description, case_qty, total_qty),
   try to infer them from context
3. If a UPC fails Luhn check, suggest a corrected UPC if possible (common typo patterns)
4. Infer product material and category from the description
5. Rate your confidence in each item (0.0 to 1.0)

Input items:
{items_json}

Return a JSON object with:
{{
  "validated_items": [
    {{
      "item_no": "...",
      "enrichments": {{
        "inferred_material": "string or null",
        "inferred_category": "string or null",
        "suggested_upc": "string or null",
        "description_quality": "good|fair|poor"
      }},
      "confidence": 0.0-1.0,
      "notes": ["any observations"]
    }}
  ],
  "cross_item_issues": ["any issues spanning multiple items"]
}}

Return ONLY JSON. No markdown fences.
"""


class POParserAgent(BaseAgent):
    """PO Parser Agent — AI-driven extraction and validation of Purchase Orders.

    Per v1.0 spec (section 6.2): Uses vision LLM + structured output for
    adaptive extraction from any PO layout. Deterministic validation as
    post-processing. LLM enrichment for field inference and UPC correction.
    """

    agent_id = "agent-6.2-po-parser"

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    async def execute(self, input_data: dict) -> AgentResult:
        """Parse PO data with AI extraction and validation.

        Input modes:
            1. Structured: input_data["items"] — pre-parsed dicts (validated + enriched by LLM)
            2. Raw text:   input_data["document_content"] — full LLM extraction
            3. Multi-page: input_data["pages"] — concatenated LLM extraction
        """
        cost = 0.0
        page_count = 1

        # ── Step 1: Extract items ────────────────────────────────────────
        if "items" in input_data:
            items = input_data["items"]
        elif "pages" in input_data:
            pages = input_data["pages"]
            page_count = len(pages)
            document_text = "\n\n--- PAGE BREAK ---\n\n".join(pages)
            items, extract_cost = await self._extract_from_text(document_text)
            cost += extract_cost
        elif "document_content" in input_data:
            items, extract_cost = await self._extract_from_text(input_data["document_content"])
            cost += extract_cost
        else:
            items = []

        # ── Step 2: Deterministic validation ─────────────────────────────
        parsed_items = []
        issues: list[dict] = []

        for item in items:
            item_no = item.get("item_no", "UNKNOWN")

            missing = [f for f in REQUIRED_FIELDS if not item.get(f)]
            if missing:
                issues.append({
                    "item_no": item_no,
                    "issue": f"Missing required fields: {', '.join(sorted(missing))}",
                })

            upc = str(item.get("upc", ""))
            if upc and not validate_upc_luhn(upc):
                issues.append({
                    "item_no": item_no,
                    "issue": "UPC Luhn check failed",
                })

            _validate_dimensions(item, item_no, issues)
            _validate_weight(item, item_no, issues)

            item["confidence"] = _compute_item_confidence(item)
            parsed_items.append(item)

        # ── Step 3: LLM validation & enrichment ─────────────────────────
        if self.llm and parsed_items:
            enrichment_result, enrich_cost = await self._validate_and_enrich(parsed_items)
            cost += enrich_cost

            if enrichment_result:
                self._apply_enrichments(parsed_items, enrichment_result, issues)

        # ── Step 4: Compute overall confidence ───────────────────────────
        if parsed_items:
            avg_confidence = sum(i.get("confidence", 0.5) for i in parsed_items) / len(parsed_items)
        else:
            avg_confidence = 0.0

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
            "PO parsed: %d items, %d issues, confidence=%.2f, hitl=%s, cost=$%.4f",
            len(parsed_items), len(issues), avg_confidence, needs_hitl, cost,
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
        """Use LLM to extract items from raw PO text (any format)."""
        if not self.llm:
            return [], 0.0

        prompt = _EXTRACTION_PROMPT.format(document_text=document_text)

        try:
            result = await self.llm.complete(prompt, model_id="default")
            content = result.content.strip()
            items = json.loads(content)
            if not isinstance(items, list):
                items = [items] if isinstance(items, dict) else []
            return items, getattr(result, "cost_usd", 0.0)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("LLM extraction failed: %s", exc)
            return [], 0.0

    async def _validate_and_enrich(self, items: list[dict]) -> tuple[Optional[dict], float]:
        """Use LLM to validate items and enrich with inferred fields.

        Returns enrichment data with:
          - inferred_material / inferred_category per item
          - suggested_upc corrections
          - description quality assessment
          - cross-item issues
        """
        if not self.llm:
            return None, 0.0

        safe_items = []
        for item in items:
            safe = {k: v for k, v in item.items() if k != "confidence"}
            safe_items.append(safe)

        prompt = _VALIDATION_PROMPT.format(items_json=json.dumps(safe_items, default=str))

        try:
            result = await self.llm.complete(prompt, model_id="default")
            content = result.content.strip()
            data = json.loads(content)
            if not isinstance(data, dict):
                logger.debug("LLM enrichment returned non-dict, skipping")
                return None, getattr(result, "cost_usd", 0.0)
            return data, getattr(result, "cost_usd", 0.0)
        except (json.JSONDecodeError, Exception) as exc:
            logger.debug("LLM validation/enrichment failed: %s", exc)
            return None, 0.0

    def _apply_enrichments(
        self, items: list[dict], enrichment: dict, issues: list[dict]
    ) -> None:
        """Apply LLM enrichment results to parsed items."""
        validated = enrichment.get("validated_items", [])
        items_by_no = {i.get("item_no"): i for i in items}

        for v in validated:
            item_no = v.get("item_no")
            item = items_by_no.get(item_no)
            if not item:
                continue

            enrichments = v.get("enrichments", {})

            # Apply inferred material
            if enrichments.get("inferred_material") and not item.get("material"):
                item["material"] = enrichments["inferred_material"]

            # Apply inferred category
            if enrichments.get("inferred_category") and not item.get("category"):
                item["category"] = enrichments["inferred_category"]

            # Record UPC suggestion (don't auto-correct — surface for HiTL)
            suggested_upc = enrichments.get("suggested_upc")
            if suggested_upc and suggested_upc != item.get("upc"):
                item["suggested_upc"] = suggested_upc
                issues.append({
                    "item_no": item_no,
                    "issue": f"LLM suggests corrected UPC: {suggested_upc}",
                    "severity": "info",
                })

            # Boost or reduce confidence based on LLM assessment
            llm_confidence = v.get("confidence")
            if llm_confidence is not None:
                current = item.get("confidence", 0.5)
                # Blend: 60% deterministic + 40% LLM assessment
                item["confidence"] = round(
                    min(1.0, current * 0.6 + float(llm_confidence) * 0.4), 2
                )

            # Store LLM notes on the item
            notes = v.get("notes", [])
            if notes:
                item["llm_notes"] = notes

        # Cross-item issues from LLM
        for cross_issue in enrichment.get("cross_item_issues", []):
            issues.append({
                "item_no": "ALL",
                "issue": cross_issue,
                "severity": "warning",
                "source": "llm",
            })
