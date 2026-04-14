"""Tests for PI Parser Agent (Agent 6.3) — deterministic, no LLM."""
import asyncio
from labelforge.agents.pi_parser import PIParserAgent


# ── Basic behavior (backward compat) ────────────────────────────────────────


def test_deterministic_no_llm_calls():
    """PIParserAgent should not require an LLM provider."""
    agent = PIParserAgent()
    assert not hasattr(agent, "llm")


def test_template_mapping_applied_correctly():
    agent = PIParserAgent()
    input_data = {
        "rows": [
            {"Col_A": "ITEM-001", "Col_B": 12.5, "Col_C": 8.0, "Col_D": 6.0},
            {"Col_A": "ITEM-002", "Col_B": 10.0, "Col_C": 7.0, "Col_D": 5.0},
        ],
        "template_mapping": {
            "item_no": "Col_A",
            "box_L": "Col_B",
            "box_W": "Col_C",
            "box_H": "Col_D",
        },
    }
    result = asyncio.run(agent.execute(input_data))
    assert result.success is True
    items = result.data["items"]
    assert len(items) == 2
    assert items[0]["item_no"] == "ITEM-001"
    assert items[0]["box_L"] == 12.5
    assert items[1]["item_no"] == "ITEM-002"
    assert items[1]["box_W"] == 7.0


def test_confidence_is_always_1():
    """Full items with all required fields should have confidence 1.0."""
    agent = PIParserAgent()
    result = asyncio.run(agent.execute({
        "rows": [{"a": "ITEM-1", "b": 10, "c": 8, "d": 6, "e": 50}],
        "template_mapping": {
            "item_no": "a",
            "box_L": "b",
            "box_W": "c",
            "box_H": "d",
            "total_cartons": "e",
        },
    }))
    assert result.confidence == 1.0


def test_handles_missing_fields():
    agent = PIParserAgent()
    input_data = {
        "rows": [{"Col_A": "ITEM-001"}],
        "template_mapping": {
            "item_no": "Col_A",
            "box_L": "Col_B",
        },
    }
    result = asyncio.run(agent.execute(input_data))
    assert result.success is True
    items = result.data["items"]
    assert items[0]["item_no"] == "ITEM-001"
    assert items[0]["box_L"] is None


def test_empty_rows():
    agent = PIParserAgent()
    result = asyncio.run(agent.execute({"rows": [], "template_mapping": {"x": "a"}}))
    assert result.success is True
    assert result.data["items"] == []


# ── Type coercion ────────────────────────────────────────────────────────────


def test_type_coercion_string_to_float():
    agent = PIParserAgent()
    result = asyncio.run(agent.execute({
        "rows": [{"a": "ITEM-1", "b": "12.5", "c": "8.0", "d": "6.0", "e": "50"}],
        "template_mapping": {
            "item_no": "a",
            "box_L": "b",
            "box_W": "c",
            "box_H": "d",
            "total_cartons": "e",
        },
    }))
    items = result.data["items"]
    assert items[0]["box_L"] == 12.5
    assert isinstance(items[0]["box_L"], float)


def test_type_coercion_string_to_int():
    agent = PIParserAgent()
    result = asyncio.run(agent.execute({
        "rows": [{"a": "ITEM-1", "b": 10, "c": 8, "d": 6, "e": "50", "f": "4"}],
        "template_mapping": {
            "item_no": "a",
            "box_L": "b",
            "box_W": "c",
            "box_H": "d",
            "total_cartons": "e",
            "inner_pack": "f",
        },
    }))
    items = result.data["items"]
    assert items[0]["total_cartons"] == 50
    assert isinstance(items[0]["total_cartons"], int)
    assert items[0]["inner_pack"] == 4
    assert isinstance(items[0]["inner_pack"], int)


# ── CBM auto-computation ────────────────────────────────────────────────────


def test_auto_compute_cbm():
    """When cbm not in template_mapping, auto-compute from L*W*H/1e6."""
    agent = PIParserAgent()
    result = asyncio.run(agent.execute({
        "rows": [{"a": "ITEM-1", "b": 100, "c": 50, "d": 40, "e": 20}],
        "template_mapping": {
            "item_no": "a",
            "box_L": "b",
            "box_W": "c",
            "box_H": "d",
            "total_cartons": "e",
        },
    }))
    items = result.data["items"]
    # 100 * 50 * 40 / 1e6 = 0.2
    assert items[0]["cbm"] == 0.2


def test_cbm_not_overridden_if_in_mapping():
    """If cbm is in template_mapping, don't auto-compute."""
    agent = PIParserAgent()
    result = asyncio.run(agent.execute({
        "rows": [{"a": "ITEM-1", "b": 100, "c": 50, "d": 40, "e": 20, "f": 0.15}],
        "template_mapping": {
            "item_no": "a",
            "box_L": "b",
            "box_W": "c",
            "box_H": "d",
            "total_cartons": "e",
            "cbm": "f",
        },
    }))
    items = result.data["items"]
    assert items[0]["cbm"] == 0.15  # from mapping, not computed


# ── Warnings and confidence ──────────────────────────────────────────────────


def test_missing_item_no_generates_warning():
    agent = PIParserAgent()
    result = asyncio.run(agent.execute({
        "rows": [{"b": 10, "c": 8, "d": 6, "e": 50}],
        "template_mapping": {
            "item_no": "a",  # column 'a' not in row
            "box_L": "b",
            "box_W": "c",
            "box_H": "d",
            "total_cartons": "e",
        },
    }))
    assert any("item_no" in w.get("field", "") for w in result.data["warnings"])


def test_missing_required_dims_lowers_confidence():
    agent = PIParserAgent()
    result = asyncio.run(agent.execute({
        "rows": [{"a": "ITEM-1"}],  # only item_no
        "template_mapping": {"item_no": "a"},
    }))
    assert result.confidence < 1.0


def test_row_count_in_output():
    agent = PIParserAgent()
    result = asyncio.run(agent.execute({
        "rows": [{"a": 1}, {"a": 2}, {"a": 3}],
        "template_mapping": {"item_no": "a"},
    }))
    assert result.data["row_count"] == 3


def test_warnings_in_output():
    agent = PIParserAgent()
    result = asyncio.run(agent.execute({
        "rows": [{"a": "ITEM-1"}],
        "template_mapping": {"item_no": "a"},
    }))
    assert "warnings" in result.data
    assert isinstance(result.data["warnings"], list)
