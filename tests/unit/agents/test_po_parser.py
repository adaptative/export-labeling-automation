"""Tests for PO Parser Agent (Agent 6.2) — AI-driven extraction and validation."""
import asyncio
import json
from labelforge.agents.po_parser import POParserAgent, validate_upc_luhn


# Known valid UPC-A: 012345678905
VALID_UPC = "012345678905"
INVALID_UPC = "012345678900"


# ── UPC Luhn validation ─────────────────────────────────────────────────────


def test_validate_upc_luhn_with_valid_upc():
    assert validate_upc_luhn(VALID_UPC) is True


def test_validate_upc_luhn_with_invalid_upc():
    assert validate_upc_luhn(INVALID_UPC) is False


def test_validate_upc_luhn_wrong_length():
    assert validate_upc_luhn("12345") is False


def test_validate_upc_luhn_non_digit():
    assert validate_upc_luhn("01234567890a") is False


# ── Structured mode — basic ─────────────────────────────────────────────────


def test_hitl_triggered_on_luhn_failure(llm_provider):
    agent = POParserAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "items": [{"item_no": "001", "upc": INVALID_UPC}],
    }))
    assert result.needs_hitl is True
    assert result.success is False
    assert result.confidence <= 0.60
    assert "UPC validation failures" in result.hitl_reason


def test_multi_item_parsing(llm_provider):
    agent = POParserAgent(llm_provider=llm_provider)
    items = [
        {"item_no": "001", "upc": VALID_UPC, "description": "A", "case_qty": "10", "total_qty": 100},
        {"item_no": "002", "upc": VALID_UPC, "description": "B", "case_qty": "10", "total_qty": 200},
        {"item_no": "003", "upc": INVALID_UPC, "description": "C", "case_qty": "5", "total_qty": 50},
    ]
    result = asyncio.run(agent.execute({"items": items}))
    assert len(result.data["items"]) == 3
    assert any("UPC Luhn" in i["issue"] for i in result.data["issues"])
    assert result.needs_hitl is True


def test_all_valid_upcs_no_hitl(llm_provider):
    agent = POParserAgent(llm_provider=llm_provider)
    items = [
        {"item_no": "001", "upc": VALID_UPC, "description": "A", "case_qty": "10", "total_qty": 100},
        {"item_no": "002", "upc": VALID_UPC, "description": "B", "case_qty": "5", "total_qty": 200},
    ]
    result = asyncio.run(agent.execute({"items": items}))
    assert result.needs_hitl is False
    assert result.success is True
    assert result.confidence >= 0.80


# ── Structured mode — field validations ─────────────────────────────────────


def test_structured_mode_validates_required_fields():
    agent = POParserAgent()
    result = asyncio.run(agent.execute({
        "items": [{"item_no": "001", "upc": VALID_UPC}],
    }))
    assert result.needs_hitl is True
    assert any("Missing required" in i["issue"] for i in result.data["issues"])


def test_dimension_extraction():
    agent = POParserAgent()
    items = [{
        "item_no": "001", "upc": VALID_UPC, "description": "Widget",
        "case_qty": "10", "total_qty": 100,
        "product_dims": {"length": 4.5, "width": 3.5, "height": 4.0, "unit": "in"},
    }]
    result = asyncio.run(agent.execute({"items": items}))
    assert result.data["items"][0]["product_dims"]["length"] == 4.5
    dim_issues = [i for i in result.data["issues"] if "dimension" in i.get("issue", "").lower()]
    assert len(dim_issues) == 0


def test_invalid_dimension_detected():
    agent = POParserAgent()
    items = [{
        "item_no": "001", "upc": VALID_UPC, "description": "Widget",
        "case_qty": "10", "total_qty": 100,
        "product_dims": {"length": "abc", "width": 3.5, "height": 4.0},
    }]
    result = asyncio.run(agent.execute({"items": items}))
    dim_issues = [i for i in result.data["issues"] if "dimension" in i.get("issue", "").lower()]
    assert len(dim_issues) == 1


def test_weight_extraction():
    agent = POParserAgent()
    items = [{
        "item_no": "001", "upc": VALID_UPC, "description": "Widget",
        "case_qty": "10", "total_qty": 100, "net_weight": 0.75,
    }]
    result = asyncio.run(agent.execute({"items": items}))
    weight_issues = [i for i in result.data["issues"] if "weight" in i.get("issue", "").lower()]
    assert len(weight_issues) == 0


def test_negative_weight_detected():
    agent = POParserAgent()
    items = [{
        "item_no": "001", "upc": VALID_UPC, "description": "Widget",
        "case_qty": "10", "total_qty": 100, "net_weight": -1.0,
    }]
    result = asyncio.run(agent.execute({"items": items}))
    weight_issues = [i for i in result.data["issues"] if "weight" in i.get("issue", "").lower()]
    assert len(weight_issues) == 1


def test_image_refs_preserved():
    agent = POParserAgent()
    items = [{
        "item_no": "001", "upc": VALID_UPC, "description": "Widget",
        "case_qty": "10", "total_qty": 100,
        "product_image_refs": ["s3://bucket/img1.jpg", "s3://bucket/img2.jpg"],
    }]
    result = asyncio.run(agent.execute({"items": items}))
    assert result.data["items"][0]["product_image_refs"] == ["s3://bucket/img1.jpg", "s3://bucket/img2.jpg"]


def test_per_item_confidence():
    agent = POParserAgent()
    full_item = {
        "item_no": "001", "upc": VALID_UPC, "description": "Widget",
        "case_qty": "10", "total_qty": 100,
        "product_dims": {"length": 4.5}, "net_weight": 0.75,
        "product_image_refs": ["s3://img.jpg"],
    }
    sparse_item = {"item_no": "002", "upc": VALID_UPC}
    result = asyncio.run(agent.execute({"items": [full_item, sparse_item]}))
    items = result.data["items"]
    assert items[0]["confidence"] > items[1]["confidence"]


def test_empty_items_returns_zero_confidence():
    agent = POParserAgent()
    result = asyncio.run(agent.execute({"items": []}))
    assert result.confidence == 0.0
    assert result.data["items"] == []


# ── Raw text mode ────────────────────────────────────────────────────────────


def test_raw_text_mode_uses_llm(llm_provider):
    agent = POParserAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "document_content": "PO Number: 12345\nItem 1: Widget\nUPC: 012345678905",
    }))
    # StubLLMProvider returns "PURCHASE_ORDER" which isn't valid JSON,
    # so extraction will fail gracefully
    assert result.data["items"] == []
    assert result.confidence == 0.0


def test_raw_text_llm_extracts_items(llm_provider_factory):
    """LLM returns valid JSON → items are extracted and validated."""
    llm = llm_provider_factory(default_content=json.dumps([
        {"item_no": "001", "upc": VALID_UPC, "description": "Paper Mache Vase",
         "case_qty": "10", "total_qty": 500},
    ]))
    agent = POParserAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "document_content": "PO#25364 Item 001 Paper Mache Vase UPC:012345678905 Qty:500",
    }))
    assert len(result.data["items"]) == 1
    assert result.data["items"][0]["item_no"] == "001"
    assert result.success is True


def test_multi_page_concatenation(llm_provider):
    agent = POParserAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "pages": ["Page 1 content", "Page 2 content", "Page 3 content"],
    }))
    assert result.data["page_count"] == 3


def test_no_llm_raw_text_returns_empty():
    """Without LLM, raw text mode returns empty items gracefully."""
    agent = POParserAgent()
    result = asyncio.run(agent.execute({
        "document_content": "Some PO text...",
    }))
    assert result.data["items"] == []
    assert result.success is True


# ── LLM validation & enrichment ─────────────────────────────────────────────


def test_llm_enriches_material_and_category(llm_provider_factory):
    """LLM infers material and category from description."""
    enrichment = {
        "validated_items": [{
            "item_no": "001",
            "enrichments": {
                "inferred_material": "Paper Mache",
                "inferred_category": "Decorative Vase",
                "suggested_upc": None,
                "description_quality": "good",
            },
            "confidence": 0.95,
            "notes": [],
        }],
        "cross_item_issues": [],
    }
    llm = llm_provider_factory(default_content=json.dumps(enrichment))
    agent = POParserAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "items": [{
            "item_no": "001", "upc": VALID_UPC,
            "description": "15X12 Paper Mache Vase w/ Handles, Taupe",
            "case_qty": "10", "total_qty": 300,
        }],
    }))
    item = result.data["items"][0]
    assert item["material"] == "Paper Mache"
    assert item["category"] == "Decorative Vase"


def test_llm_suggests_upc_correction(llm_provider_factory):
    """LLM suggests corrected UPC when Luhn check fails."""
    enrichment = {
        "validated_items": [{
            "item_no": "001",
            "enrichments": {
                "inferred_material": None,
                "inferred_category": None,
                "suggested_upc": VALID_UPC,
                "description_quality": "fair",
            },
            "confidence": 0.70,
            "notes": ["UPC appears to have a transposed digit"],
        }],
        "cross_item_issues": [],
    }
    llm = llm_provider_factory(default_content=json.dumps(enrichment))
    agent = POParserAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "items": [{
            "item_no": "001", "upc": INVALID_UPC,
            "description": "Widget", "case_qty": "5", "total_qty": 100,
        }],
    }))
    item = result.data["items"][0]
    assert item["suggested_upc"] == VALID_UPC
    assert any("LLM suggests corrected UPC" in i["issue"] for i in result.data["issues"])
    assert item.get("llm_notes") == ["UPC appears to have a transposed digit"]


def test_llm_blends_confidence(llm_provider_factory):
    """Confidence is blended: 60% deterministic + 40% LLM."""
    enrichment = {
        "validated_items": [{
            "item_no": "001",
            "enrichments": {
                "inferred_material": None, "inferred_category": None,
                "suggested_upc": None, "description_quality": "good",
            },
            "confidence": 1.0,
            "notes": [],
        }],
        "cross_item_issues": [],
    }
    llm = llm_provider_factory(default_content=json.dumps(enrichment))
    agent = POParserAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "items": [{
            "item_no": "001", "upc": VALID_UPC,
            "description": "Widget", "case_qty": "10", "total_qty": 100,
        }],
    }))
    item = result.data["items"][0]
    # Deterministic confidence = 0.9 (all required present, no optionals)
    # Blended = 0.9 * 0.6 + 1.0 * 0.4 = 0.54 + 0.40 = 0.94
    assert item["confidence"] == 0.94


def test_llm_cross_item_issues(llm_provider_factory):
    """LLM detects cross-item issues (e.g., duplicate item_nos)."""
    enrichment = {
        "validated_items": [],
        "cross_item_issues": ["Items 001 and 002 have very similar descriptions — possible duplicate"],
    }
    llm = llm_provider_factory(default_content=json.dumps(enrichment))
    agent = POParserAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "items": [
            {"item_no": "001", "upc": VALID_UPC, "description": "Vase", "case_qty": "10", "total_qty": 100},
            {"item_no": "002", "upc": VALID_UPC, "description": "Vase", "case_qty": "10", "total_qty": 100},
        ],
    }))
    cross = [i for i in result.data["issues"] if i.get("source") == "llm"]
    assert len(cross) == 1
    assert "duplicate" in cross[0]["issue"].lower()


def test_llm_enrichment_graceful_failure(llm_provider):
    """When LLM returns non-JSON, enrichment fails gracefully."""
    agent = POParserAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "items": [{
            "item_no": "001", "upc": VALID_UPC,
            "description": "Widget", "case_qty": "10", "total_qty": 100,
        }],
    }))
    # Should still work — just no enrichment applied
    assert result.success is True
    assert len(result.data["items"]) == 1
    assert result.data["items"][0].get("material") is None


def test_no_llm_no_enrichment():
    """Without LLM provider, no enrichment is attempted."""
    agent = POParserAgent()
    result = asyncio.run(agent.execute({
        "items": [{
            "item_no": "001", "upc": VALID_UPC,
            "description": "Paper Mache Bowl", "case_qty": "10", "total_qty": 200,
        }],
    }))
    assert result.success is True
    item = result.data["items"][0]
    assert item.get("material") is None
    assert item.get("category") is None


def test_cost_tracks_llm_calls(llm_provider_factory):
    """Cost accumulates from both extraction and enrichment LLM calls."""
    llm = llm_provider_factory(default_content=json.dumps({
        "validated_items": [], "cross_item_issues": [],
    }), cost=0.005)
    agent = POParserAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "items": [{
            "item_no": "001", "upc": VALID_UPC,
            "description": "Widget", "case_qty": "10", "total_qty": 100,
        }],
    }))
    assert result.cost > 0  # enrichment call was made


# ── Page count ───────────────────────────────────────────────────────────────


def test_structured_mode_page_count_is_1():
    agent = POParserAgent()
    result = asyncio.run(agent.execute({
        "items": [{"item_no": "001", "upc": VALID_UPC, "description": "A", "case_qty": "1", "total_qty": 1}],
    }))
    assert result.data["page_count"] == 1
