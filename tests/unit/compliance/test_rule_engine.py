"""Tests for the compliance rule engine — compiler and matcher."""
import time
from labelforge.compliance.rule_engine import (
    RuleCompiler, RuleContext, RuleDefinition, RuleMatcher, RuleVerdict, ComplianceReport,
)


def _make_rule(code="R001", version=1, title="Test Rule", country="US",
               category="general", placement="carton",
               conditions=None, requirements=None):
    return RuleDefinition(
        code=code, version=version, title=title, country=country,
        category=category, placement=placement,
        conditions=conditions or {"op": "true"},
        requirements=requirements or {"op": "true"},
    )


# ── Operator tests ───────────────────────────────────────────────────────────


def test_operator_eq():
    compiler = RuleCompiler()
    ctx = RuleContext(item_no="001", destination="US")
    rule = _make_rule(conditions={"op": "==", "field": "destination", "value": "US"},
                      requirements={"op": "true"})
    fn = compiler.compile(rule)
    verdict = fn(ctx)
    assert verdict.passed is True


def test_operator_neq():
    compiler = RuleCompiler()
    ctx = RuleContext(item_no="001", destination="US")
    rule = _make_rule(conditions={"op": "!=", "field": "destination", "value": "EU"},
                      requirements={"op": "true"})
    fn = compiler.compile(rule)
    assert fn(ctx).passed is True


def test_operator_in():
    compiler = RuleCompiler()
    ctx = RuleContext(item_no="001", destination="CA")
    rule = _make_rule(conditions={"op": "in", "field": "destination", "values": ["US", "CA", "MX"]},
                      requirements={"op": "true"})
    fn = compiler.compile(rule)
    assert fn(ctx).passed is True


def test_operator_not_in():
    compiler = RuleCompiler()
    ctx = RuleContext(item_no="001", destination="JP")
    rule = _make_rule(conditions={"op": "not_in", "field": "destination", "values": ["US", "CA"]},
                      requirements={"op": "true"})
    fn = compiler.compile(rule)
    assert fn(ctx).passed is True


def test_operator_gt():
    compiler = RuleCompiler()
    ctx = RuleContext(item_no="001", weight=15.0)
    rule = _make_rule(conditions={"op": ">", "field": "weight", "value": 10.0},
                      requirements={"op": "true"})
    fn = compiler.compile(rule)
    assert fn(ctx).passed is True


def test_operator_lt():
    compiler = RuleCompiler()
    ctx = RuleContext(item_no="001", weight=5.0)
    rule = _make_rule(conditions={"op": "<", "field": "weight", "value": 10.0},
                      requirements={"op": "true"})
    fn = compiler.compile(rule)
    assert fn(ctx).passed is True


def test_operator_gte():
    compiler = RuleCompiler()
    ctx = RuleContext(item_no="001", weight=10.0)
    rule = _make_rule(conditions={"op": ">=", "field": "weight", "value": 10.0},
                      requirements={"op": "true"})
    assert compiler.compile(rule)(ctx).passed is True


def test_operator_lte():
    compiler = RuleCompiler()
    ctx = RuleContext(item_no="001", weight=10.0)
    rule = _make_rule(conditions={"op": "<=", "field": "weight", "value": 10.0},
                      requirements={"op": "true"})
    assert compiler.compile(rule)(ctx).passed is True


def test_operator_and():
    compiler = RuleCompiler()
    ctx = RuleContext(item_no="001", destination="US", weight=15.0)
    rule = _make_rule(
        conditions={"op": "AND", "children": [
            {"op": "==", "field": "destination", "value": "US"},
            {"op": ">", "field": "weight", "value": 10.0},
        ]},
        requirements={"op": "true"},
    )
    assert compiler.compile(rule)(ctx).passed is True


def test_operator_or():
    compiler = RuleCompiler()
    ctx = RuleContext(item_no="001", destination="JP")
    rule = _make_rule(
        conditions={"op": "OR", "children": [
            {"op": "==", "field": "destination", "value": "US"},
            {"op": "==", "field": "destination", "value": "JP"},
        ]},
        requirements={"op": "true"},
    )
    assert compiler.compile(rule)(ctx).passed is True


def test_operator_not():
    compiler = RuleCompiler()
    ctx = RuleContext(item_no="001", destination="JP")
    rule = _make_rule(
        conditions={"op": "NOT", "child": {"op": "==", "field": "destination", "value": "US"}},
        requirements={"op": "true"},
    )
    assert compiler.compile(rule)(ctx).passed is True


# ── RuleContext tests ────────────────────────────────────────────────────────


def test_rule_context_holds_item_data():
    ctx = RuleContext(item_no="X-42", material="plastic", destination="EU",
                      weight=2.5, product_type="toy",
                      dimensions={"length": 10}, custom={"flammable": True})
    assert ctx.item_no == "X-42"
    assert ctx.material == "plastic"
    assert ctx.custom["flammable"] is True


def test_rule_context_custom_field_access():
    compiler = RuleCompiler()
    ctx = RuleContext(item_no="001", custom={"flammable": True})
    rule = _make_rule(
        conditions={"op": "==", "field": "flammable", "value": True},
        requirements={"op": "true"},
    )
    assert compiler.compile(rule)(ctx).passed is True


# ── RuleCompiler tests ───────────────────────────────────────────────────────


def test_rule_compiler_compiles_to_callable():
    compiler = RuleCompiler()
    rule = _make_rule()
    fn = compiler.compile(rule)
    assert callable(fn)
    ctx = RuleContext(item_no="001")
    result = fn(ctx)
    assert isinstance(result, RuleVerdict)


# ── RuleMatcher tests ───────────────────────────────────────────────────────


def test_compiled_rules_cached_in_matcher():
    matcher = RuleMatcher()
    rule = _make_rule(code="R-CACHE", version=1)
    ctx = RuleContext(item_no="001")
    matcher.evaluate(ctx, [rule])
    assert "R-CACHE@v1" in matcher._cache
    # Second call should use cache
    matcher.evaluate(ctx, [rule])
    assert len(matcher._cache) == 1


def test_rule_matcher_returns_compliance_report():
    matcher = RuleMatcher()
    rules = [_make_rule(code="R001"), _make_rule(code="R002")]
    ctx = RuleContext(item_no="001")
    report = matcher.evaluate(ctx, rules)
    assert isinstance(report, ComplianceReport)
    assert report.item_no == "001"
    assert len(report.verdicts) == 2


def test_applicable_warnings_from_passing_rules():
    matcher = RuleMatcher()
    rule = _make_rule(code="R001", title="Prop 65 Warning",
                      conditions={"op": "true"},
                      requirements={"op": "true"})
    ctx = RuleContext(item_no="001")
    report = matcher.evaluate(ctx, [rule])
    assert "Prop 65 Warning" in report.applicable_warnings


def test_not_applicable_rules_marked_correctly():
    matcher = RuleMatcher()
    rule = _make_rule(
        conditions={"op": "==", "field": "destination", "value": "EU"},
        requirements={"op": "true"},
    )
    ctx = RuleContext(item_no="001", destination="US")  # Not EU
    report = matcher.evaluate(ctx, [rule])
    assert report.verdicts[0].explanation == "Not applicable"
    assert report.passed is True


def test_failing_rule():
    matcher = RuleMatcher()
    rule = _make_rule(
        title="Must be lightweight",
        conditions={"op": "true"},
        requirements={"op": "<", "field": "weight", "value": 5.0},
    )
    ctx = RuleContext(item_no="001", weight=10.0)
    report = matcher.evaluate(ctx, [rule])
    assert report.passed is False
    assert report.verdicts[0].passed is False
    assert "Failed" in report.verdicts[0].explanation


def test_100_rules_evaluated_performance():
    """Evaluate 100 rules and ensure it completes in under 1 second."""
    matcher = RuleMatcher()
    rules = [_make_rule(code=f"R{i:04d}", version=1) for i in range(100)]
    ctx = RuleContext(item_no="001")
    start = time.time()
    report = matcher.evaluate(ctx, rules)
    elapsed = time.time() - start
    assert len(report.verdicts) == 100
    assert elapsed < 1.0, f"100-rule evaluation took {elapsed:.3f}s (expected < 1s)"
