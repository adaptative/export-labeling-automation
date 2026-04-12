"""Tests for PO Parser Agent (Agent 6.2)."""
import asyncio
from labelforge.agents.po_parser import POParserAgent, validate_upc_luhn
from tests.stubs import LLMProvider


# Known valid UPC-A: 012345678905
VALID_UPC = "012345678905"
INVALID_UPC = "012345678900"


def test_validate_upc_luhn_with_valid_upc():
    assert validate_upc_luhn(VALID_UPC) is True


def test_validate_upc_luhn_with_invalid_upc():
    assert validate_upc_luhn(INVALID_UPC) is False


def test_validate_upc_luhn_wrong_length():
    assert validate_upc_luhn("12345") is False


def test_validate_upc_luhn_non_digit():
    assert validate_upc_luhn("01234567890a") is False


def test_hitl_triggered_on_luhn_failure(llm_provider):
    agent = POParserAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "items": [{"item_no": "001", "upc": INVALID_UPC}],
    }))
    assert result.needs_hitl is True
    assert result.success is False
    assert result.confidence == 0.60
    assert "1 UPC validation failures" in result.hitl_reason


def test_multi_item_parsing(llm_provider):
    agent = POParserAgent(llm_provider=llm_provider)
    items = [
        {"item_no": "001", "upc": VALID_UPC},
        {"item_no": "002", "upc": VALID_UPC},
        {"item_no": "003", "upc": INVALID_UPC},
    ]
    result = asyncio.run(agent.execute({"items": items}))
    assert len(result.data["items"]) == 3
    assert len(result.data["issues"]) == 1
    assert result.data["issues"][0]["item_no"] == "003"
    assert result.needs_hitl is True


def test_all_valid_upcs_no_hitl(llm_provider):
    agent = POParserAgent(llm_provider=llm_provider)
    items = [
        {"item_no": "001", "upc": VALID_UPC},
        {"item_no": "002", "upc": VALID_UPC},
    ]
    result = asyncio.run(agent.execute({"items": items}))
    assert result.needs_hitl is False
    assert result.success is True
    assert result.confidence == 0.90
