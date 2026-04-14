"""Fusion Agent (Agent 6.7) — AI-driven data fusion and validation.

Per v2.0 architecture (section 6.4): Uses LLM reasoning to resolve
mismatches between PO and PI. The agent joins PO+PI by item_no,
runs deterministic cross-validation (UPC Luhn, dimension fit, weight),
then uses LLM for:
  - Material/finish inference from product description
  - Mismatch resolution reasoning (suggest fixes, generate HiTL questions)
  - Cross-validation beyond rules (description-dimension consistency)

Deterministic checks run first; LLM reasoning runs on issues found.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from labelforge.agents.base import BaseAgent, AgentResult
from labelforge.agents.po_parser import validate_upc_luhn

logger = logging.getLogger(__name__)

DIMENSION_TOLERANCE = 0.5  # inches
MAX_WEIGHT_PER_CARTON_KG = 50  # reasonable manual handling limit

# ── LLM Prompts ──────────────────────────────────────────────────────────────

_MATERIAL_PROMPT = """Given this product description, infer the likely material and finish.
Return ONLY a JSON object with two keys: "material" and "finish".
If unknown, use null.

Product: {description}
"""

_MISMATCH_RESOLUTION_PROMPT = """You are a fusion validation agent for an export labeling system.
You have been given a list of issues found while merging Purchase Order (PO) and
Proforma Invoice (PI) data for carton labeling.

For each issue, analyze the context and provide:
1. A suggested resolution (what value should be used, or what action to take)
2. A confidence score (0.0-1.0) for your suggestion
3. A clear, specific question to ask the human operator if HiTL is needed

Issues found:
{issues_json}

Fused item context:
{items_json}

Return a JSON object:
{{
  "resolutions": [
    {{
      "item_no": "string",
      "field": "string",
      "suggested_value": "string or null",
      "resolution_confidence": 0.0-1.0,
      "reasoning": "brief explanation",
      "hitl_question": "specific question for the human operator"
    }}
  ],
  "overall_assessment": "brief summary of fusion quality",
  "recommended_action": "proceed|review|block"
}}

Return ONLY JSON. No markdown fences.
"""

_CROSS_VALIDATION_PROMPT = """You are a cross-validation agent for export labeling.
Review these fused PO+PI items for consistency issues that rule-based checks might miss.

Check for:
1. Description vs dimensions mismatch (e.g., "mug" shouldn't be 24x18x12 inches)
2. Unusual quantity patterns (e.g., total_qty not divisible by case_qty)
3. Description vs weight mismatch (e.g., "ceramic vase" at 0.01 kg is suspicious)
4. Duplicate or near-duplicate items that might be errors
5. Any other anomalies in the data

Items:
{items_json}

Return a JSON object:
{{
  "anomalies": [
    {{
      "item_no": "string",
      "field": "string",
      "observation": "what seems wrong",
      "severity": "warning|info",
      "suggested_action": "brief suggestion"
    }}
  ]
}}

Return ONLY JSON. No markdown fences.
"""


class FusionAgent(BaseAgent):
    """Fusion Agent — AI-driven PO+PI merge with mismatch resolution.

    Per v2.0 architecture: Uses LLM reasoning graph for mismatch resolution.
    Deterministic validation runs first, then LLM provides intelligent
    resolution suggestions and generates contextual HiTL questions.
    """

    agent_id = "agent-6.7-fusion"

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    async def execute(self, input_data: dict) -> AgentResult:
        po_items = {i["item_no"]: i for i in input_data.get("po_items", [])}
        pi_items = {i["item_no"]: i for i in input_data.get("pi_items", [])}
        fused = []
        issues = []
        cost = 0.0

        # ── Step 1: Deterministic join + validation ──────────────────────
        all_item_nos = set(po_items.keys()) | set(pi_items.keys())
        for item_no in sorted(all_item_nos):
            po = po_items.get(item_no)
            pi = pi_items.get(item_no)

            if not po:
                issues.append({
                    "item_no": item_no, "field": "item_no",
                    "severity": "critical", "message": "Missing from PO",
                    "po_value": None, "pi_value": str(item_no),
                })
                continue
            if not pi:
                issues.append({
                    "item_no": item_no, "field": "item_no",
                    "severity": "critical", "message": "Missing from PI",
                    "po_value": str(item_no), "pi_value": None,
                })
                continue

            # UPC Luhn re-validation
            upc = str(po.get("upc", ""))
            if upc and not validate_upc_luhn(upc):
                issues.append({
                    "item_no": item_no, "field": "upc",
                    "severity": "warning",
                    "message": f"UPC '{upc}' fails Luhn check",
                    "po_value": upc, "pi_value": None,
                })

            # Dimension fit check
            if po.get("product_dims") and pi.get("box_L"):
                self._check_dimension_fit(item_no, po["product_dims"], pi, issues)

            # Weight plausibility check
            self._check_weight_plausibility(item_no, po, pi, issues)

            # Merge PO + PI fields
            merged = {**po, **pi, "item_no": item_no}

            # ── Step 2: LLM material inference ───────────────────────────
            if self.llm and po.get("description"):
                material, finish, llm_cost = await self._infer_material(po["description"])
                merged["material"] = material
                merged["finish"] = finish
                cost += llm_cost

            fused.append(merged)

        # ── Step 3: LLM mismatch resolution ──────────────────────────────
        if self.llm and issues:
            resolution_data, res_cost = await self._resolve_mismatches(issues, fused)
            cost += res_cost
            if resolution_data:
                self._apply_resolutions(fused, issues, resolution_data)

        # ── Step 4: LLM cross-validation ─────────────────────────────────
        if self.llm and fused:
            anomalies, cv_cost = await self._cross_validate(fused)
            cost += cv_cost
            if anomalies:
                for anomaly in anomalies:
                    issues.append({
                        "item_no": anomaly.get("item_no", "UNKNOWN"),
                        "field": anomaly.get("field", "cross_validation"),
                        "severity": anomaly.get("severity", "info"),
                        "message": anomaly.get("observation", "Anomaly detected"),
                        "po_value": None, "pi_value": None,
                        "source": "llm_cross_validation",
                        "suggested_action": anomaly.get("suggested_action"),
                    })

        # ── Step 5: Confidence & HiTL decision ──────────────────────────
        has_critical = any(i["severity"] == "critical" for i in issues)
        warning_count = sum(1 for i in issues if i["severity"] == "warning")

        if has_critical:
            confidence = 0.50
        else:
            confidence = max(0.60, 0.95 - 0.05 * warning_count)

        confidence = round(min(1.0, max(0.0, confidence)), 2)

        needs_hitl = has_critical
        hitl_reason = "Critical fusion issues found" if has_critical else None

        logger.info(
            "Fusion: %d items fused, %d issues (%d critical), confidence=%.2f, cost=$%.4f",
            len(fused), len(issues),
            sum(1 for i in issues if i["severity"] == "critical"),
            confidence, cost,
        )

        return AgentResult(
            success=not has_critical,
            data={"fused_items": fused, "issues": issues},
            confidence=confidence,
            needs_hitl=needs_hitl,
            hitl_reason=hitl_reason,
            cost=cost,
        )

    # ── Deterministic checks ─────────────────────────────────────────────────

    def _check_dimension_fit(self, item_no: str, product_dims: dict, pi: dict, issues: list) -> None:
        """Check that product fits inside carton with tolerance."""
        for dim_key, box_key in [("length", "box_L"), ("width", "box_W"), ("height", "box_H")]:
            prod_dim = product_dims.get(dim_key, 0)
            box_dim = pi.get(box_key, 0)
            if prod_dim > 0 and box_dim > 0:
                if prod_dim > box_dim + DIMENSION_TOLERANCE:
                    issues.append({
                        "item_no": item_no, "field": dim_key,
                        "severity": "critical",
                        "message": f"Product {dim_key} ({prod_dim}) exceeds box ({box_dim}) + tolerance ({DIMENSION_TOLERANCE})",
                        "po_value": str(prod_dim),
                        "pi_value": str(box_dim),
                    })

    def _check_weight_plausibility(self, item_no: str, po: dict, pi: dict, issues: list) -> None:
        """Check if weight per carton is plausible for manual handling."""
        net_weight = po.get("net_weight")
        if net_weight is None:
            return

        try:
            weight = float(net_weight)
        except (TypeError, ValueError):
            return

        if weight <= 0:
            issues.append({
                "item_no": item_no, "field": "net_weight",
                "severity": "warning",
                "message": f"Net weight must be positive, got {weight}",
                "po_value": str(weight), "pi_value": None,
            })
            return

        case_qty = po.get("case_qty")
        if case_qty:
            try:
                qty = int(float(str(case_qty)))
                weight_per_carton = weight * qty
                if weight_per_carton > MAX_WEIGHT_PER_CARTON_KG:
                    issues.append({
                        "item_no": item_no, "field": "net_weight",
                        "severity": "warning",
                        "message": f"Estimated carton weight ({weight_per_carton:.1f}kg) exceeds {MAX_WEIGHT_PER_CARTON_KG}kg limit",
                        "po_value": str(weight_per_carton),
                        "pi_value": str(MAX_WEIGHT_PER_CARTON_KG),
                    })
            except (TypeError, ValueError):
                pass

    # ── LLM-powered capabilities ─────────────────────────────────────────────

    async def _infer_material(self, description: str) -> tuple[Optional[str], Optional[str], float]:
        """Use LLM to infer material and finish from description."""
        try:
            prompt = _MATERIAL_PROMPT.format(description=description)
            result = await self.llm.complete(prompt, model_id="default")
            content = result.content.strip()
            data = json.loads(content)
            if not isinstance(data, dict):
                return None, None, getattr(result, "cost_usd", 0.0)
            return (
                data.get("material"),
                data.get("finish"),
                getattr(result, "cost_usd", 0.0),
            )
        except (json.JSONDecodeError, Exception) as exc:
            logger.debug("Material inference failed: %s", exc)
            return None, None, 0.0

    async def _resolve_mismatches(
        self, issues: list[dict], fused_items: list[dict]
    ) -> tuple[Optional[dict], float]:
        """Use LLM to reason about mismatch resolution.

        Per v2.0 architecture: The reasoning graph decides how to resolve
        mismatches between PO and PI. Returns suggested resolutions and
        contextual HiTL questions.
        """
        if not self.llm:
            return None, 0.0

        safe_issues = [{k: v for k, v in i.items()} for i in issues]
        safe_items = [{k: v for k, v in i.items()} for i in fused_items]

        prompt = _MISMATCH_RESOLUTION_PROMPT.format(
            issues_json=json.dumps(safe_issues, default=str),
            items_json=json.dumps(safe_items, default=str),
        )

        try:
            result = await self.llm.complete(prompt, model_id="default")
            content = result.content.strip()
            data = json.loads(content)
            if not isinstance(data, dict):
                return None, getattr(result, "cost_usd", 0.0)
            return data, getattr(result, "cost_usd", 0.0)
        except (json.JSONDecodeError, Exception) as exc:
            logger.debug("Mismatch resolution failed: %s", exc)
            return None, 0.0

    def _apply_resolutions(
        self, fused: list[dict], issues: list[dict], resolution_data: dict
    ) -> None:
        """Apply LLM resolution suggestions to issues and fused items."""
        resolutions = resolution_data.get("resolutions", [])
        items_by_no = {i.get("item_no"): i for i in fused}

        for res in resolutions:
            item_no = res.get("item_no")
            field = res.get("field")

            # Attach resolution metadata to the matching issue
            for issue in issues:
                if issue.get("item_no") == item_no and issue.get("field") == field:
                    issue["suggested_value"] = res.get("suggested_value")
                    issue["resolution_confidence"] = res.get("resolution_confidence")
                    issue["reasoning"] = res.get("reasoning")
                    issue["hitl_question"] = res.get("hitl_question")
                    break

            # Apply high-confidence suggestions to fused items (non-critical only)
            conf = res.get("resolution_confidence", 0)
            suggested = res.get("suggested_value")
            if conf >= 0.9 and suggested and item_no in items_by_no:
                matching = [i for i in issues if i.get("item_no") == item_no
                            and i.get("field") == field]
                if matching and matching[0].get("severity") != "critical":
                    items_by_no[item_no][field] = suggested
                    matching[0]["auto_resolved"] = True

        # Store overall assessment
        assessment = resolution_data.get("overall_assessment")
        if assessment:
            for item in fused:
                item.setdefault("_fusion_metadata", {})["llm_assessment"] = assessment

    async def _cross_validate(self, fused_items: list[dict]) -> tuple[list[dict], float]:
        """Use LLM for intelligent cross-validation beyond rule-based checks.

        Detects anomalies like description-dimension mismatches,
        unusual quantities, and potential duplicate items.
        """
        if not self.llm:
            return [], 0.0

        safe_items = []
        for item in fused_items:
            safe = {k: v for k, v in item.items()
                    if not k.startswith("_") and k != "confidence"}
            safe_items.append(safe)

        prompt = _CROSS_VALIDATION_PROMPT.format(
            items_json=json.dumps(safe_items, default=str),
        )

        try:
            result = await self.llm.complete(prompt, model_id="default")
            content = result.content.strip()
            data = json.loads(content)
            if not isinstance(data, dict):
                return [], getattr(result, "cost_usd", 0.0)
            return data.get("anomalies", []), getattr(result, "cost_usd", 0.0)
        except (json.JSONDecodeError, Exception) as exc:
            logger.debug("Cross-validation failed: %s", exc)
            return [], 0.0
