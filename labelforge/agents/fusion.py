"""Fusion Agent (Agent 6.7) — rewritten with correct validation.

Joins PO+PI by item_no. Cross-validation: UPC Luhn, dimension fit
(product in carton + 0.5" tolerance), weight plausibility, material
inference via LLM. Missing item detection. HiTL on critical mismatch.
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

_MATERIAL_PROMPT = """Given this product description, infer the likely material and finish.
Return ONLY a JSON object with two keys: "material" and "finish".
If unknown, use null.

Product: {description}
"""


class FusionAgent(BaseAgent):
    """Fusion Agent — merges PO + PI items with cross-validation."""

    agent_id = "agent-6.7-fusion"

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    async def execute(self, input_data: dict) -> AgentResult:
        po_items = {i["item_no"]: i for i in input_data.get("po_items", [])}
        pi_items = {i["item_no"]: i for i in input_data.get("pi_items", [])}
        fused = []
        issues = []
        cost = 0.0

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

            # Material inference via LLM
            if self.llm and po.get("description"):
                material, finish, llm_cost = await self._infer_material(po["description"])
                merged["material"] = material
                merged["finish"] = finish
                cost += llm_cost

            fused.append(merged)

        # Confidence calculation
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
            "Fusion: %d items fused, %d issues (%d critical), confidence=%.2f",
            len(fused), len(issues),
            sum(1 for i in issues if i["severity"] == "critical"),
            confidence,
        )

        return AgentResult(
            success=not has_critical,
            data={"fused_items": fused, "issues": issues},
            confidence=confidence,
            needs_hitl=needs_hitl,
            hitl_reason=hitl_reason,
            cost=cost,
        )

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

        # Estimate weight per carton
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

    async def _infer_material(self, description: str) -> tuple[Optional[str], Optional[str], float]:
        """Use LLM to infer material and finish from description."""
        try:
            prompt = _MATERIAL_PROMPT.format(description=description)
            result = await self.llm.complete(prompt, model_id="default")
            content = result.content.strip()
            data = json.loads(content)
            return (
                data.get("material"),
                data.get("finish"),
                getattr(result, "cost_usd", 0.0),
            )
        except (json.JSONDecodeError, Exception) as exc:
            logger.debug("Material inference failed: %s", exc)
            return None, None, 0.0
