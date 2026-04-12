"""Fusion Agent (Agent 6.7)."""
from labelforge.agents.base import BaseAgent, AgentResult

DIMENSION_TOLERANCE = 0.5  # inches


class FusionAgent(BaseAgent):
    agent_id = "agent-6.7-fusion"

    async def execute(self, input_data: dict) -> AgentResult:
        po_items = {i["item_no"]: i for i in input_data.get("po_items", [])}
        pi_items = {i["item_no"]: i for i in input_data.get("pi_items", [])}
        fused = []
        issues = []
        all_item_nos = set(po_items.keys()) | set(pi_items.keys())
        for item_no in all_item_nos:
            po = po_items.get(item_no)
            pi = pi_items.get(item_no)
            if not po:
                issues.append({"item_no": item_no, "field": "item_no", "severity": "critical", "message": "Missing from PO"})
                continue
            if not pi:
                issues.append({"item_no": item_no, "field": "item_no", "severity": "critical", "message": "Missing from PI"})
                continue
            # Dimension fit check
            if po.get("product_dims") and pi.get("box_L"):
                self._check_dimension_fit(item_no, po["product_dims"], pi, issues)
            merged = {**po, **pi, "item_no": item_no}
            fused.append(merged)
        has_critical = any(i["severity"] == "critical" for i in issues)
        return AgentResult(
            success=not has_critical,
            data={"fused_items": fused, "issues": issues},
            confidence=0.95 if not has_critical else 0.50,
            needs_hitl=has_critical,
            hitl_reason="Critical fusion issues found" if has_critical else None,
        )

    def _check_dimension_fit(self, item_no, product_dims, pi, issues):
        for dim_key, box_key in [("length", "box_L"), ("width", "box_W"), ("height", "box_H")]:
            prod_dim = product_dims.get(dim_key, 0)
            box_dim = pi.get(box_key, 0)
            if prod_dim > 0 and box_dim > 0:
                if prod_dim > box_dim + DIMENSION_TOLERANCE:
                    issues.append({
                        "item_no": item_no, "field": dim_key,
                        "severity": "critical",
                        "message": f"Product {dim_key} ({prod_dim}) exceeds box ({box_dim}) + tolerance ({DIMENSION_TOLERANCE})",
                    })
