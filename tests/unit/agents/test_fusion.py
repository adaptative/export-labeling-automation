"""Tests for Fusion Agent (Agent 6.7)."""
import asyncio
from labelforge.agents.fusion import FusionAgent, DIMENSION_TOLERANCE


def _make_po_item(item_no, product_dims=None):
    item = {"item_no": item_no, "description": f"Item {item_no}"}
    if product_dims:
        item["product_dims"] = product_dims
    return item


def _make_pi_item(item_no, box_L=10.0, box_W=8.0, box_H=6.0):
    return {"item_no": item_no, "box_L": box_L, "box_W": box_W, "box_H": box_H}


def test_join_by_item_no():
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001"), _make_po_item("002")],
        "pi_items": [_make_pi_item("001"), _make_pi_item("002")],
    }))
    assert result.success is True
    fused = result.data["fused_items"]
    item_nos = {f["item_no"] for f in fused}
    assert item_nos == {"001", "002"}


def test_missing_po_item_detected():
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [],
        "pi_items": [_make_pi_item("001")],
    }))
    assert result.success is False
    issues = result.data["issues"]
    assert any(i["message"] == "Missing from PO" and i["item_no"] == "001" for i in issues)


def test_missing_pi_item_detected():
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001")],
        "pi_items": [],
    }))
    assert result.success is False
    issues = result.data["issues"]
    assert any(i["message"] == "Missing from PI" and i["item_no"] == "001" for i in issues)


def test_dimension_fit_check_with_tolerance():
    """Product dim exactly at box + tolerance should pass."""
    agent = FusionAgent()
    # product length = 10.5, box_L = 10.0, tolerance = 0.5 => 10.5 <= 10.5 => pass
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001", product_dims={"length": 10.5, "width": 7.0, "height": 5.0})],
        "pi_items": [_make_pi_item("001", box_L=10.0, box_W=8.0, box_H=6.0)],
    }))
    dim_issues = [i for i in result.data["issues"] if i.get("field") in ("length", "width", "height")]
    assert len(dim_issues) == 0


def test_dimension_fit_check_exceeds_tolerance():
    """Product dim exceeding box + tolerance should trigger critical issue."""
    agent = FusionAgent()
    # product length = 11.0, box_L = 10.0, tolerance = 0.5 => 11.0 > 10.5 => fail
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001", product_dims={"length": 11.0, "width": 7.0, "height": 5.0})],
        "pi_items": [_make_pi_item("001", box_L=10.0, box_W=8.0, box_H=6.0)],
    }))
    dim_issues = [i for i in result.data["issues"] if i.get("field") == "length"]
    assert len(dim_issues) == 1
    assert dim_issues[0]["severity"] == "critical"


def test_critical_issues_trigger_hitl():
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001")],
        "pi_items": [],  # Missing PI => critical
    }))
    assert result.needs_hitl is True
    assert result.hitl_reason == "Critical fusion issues found"


def test_no_issues_high_confidence():
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001")],
        "pi_items": [_make_pi_item("001")],
    }))
    assert result.confidence == 0.95
    assert result.needs_hitl is False
    assert len(result.data["issues"]) == 0
