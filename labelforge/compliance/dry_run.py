"""Rule dry-run engine."""
from __future__ import annotations
from dataclasses import dataclass, field
from labelforge.compliance.rule_engine import RuleMatcher, RuleDefinition, RuleContext


@dataclass
class DryRunReport:
    newly_failing: list[str] = field(default_factory=list)
    newly_passing: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    items_evaluated: int = 0
    blocking_errors: list[str] = field(default_factory=list)


class DryRunEngine:
    def __init__(self, matcher: RuleMatcher | None = None):
        self.matcher = matcher or RuleMatcher()

    def run(self, proposed_rule: RuleDefinition, existing_rules: list[RuleDefinition],
            items: list[RuleContext]) -> DryRunReport:
        report = DryRunReport(items_evaluated=len(items))
        rules_without = [r for r in existing_rules if r.code != proposed_rule.code]
        rules_with = rules_without + [proposed_rule]
        for item in items:
            before = self.matcher.evaluate(item, rules_without)
            after = self.matcher.evaluate(item, rules_with)
            if before.passed and not after.passed:
                report.newly_failing.append(item.item_no)
            elif not before.passed and after.passed:
                report.newly_passing.append(item.item_no)
            else:
                report.unchanged.append(item.item_no)
        return report
