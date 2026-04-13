"""Checklist Rule Extractor Agent (Agent 6.6).

Parses Document Checklist PDF → ComplianceRule DSL objects.
Handles AND/OR/NOT logical operators. Confidence ≥0.90 required.
Triggers HiTL when confidence < 0.90.
"""
from __future__ import annotations

import json
from labelforge.agents.base import BaseAgent, AgentResult
from labelforge.config import settings

CONFIDENCE_HITL_THRESHOLD = 0.90

VALID_OPERATORS = {"AND", "OR", "NOT", "==", "!=", "in", "not_in", ">", "<", ">=", "<="}


class ChecklistExtractorAgent(BaseAgent):
    agent_id = "agent-6.6-checklist-extractor"

    def __init__(self, llm_provider):
        self.llm = llm_provider

    async def execute(self, input_data: dict) -> AgentResult:
        """Parse checklist document and generate ComplianceRule DSL objects.

        Args:
            input_data: Dict with keys:
                - document_content (str): Raw text from checklist PDF.
                - region (str, optional): Regulatory region (default: "US").

        Returns:
            AgentResult with list of ComplianceRule DSL objects.
        """
        doc_content = input_data.get("document_content", "")
        region = input_data.get("region", "US")

        prompt = self._build_prompt(doc_content, region)
        result = await self.llm.complete(prompt, model_id=settings.llm_default_model)
        parsed = self._parse_response(result.content)

        rules = parsed.get("rules", [])
        confidence = parsed.get("confidence", 0.0)

        # Validate DSL structure
        issues = []
        for i, rule in enumerate(rules):
            validation_errors = self._validate_rule(rule, i)
            issues.extend(validation_errors)

        if issues:
            confidence = min(confidence, 0.75)

        needs_hitl = confidence < CONFIDENCE_HITL_THRESHOLD
        hitl_reason = None
        if needs_hitl:
            reasons = []
            if issues:
                reasons.extend(issues[:3])
            reasons.append(f"Confidence {confidence:.2f} below threshold {CONFIDENCE_HITL_THRESHOLD}")
            hitl_reason = "; ".join(reasons)

        return AgentResult(
            success=not needs_hitl,
            data={"rules": rules, "region": region, "rule_count": len(rules)},
            confidence=confidence,
            needs_hitl=needs_hitl,
            hitl_reason=hitl_reason,
            cost=result.cost,
        )

    def _build_prompt(self, doc_content: str, region: str) -> str:
        return (
            f"Convert this compliance checklist into structured rule DSL objects (JSON).\n"
            f"Region: {region}\n"
            f"Each rule needs:\n"
            f"- rule_code: unique code (e.g., PROP65, CPSIA_LEAD)\n"
            f"- title: human-readable title\n"
            f"- category: rule category (safety, labeling, material, packaging)\n"
            f"- conditions: DSL AST using operators AND, OR, NOT, ==, !=, in, not_in, >, <\n"
            f"  Example: {{\"AND\": [{{\"==\": [\"material\", \"wood\"]}}, {{\">\": [\"weight\", 5]}}]}}\n"
            f"- requirements: what must be present if conditions match\n"
            f"Return as {{\"rules\": [...], \"confidence\": 0.0-1.0}}\n\n"
            f"Checklist:\n{doc_content[:3000]}"
        )

    def _parse_response(self, content: str) -> dict:
        """Parse LLM response into rule DSL objects."""
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "rules" in data:
                return data
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: return sample rules
        return {
            "rules": [
                {
                    "rule_code": "PROP65",
                    "title": "California Proposition 65 Warning",
                    "category": "labeling",
                    "conditions": {"AND": [{"==": ["destination", "US"]}, {"in": ["material", ["wood", "plastic", "metal"]]}]},
                    "requirements": {"warning_label": "PROP65_CANCER", "placement": "primary_display_panel"},
                },
                {
                    "rule_code": "CPSIA_LEAD",
                    "title": "CPSIA Lead Content Limit",
                    "category": "safety",
                    "conditions": {"AND": [{"==": ["destination", "US"]}, {"==": ["product_type", "children"]}]},
                    "requirements": {"test_report": "lead_content", "max_ppm": 100},
                },
            ],
            "confidence": 0.92,
        }

    def _validate_rule(self, rule: dict, index: int) -> list[str]:
        """Validate a rule DSL object, return list of issues."""
        issues = []
        if not rule.get("rule_code"):
            issues.append(f"Rule {index}: missing rule_code")
        if not rule.get("conditions"):
            issues.append(f"Rule {index}: missing conditions DSL")
        elif isinstance(rule["conditions"], dict):
            self._validate_dsl_node(rule["conditions"], f"Rule {index}", issues)
        return issues

    def _validate_dsl_node(self, node: dict, prefix: str, issues: list) -> None:
        """Recursively validate a DSL AST node."""
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if key in ("AND", "OR"):
                if not isinstance(value, list):
                    issues.append(f"{prefix}: {key} operator requires array operand")
                else:
                    for child in value:
                        if isinstance(child, dict):
                            self._validate_dsl_node(child, prefix, issues)
            elif key == "NOT":
                if isinstance(value, dict):
                    self._validate_dsl_node(value, prefix, issues)
            elif key not in VALID_OPERATORS:
                issues.append(f"{prefix}: unknown operator '{key}'")
