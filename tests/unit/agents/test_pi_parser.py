"""Tests for PI Parser Agent (Agent 6.3) — deterministic, no LLM."""
import asyncio
from labelforge.agents.pi_parser import PIParserAgent


def test_deterministic_no_llm_calls():
    """PIParserAgent should not require an LLM provider."""
    agent = PIParserAgent()
    # Should not have an llm attribute
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
    agent = PIParserAgent()
    result = asyncio.run(agent.execute({"rows": [{"a": 1}], "template_mapping": {"x": "a"}}))
    assert result.confidence == 1.0


def test_handles_missing_fields():
    agent = PIParserAgent()
    input_data = {
        "rows": [{"Col_A": "ITEM-001"}],  # Missing Col_B
        "template_mapping": {
            "item_no": "Col_A",
            "box_L": "Col_B",  # Col_B not in row
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
