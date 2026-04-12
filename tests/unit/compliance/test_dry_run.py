"""Tests for the rule dry-run engine."""
import copy
from labelforge.compliance.dry_run import DryRunEngine, DryRunReport
from labelforge.compliance.rule_engine import RuleDefinition, RuleContext, RuleMatcher


def _make_rule(code, version=1, title="Rule", conditions=None, requirements=None):
    return RuleDefinition(
        code=code, version=version, title=title, country="US",
        category="general", placement="carton",
        conditions=conditions or {"op": "true"},
        requirements=requirements or {"op": "true"},
    )


def test_newly_failing_detected():
    """Adding a rule that causes an item to fail should be detected."""
    engine = DryRunEngine()
    existing = []
    proposed = _make_rule(
        code="R-NEW", title="Weight limit",
        conditions={"op": "true"},
        requirements={"op": "<", "field": "weight", "value": 5.0},
    )
    items = [RuleContext(item_no="001", weight=10.0)]  # Fails the new rule
    report = engine.run(proposed, existing, items)
    assert "001" in report.newly_failing


def test_newly_passing_detected():
    """Verify the newly_passing path fires when before=fail, after=pass.

    We mock the matcher to control before/after results directly, since the
    additive nature of rule evaluation makes it hard to construct a pure
    newly_passing scenario without mocking.
    """
    from unittest.mock import MagicMock
    from labelforge.compliance.rule_engine import ComplianceReport, RuleVerdict

    fail_report = ComplianceReport(item_no="001", verdicts=[], applicable_warnings=[], passed=False)
    pass_report = ComplianceReport(item_no="001", verdicts=[], applicable_warnings=[], passed=True)

    mock_matcher = MagicMock()
    mock_matcher.evaluate = MagicMock(side_effect=[fail_report, pass_report])

    engine = DryRunEngine(matcher=mock_matcher)
    proposed = _make_rule(code="R-NEW")
    items = [RuleContext(item_no="001")]
    report = engine.run(proposed, [], items)
    assert "001" in report.newly_passing


def test_unchanged_items_tracked():
    engine = DryRunEngine()
    existing = [_make_rule(code="R-STABLE")]
    proposed = _make_rule(code="R-NEW", conditions={"op": "true"}, requirements={"op": "true"})
    items = [RuleContext(item_no="001")]  # Passes both before and after
    report = engine.run(proposed, existing, items)
    assert "001" in report.unchanged


def test_items_evaluated_count_correct():
    engine = DryRunEngine()
    items = [RuleContext(item_no=f"{i:03d}") for i in range(5)]
    proposed = _make_rule(code="R-NEW")
    report = engine.run(proposed, [], items)
    assert report.items_evaluated == 5


def test_no_side_effects_pure_computation():
    """DryRunEngine should not mutate the input data."""
    engine = DryRunEngine()
    existing = [_make_rule(code="R-EXIST")]
    proposed = _make_rule(code="R-NEW")
    items = [RuleContext(item_no="001", weight=3.0)]

    existing_copy = copy.deepcopy(existing)
    items_copy = copy.deepcopy(items)

    engine.run(proposed, existing, items)

    # Verify inputs not mutated
    assert existing[0].code == existing_copy[0].code
    assert items[0].item_no == items_copy[0].item_no
    assert items[0].weight == items_copy[0].weight
