"""Compliance Classifier Agent (TASK-033, Sprint-12).

Evaluates fused order items against the tenant's active compliance rule set
and emits a :class:`ComplianceReport` per item. Heavy lifting is delegated
to the deterministic :class:`RuleMatcher` from
``labelforge.compliance.rule_engine`` — the LLM is only invoked to resolve
*ambiguous* verdicts (e.g. a rule flagged ``needs_review`` or conflicting
warnings from multiple rules) and to generate contextual HiTL questions.

Input::

    {
        "fused_items": [FusedItem.dict(), ...],
        "rules": [RuleDefinition.dict() | RuleDefinition, ...],
        "default_destination": "US",   # optional — used if item omits one
    }

Output :class:`AgentResult.data`::

    {
        "reports":   [ComplianceReport.dict(), ...],
        "warnings":  {item_no: [str, ...]},   # applicable warnings per item
        "item_state": "COMPLIANCE_EVAL",      # advances every passed item
        "needs_hitl_items": [item_no, ...],
    }

HiTL is triggered when *any* item:

*   has a failing verdict (regulatory risk — never auto-pass),
*   has more than ``AMBIGUOUS_WARNING_THRESHOLD`` applicable warnings (likely
    overlap between rules that a reviewer should consolidate), or
*   was evaluated against zero rules (importer profile drift — refuse to
    silently mark items compliant).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from labelforge.agents.base import AgentResult, BaseAgent
from labelforge.compliance.rule_engine import (
    ComplianceReport as EngineComplianceReport,
    RuleContext,
    RuleDefinition,
    RuleMatcher,
)

logger = logging.getLogger(__name__)

AMBIGUOUS_WARNING_THRESHOLD = 4   # >4 warnings on one item → HiTL
LOW_CONFIDENCE_THRESHOLD = 0.70


_AMBIGUITY_PROMPT = """You are a compliance review triage agent.

A product failed compliance against one or more rules, or carries a large
number of overlapping warnings. Your job is to decide whether the reviewer
needs to act and craft a single clear question for them.

Item:
{item_json}

Verdicts:
{verdicts_json}

Applicable warnings:
{warnings_json}

Return a JSON object:
{{
  "needs_hitl": true | false,
  "priority": "P0" | "P1" | "P2",
  "hitl_question": "<single concise question for the reviewer>",
  "summary": "<brief summary of the compliance risk>"
}}

Return ONLY JSON. No markdown fences.
"""


class ComplianceClassifierAgent(BaseAgent):
    """Runs the compliance rule engine over a batch of fused items.

    The agent is deliberately thin — the rule engine is the source of truth
    for pass/fail and for warnings. The LLM only runs as a triage helper for
    failed or warning-heavy items, and only if a provider is configured.
    """

    agent_id = "agent-6.9-compliance-classifier"

    def __init__(self, llm_provider: Optional[Any] = None, matcher: Optional[RuleMatcher] = None) -> None:
        self.llm = llm_provider
        self.matcher = matcher or RuleMatcher()

    async def execute(self, input_data: dict) -> AgentResult:
        fused_items: list[dict] = list(input_data.get("fused_items") or [])
        raw_rules = list(input_data.get("rules") or [])
        default_destination: str = input_data.get("default_destination") or "US"

        rules = [self._coerce_rule(r) for r in raw_rules]
        rules = [r for r in rules if r is not None]

        reports: list[dict] = []
        warnings_by_item: dict[str, list[str]] = {}
        needs_hitl_items: list[str] = []
        hitl_reasons: list[str] = []
        cost = 0.0
        all_passed = True
        confidence_samples: list[float] = []

        if not fused_items:
            logger.info("ComplianceClassifier: no fused items supplied, returning empty report batch")
            return AgentResult(
                success=True,
                data={
                    "reports": [],
                    "warnings": {},
                    "item_state": "COMPLIANCE_EVAL",
                    "needs_hitl_items": [],
                },
                confidence=1.0,
                needs_hitl=False,
                cost=0.0,
            )

        if not rules:
            # Zero rules usually means an importer-profile drift bug. We refuse
            # to silently mark items "compliant" — every item goes to HiTL.
            hitl_reasons.append("No active compliance rules loaded for tenant")

        for item in fused_items:
            item_no = str(item.get("item_no") or "UNKNOWN")
            ctx = self._context_from_item(item, default_destination)

            engine_report = self.matcher.evaluate(ctx, rules)
            report_dict = self._report_to_dict(engine_report)
            reports.append(report_dict)

            warnings_by_item[item_no] = list(engine_report.applicable_warnings)

            # Compute per-item confidence from verdict density.
            confidence_samples.append(self._item_confidence(engine_report, len(rules)))

            ambiguous = (
                not engine_report.passed
                or len(engine_report.applicable_warnings) > AMBIGUOUS_WARNING_THRESHOLD
                or not rules
            )
            if ambiguous:
                needs_hitl_items.append(item_no)
                all_passed = False

                if self.llm and rules:
                    question, cost_delta = await self._ask_for_triage(
                        item, engine_report
                    )
                    cost += cost_delta
                    if question:
                        report_dict["hitl_question"] = question
                        hitl_reasons.append(f"{item_no}: {question}")
                else:
                    hitl_reasons.append(
                        f"{item_no}: "
                        + ("no rules available" if not rules else self._default_reason(engine_report))
                    )

        confidence = (
            sum(confidence_samples) / len(confidence_samples)
            if confidence_samples
            else 1.0
        )
        confidence = round(max(0.0, min(1.0, confidence)), 2)

        needs_hitl = bool(needs_hitl_items) or confidence < LOW_CONFIDENCE_THRESHOLD

        logger.info(
            "ComplianceClassifier: %d items evaluated, %d need HiTL, confidence=%.2f, cost=$%.4f",
            len(fused_items),
            len(needs_hitl_items),
            confidence,
            cost,
        )

        return AgentResult(
            success=all_passed and not needs_hitl_items,
            data={
                "reports": reports,
                "warnings": warnings_by_item,
                "item_state": "COMPLIANCE_EVAL",
                "needs_hitl_items": needs_hitl_items,
            },
            confidence=confidence,
            needs_hitl=needs_hitl,
            hitl_reason="; ".join(hitl_reasons) if hitl_reasons else None,
            cost=cost,
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _coerce_rule(raw: Any) -> Optional[RuleDefinition]:
        """Accept either a :class:`RuleDefinition` or a dict with the same shape."""
        if isinstance(raw, RuleDefinition):
            return raw
        if not isinstance(raw, dict):
            return None
        try:
            return RuleDefinition(
                code=raw["code"],
                version=int(raw.get("version", 1)),
                title=raw.get("title", raw["code"]),
                country=raw.get("country") or raw.get("region") or "US",
                category=raw.get("category", "compliance"),
                placement=raw.get("placement", "both"),
                conditions=raw.get("conditions") or raw.get("logic", {}).get("conditions") or {"op": "true"},
                requirements=raw.get("requirements") or raw.get("logic", {}).get("requirements") or {"op": "true"},
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping malformed rule %r: %s", raw, exc)
            return None

    @staticmethod
    def _context_from_item(item: dict, default_destination: str) -> RuleContext:
        """Project a FusedItem dict into a RuleContext.

        Known fields are promoted onto the dataclass; anything else stays in
        ``custom`` so DSL rules can still reference it via ``ctx.custom[...]``.
        """
        known = {"material", "destination", "weight", "product_type", "dimensions"}
        custom = {k: v for k, v in item.items() if k not in known and k != "item_no"}
        weight = item.get("weight")
        if weight is None:
            weight = item.get("net_weight")
        try:
            weight_f = float(weight) if weight is not None else 0.0
        except (TypeError, ValueError):
            weight_f = 0.0

        return RuleContext(
            item_no=str(item.get("item_no") or "UNKNOWN"),
            material=item.get("material"),
            destination=item.get("destination") or default_destination,
            weight=weight_f,
            product_type=item.get("product_type"),
            dimensions=item.get("dimensions") or item.get("product_dims"),
            custom=custom,
        )

    @staticmethod
    def _report_to_dict(report: EngineComplianceReport) -> dict:
        return {
            "item_no": report.item_no,
            "verdicts": [
                {
                    "rule_code": v.rule_code,
                    "rule_version": v.rule_version,
                    "passed": v.passed,
                    "explanation": v.explanation,
                    "placement": v.placement,
                }
                for v in report.verdicts
            ],
            "applicable_warnings": list(report.applicable_warnings),
            "passed": report.passed,
        }

    @staticmethod
    def _item_confidence(report: EngineComplianceReport, rules_evaluated: int) -> float:
        """Confidence heuristic.

        * 1.0 when the item passes every applicable rule.
        * Decays by 0.1 per failing verdict, floor 0.5.
        * Drops to 0.4 when zero rules were evaluated (profile drift).
        """
        if rules_evaluated == 0:
            return 0.4
        failing = sum(1 for v in report.verdicts if not v.passed)
        if failing == 0:
            return 1.0
        return max(0.5, 1.0 - 0.1 * failing)

    @staticmethod
    def _default_reason(report: EngineComplianceReport) -> str:
        failures = [v.rule_code for v in report.verdicts if not v.passed]
        if failures:
            return f"failed rules: {', '.join(failures)}"
        return f"{len(report.applicable_warnings)} overlapping warnings"

    async def _ask_for_triage(
        self, item: dict, report: EngineComplianceReport
    ) -> tuple[Optional[str], float]:
        """Use the LLM to produce a compact HiTL triage question."""
        try:
            safe_verdicts = [
                {
                    "rule_code": v.rule_code,
                    "passed": v.passed,
                    "explanation": v.explanation,
                }
                for v in report.verdicts
            ]
            prompt = _AMBIGUITY_PROMPT.format(
                item_json=json.dumps(item, default=str),
                verdicts_json=json.dumps(safe_verdicts),
                warnings_json=json.dumps(list(report.applicable_warnings)),
            )
            result = await self.llm.complete(prompt, model_id="default")
            content = getattr(result, "content", "").strip()
            data = json.loads(content)
            return data.get("hitl_question"), getattr(result, "cost_usd", 0.0) or 0.0
        except Exception as exc:
            logger.debug("LLM triage failed for %s: %s", report.item_no, exc)
            return None, 0.0
