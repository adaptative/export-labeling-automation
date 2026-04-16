"""Tests for Compliance Classifier Agent (TASK-033, Sprint-12)."""
import asyncio

from labelforge.agents.compliance_classifier import (
    AMBIGUOUS_WARNING_THRESHOLD,
    ComplianceClassifierAgent,
)
from labelforge.compliance.rule_engine import RuleDefinition


def _rule(
    code="R001",
    version=1,
    title="Test rule",
    country="US",
    category="general",
    placement="carton",
    conditions=None,
    requirements=None,
):
    return RuleDefinition(
        code=code, version=version, title=title, country=country,
        category=category, placement=placement,
        conditions=conditions or {"op": "true"},
        requirements=requirements or {"op": "true"},
    )


def _item(item_no="1", **kwargs):
    base = {
        "item_no": item_no,
        "upc": "012345678905",
        "description": "Ceramic Mug",
        "material": "ceramic",
        "destination": "US",
        "net_weight": 0.5,
    }
    base.update(kwargs)
    return base


# ── Core rule evaluation ───────────────────────────────────────────────────


def test_all_rules_evaluated():
    """Every rule produces a verdict for every item."""
    agent = ComplianceClassifierAgent()
    rules = [_rule(code="R001"), _rule(code="R002"), _rule(code="R003")]
    result = asyncio.run(agent.execute({
        "fused_items": [_item("1"), _item("2")],
        "rules": rules,
    }))
    reports = result.data["reports"]
    assert len(reports) == 2
    for report in reports:
        assert {v["rule_code"] for v in report["verdicts"]} == {"R001", "R002", "R003"}


def test_item_state_advances_to_compliance_eval():
    agent = ComplianceClassifierAgent()
    result = asyncio.run(agent.execute({
        "fused_items": [_item("1")],
        "rules": [_rule()],
    }))
    assert result.data["item_state"] == "COMPLIANCE_EVAL"


def test_passing_item_reports_passed():
    agent = ComplianceClassifierAgent()
    rules = [_rule(
        code="PROP65",
        conditions={"op": "==", "field": "destination", "value": "US"},
        requirements={"op": "==", "field": "material", "value": "ceramic"},
    )]
    result = asyncio.run(agent.execute({
        "fused_items": [_item("1", material="ceramic")],
        "rules": rules,
    }))
    report = result.data["reports"][0]
    assert report["passed"] is True
    assert result.success is True


def test_failing_item_triggers_hitl():
    """Failing any rule → needs_hitl and item is flagged."""
    agent = ComplianceClassifierAgent()
    rules = [_rule(
        code="PROP65",
        conditions={"op": "==", "field": "destination", "value": "US"},
        requirements={"op": "==", "field": "material", "value": "glass"},
    )]
    result = asyncio.run(agent.execute({
        "fused_items": [_item("1", material="ceramic")],   # requires glass, we have ceramic
        "rules": rules,
    }))
    assert result.success is False
    assert result.needs_hitl is True
    assert "1" in result.data["needs_hitl_items"]


def test_correct_warnings_identified():
    """Applicable warnings bubble up on passing+applicable verdicts."""
    agent = ComplianceClassifierAgent()
    rules = [_rule(
        code="PROP65_CERAMIC",
        title="California Proposition 65 warning",
        conditions={"op": "==", "field": "destination", "value": "US"},
        requirements={"op": "true"},
    )]
    result = asyncio.run(agent.execute({
        "fused_items": [_item("1", destination="US")],
        "rules": rules,
    }))
    warnings = result.data["warnings"]["1"]
    assert any("Proposition 65" in w for w in warnings)


def test_non_applicable_rule_skipped_cleanly():
    """Rules whose conditions don't match produce a 'Not applicable' verdict and no warning."""
    agent = ComplianceClassifierAgent()
    rules = [_rule(
        code="EU_CE",
        title="EU CE Marking",
        conditions={"op": "==", "field": "destination", "value": "EU"},
        requirements={"op": "true"},
    )]
    result = asyncio.run(agent.execute({
        "fused_items": [_item("1", destination="US")],
        "rules": rules,
    }))
    report = result.data["reports"][0]
    assert report["passed"] is True
    assert report["verdicts"][0]["explanation"] == "Not applicable"
    assert result.data["warnings"]["1"] == []


# ── HiTL for ambiguous cases ────────────────────────────────────────────────


def test_hitl_on_many_overlapping_warnings():
    """>threshold applicable warnings → HiTL for consolidation."""
    agent = ComplianceClassifierAgent()
    rules = [
        _rule(code=f"R{i:03}", title=f"Warning {i}", conditions={"op": "true"})
        for i in range(AMBIGUOUS_WARNING_THRESHOLD + 2)
    ]
    result = asyncio.run(agent.execute({
        "fused_items": [_item("1")],
        "rules": rules,
    }))
    assert result.needs_hitl is True
    assert "1" in result.data["needs_hitl_items"]


def test_zero_rules_triggers_hitl():
    """Empty rule set is treated as profile drift — never silently pass."""
    agent = ComplianceClassifierAgent()
    result = asyncio.run(agent.execute({
        "fused_items": [_item("1")],
        "rules": [],
    }))
    assert result.needs_hitl is True
    assert result.confidence < 0.7


def test_empty_items_is_noop():
    agent = ComplianceClassifierAgent()
    result = asyncio.run(agent.execute({
        "fused_items": [],
        "rules": [_rule()],
    }))
    assert result.success is True
    assert result.needs_hitl is False
    assert result.data["reports"] == []


def test_rules_accepted_as_dicts():
    """The agent should coerce raw dict rules from the API layer."""
    agent = ComplianceClassifierAgent()
    rules = [{
        "code": "R001",
        "version": 1,
        "title": "From dict",
        "country": "US",
        "placement": "carton",
        "conditions": {"op": "true"},
        "requirements": {"op": "true"},
    }]
    result = asyncio.run(agent.execute({
        "fused_items": [_item("1")],
        "rules": rules,
    }))
    assert result.data["reports"][0]["verdicts"][0]["rule_code"] == "R001"


def test_malformed_rule_skipped():
    agent = ComplianceClassifierAgent()
    rules = [
        {"garbage": True},   # missing 'code'
        _rule(code="OK"),
    ]
    result = asyncio.run(agent.execute({
        "fused_items": [_item("1")],
        "rules": rules,
    }))
    # Only the well-formed rule was evaluated.
    assert [v["rule_code"] for v in result.data["reports"][0]["verdicts"]] == ["OK"]
