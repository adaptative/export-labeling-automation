"""PI Parser Agent (Agent 6.3) — deterministic, no LLM."""
from labelforge.agents.base import BaseAgent, AgentResult


class PIParserAgent(BaseAgent):
    agent_id = "agent-6.3-pi-parser"

    async def execute(self, input_data: dict) -> AgentResult:
        """Parse proforma invoice — deterministic, NO LLM used."""
        rows = input_data.get("rows", [])
        template_mapping = input_data.get("template_mapping", {})
        parsed = []
        for row in rows:
            item = {}
            for target_field, source_col in template_mapping.items():
                item[target_field] = row.get(source_col)
            parsed.append(item)
        return AgentResult(success=True, data={"items": parsed}, confidence=1.0)
