"""PO Parser Agent (Agent 6.2)."""
from labelforge.agents.base import BaseAgent, AgentResult


def validate_upc_luhn(upc: str) -> bool:
    if len(upc) != 12 or not upc.isdigit():
        return False
    digits = [int(d) for d in upc]
    odd_sum = sum(digits[i] for i in range(0, 11, 2))
    even_sum = sum(digits[i] for i in range(1, 11, 2))
    check = (10 - (odd_sum * 3 + even_sum) % 10) % 10
    return check == digits[11]


class POParserAgent(BaseAgent):
    agent_id = "agent-6.2-po-parser"

    def __init__(self, llm_provider):
        self.llm = llm_provider

    async def execute(self, input_data: dict) -> AgentResult:
        items = input_data.get("items", [])
        parsed_items = []
        issues = []
        for item in items:
            upc = item.get("upc", "")
            if not validate_upc_luhn(upc):
                issues.append({"item_no": item.get("item_no"), "issue": "UPC Luhn check failed"})
            parsed_items.append(item)
        needs_hitl = len(issues) > 0
        return AgentResult(
            success=not needs_hitl,
            data={"items": parsed_items, "issues": issues},
            confidence=0.90 if not needs_hitl else 0.60,
            needs_hitl=needs_hitl,
            hitl_reason=f"{len(issues)} UPC validation failures" if needs_hitl else None,
        )
