"""Compliance rule engine — compiler and matcher."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class RuleContext:
    item_no: str
    material: Optional[str] = None
    destination: str = "US"
    weight: float = 0.0
    product_type: Optional[str] = None
    dimensions: Optional[dict] = None
    custom: dict = field(default_factory=dict)


@dataclass
class RuleDefinition:
    code: str
    version: int
    title: str
    country: str
    category: str
    placement: str
    conditions: dict  # DSL AST
    requirements: dict  # DSL AST
    min_font_size_mm: Optional[float] = None


@dataclass
class RuleVerdict:
    rule_code: str
    rule_version: int
    passed: bool
    explanation: str
    placement: str


@dataclass
class ComplianceReport:
    item_no: str
    verdicts: list[RuleVerdict]
    applicable_warnings: list[str]
    passed: bool


class RuleCompiler:
    OPERATORS = {"==", "!=", "in", "not_in", ">", "<", ">=", "<=", "AND", "OR", "NOT"}

    def compile(self, rule: RuleDefinition) -> Callable[[RuleContext], RuleVerdict]:
        def evaluate(ctx: RuleContext) -> RuleVerdict:
            condition_met = self._eval_node(rule.conditions, ctx)
            if not condition_met:
                return RuleVerdict(rule.code, rule.version, True, "Not applicable", rule.placement)
            requirement_met = self._eval_node(rule.requirements, ctx)
            return RuleVerdict(
                rule.code, rule.version, requirement_met,
                "Passed" if requirement_met else f"Failed: {rule.title}",
                rule.placement,
            )
        return evaluate

    def _eval_node(self, node: dict, ctx: RuleContext) -> bool:
        op = node.get("op")
        if op == "==":
            return self._get_value(node["field"], ctx) == node["value"]
        elif op == "!=":
            return self._get_value(node["field"], ctx) != node["value"]
        elif op == "in":
            return self._get_value(node["field"], ctx) in node["values"]
        elif op == "not_in":
            return self._get_value(node["field"], ctx) not in node["values"]
        elif op == ">":
            return self._get_value(node["field"], ctx) > node["value"]
        elif op == "<":
            return self._get_value(node["field"], ctx) < node["value"]
        elif op == ">=":
            return self._get_value(node["field"], ctx) >= node["value"]
        elif op == "<=":
            return self._get_value(node["field"], ctx) <= node["value"]
        elif op == "AND":
            return all(self._eval_node(child, ctx) for child in node["children"])
        elif op == "OR":
            return any(self._eval_node(child, ctx) for child in node["children"])
        elif op == "NOT":
            return not self._eval_node(node["child"], ctx)
        elif op == "true":
            return True
        return False

    def _get_value(self, field: str, ctx: RuleContext) -> Any:
        if hasattr(ctx, field):
            return getattr(ctx, field)
        return ctx.custom.get(field)


class RuleMatcher:
    def __init__(self, compiler: RuleCompiler | None = None):
        self.compiler = compiler or RuleCompiler()
        self._cache: dict[str, Callable] = {}

    def evaluate(self, ctx: RuleContext, rules: list[RuleDefinition]) -> ComplianceReport:
        verdicts = []
        warnings = []
        all_passed = True
        for rule in rules:
            cache_key = f"{rule.code}@v{rule.version}"
            if cache_key not in self._cache:
                self._cache[cache_key] = self.compiler.compile(rule)
            evaluator = self._cache[cache_key]
            verdict = evaluator(ctx)
            verdicts.append(verdict)
            if verdict.passed and verdict.explanation != "Not applicable":
                warnings.append(rule.title)
            if not verdict.passed:
                all_passed = False
        return ComplianceReport(
            item_no=ctx.item_no, verdicts=verdicts,
            applicable_warnings=warnings, passed=all_passed,
        )
