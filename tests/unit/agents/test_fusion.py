"""Tests for Fusion Agent (Agent 6.7) — AI-driven fusion and validation."""
import asyncio
import json
from labelforge.agents.fusion import FusionAgent, DIMENSION_TOLERANCE


def _make_po_item(item_no, product_dims=None, upc="012345678905", **kwargs):
    item = {"item_no": item_no, "description": f"Item {item_no}", "upc": upc}
    if product_dims:
        item["product_dims"] = product_dims
    item.update(kwargs)
    return item


def _make_pi_item(item_no, box_L=10.0, box_W=8.0, box_H=6.0, total_cartons=20):
    return {"item_no": item_no, "box_L": box_L, "box_W": box_W, "box_H": box_H,
            "total_cartons": total_cartons}


# ── Deterministic join ───────────────────────────────────────────────────────


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


# ── Deterministic dimension checks ──────────────────────────────────────────


def test_dimension_fit_check_with_tolerance():
    """Product dim exactly at box + tolerance should pass."""
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001", product_dims={"length": 10.5, "width": 7.0, "height": 5.0})],
        "pi_items": [_make_pi_item("001", box_L=10.0, box_W=8.0, box_H=6.0)],
    }))
    dim_issues = [i for i in result.data["issues"] if i.get("field") in ("length", "width", "height")]
    assert len(dim_issues) == 0


def test_dimension_fit_check_exceeds_tolerance():
    """Product dim exceeding box + tolerance should trigger critical issue."""
    agent = FusionAgent()
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
        "pi_items": [],
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


# ── Deterministic validations ────────────────────────────────────────────────


def test_upc_luhn_revalidation():
    """Invalid UPC in PO item generates warning issue (not critical)."""
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001", upc="111111111111")],
        "pi_items": [_make_pi_item("001")],
    }))
    upc_issues = [i for i in result.data["issues"] if i["field"] == "upc"]
    assert len(upc_issues) == 1
    assert upc_issues[0]["severity"] == "warning"
    assert result.needs_hitl is False


def test_weight_plausibility_pass():
    """Reasonable weight produces no issue."""
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001", net_weight=0.5, case_qty="10")],
        "pi_items": [_make_pi_item("001")],
    }))
    weight_issues = [i for i in result.data["issues"] if i["field"] == "net_weight"]
    assert len(weight_issues) == 0


def test_weight_plausibility_fail():
    """Extreme weight per carton triggers warning."""
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001", net_weight=10.0, case_qty="100")],
        "pi_items": [_make_pi_item("001")],
    }))
    weight_issues = [i for i in result.data["issues"] if i["field"] == "net_weight"]
    assert len(weight_issues) == 1
    assert weight_issues[0]["severity"] == "warning"


def test_confidence_degrades_with_warnings():
    """Each warning reduces confidence by 0.05."""
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [
            _make_po_item("001", upc="111111111111"),
            _make_po_item("002", upc="222222222222"),
        ],
        "pi_items": [_make_pi_item("001"), _make_pi_item("002")],
    }))
    assert result.confidence < 0.95
    assert result.confidence == 0.85


def test_po_pi_values_in_issues():
    """Issues include po_value and pi_value strings."""
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001", product_dims={"length": 20, "width": 5, "height": 5})],
        "pi_items": [_make_pi_item("001", box_L=10.0)],
    }))
    dim_issues = [i for i in result.data["issues"] if i["field"] == "length"]
    assert len(dim_issues) == 1
    assert dim_issues[0]["po_value"] == "20"
    assert dim_issues[0]["pi_value"] == "10.0"


# ── LLM material inference ──────────────────────────────────────────────────


def test_material_inference_with_llm(llm_provider_factory):
    """When LLM provided, material inference is attempted."""
    llm = llm_provider_factory(default_content='{"material": "Ceramic", "finish": "Glossy"}')
    agent = FusionAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001")],
        "pi_items": [_make_pi_item("001")],
    }))
    fused = result.data["fused_items"]
    assert fused[0].get("material") == "Ceramic"
    assert fused[0].get("finish") == "Glossy"


def test_material_inference_without_llm():
    """When no LLM, material is not set and no error occurs."""
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001")],
        "pi_items": [_make_pi_item("001")],
    }))
    fused = result.data["fused_items"]
    assert fused[0].get("material") is None


# ── LLM mismatch resolution ─────────────────────────────────────────────────


def test_llm_mismatch_resolution_adds_suggestions(llm_provider_factory):
    """LLM suggests resolutions for issues and adds hitl_question."""
    resolution = {
        "resolutions": [{
            "item_no": "001",
            "field": "item_no",
            "suggested_value": None,
            "resolution_confidence": 0.3,
            "reasoning": "Item 001 exists in PI but not in PO — likely a new item added to the shipment",
            "hitl_question": "Item 001 appears in the PI but not the PO. Was this item added after the PO was issued?",
        }],
        "overall_assessment": "One item mismatch found — PI has item not in PO",
        "recommended_action": "review",
    }
    llm = llm_provider_factory(default_content=json.dumps(resolution))
    agent = FusionAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "po_items": [],
        "pi_items": [_make_pi_item("001")],
    }))
    issues = result.data["issues"]
    missing_issue = [i for i in issues if i["message"] == "Missing from PO"][0]
    assert missing_issue.get("hitl_question") is not None
    assert "PI" in missing_issue["hitl_question"]
    assert missing_issue.get("reasoning") is not None


def test_llm_resolution_auto_applies_high_confidence_warning(llm_provider_factory):
    """High-confidence (>=0.9) LLM resolution auto-applies for non-critical issues."""
    resolution = {
        "resolutions": [{
            "item_no": "001",
            "field": "upc",
            "suggested_value": "012345678905",
            "resolution_confidence": 0.95,
            "reasoning": "Common transposition error in UPC digit",
            "hitl_question": "The UPC appears to have a typo. Should it be 012345678905?",
        }],
        "overall_assessment": "Minor UPC issue, auto-correctable",
        "recommended_action": "proceed",
    }
    llm = llm_provider_factory(default_content=json.dumps(resolution))
    agent = FusionAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001", upc="111111111111")],
        "pi_items": [_make_pi_item("001")],
    }))
    # The UPC warning issue should be auto-resolved
    upc_issues = [i for i in result.data["issues"] if i["field"] == "upc"]
    assert upc_issues[0].get("auto_resolved") is True
    # Fused item should have the corrected UPC
    assert result.data["fused_items"][0]["upc"] == "012345678905"


def test_llm_resolution_does_not_auto_apply_critical(llm_provider_factory):
    """Critical issues are NEVER auto-resolved, even with high confidence."""
    resolution = {
        "resolutions": [{
            "item_no": "001",
            "field": "item_no",
            "suggested_value": "001-A",
            "resolution_confidence": 0.95,
            "reasoning": "Likely item_no format mismatch between PO and PI",
            "hitl_question": "Item 001 is missing from PI. Could it be listed under a different code?",
        }],
        "overall_assessment": "Critical mismatch requires human review",
        "recommended_action": "block",
    }
    llm = llm_provider_factory(default_content=json.dumps(resolution))
    agent = FusionAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001")],
        "pi_items": [],
    }))
    # Critical issue should NOT be auto-resolved
    issues = result.data["issues"]
    critical = [i for i in issues if i["severity"] == "critical"]
    assert critical[0].get("auto_resolved") is not True
    assert result.needs_hitl is True


def test_llm_resolution_stores_assessment(llm_provider_factory):
    """LLM overall_assessment is stored in fusion metadata."""
    resolution = {
        "resolutions": [{
            "item_no": "001",
            "field": "upc",
            "suggested_value": None,
            "resolution_confidence": 0.5,
            "reasoning": "UPC check digit is wrong",
            "hitl_question": "Please verify the UPC for item 001",
        }],
        "overall_assessment": "One minor UPC issue detected",
        "recommended_action": "review",
    }
    llm = llm_provider_factory(default_content=json.dumps(resolution))
    agent = FusionAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001", upc="111111111111")],
        "pi_items": [_make_pi_item("001")],
    }))
    fused = result.data["fused_items"][0]
    assert fused["_fusion_metadata"]["llm_assessment"] == "One minor UPC issue detected"


# ── LLM cross-validation ────────────────────────────────────────────────────


def test_llm_cross_validation_detects_anomalies(llm_provider_factory):
    """LLM detects description-dimension mismatch and other anomalies."""
    cv_result = {
        "anomalies": [{
            "item_no": "001",
            "field": "product_dims",
            "observation": "A 'mug' is unlikely to be 24x18x12 inches — dimensions seem like carton dims, not product dims",
            "severity": "warning",
            "suggested_action": "Verify whether product_dims are actually carton outer dimensions",
        }],
    }
    llm = llm_provider_factory(default_content=json.dumps(cv_result))
    agent = FusionAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001", product_dims={"length": 24, "width": 18, "height": 12})],
        "pi_items": [_make_pi_item("001", box_L=24, box_W=18, box_H=12)],
    }))
    cv_issues = [i for i in result.data["issues"] if i.get("source") == "llm_cross_validation"]
    assert len(cv_issues) == 1
    assert cv_issues[0]["severity"] == "warning"
    assert "mug" in cv_issues[0]["message"].lower() or "dimension" in cv_issues[0]["message"].lower()


def test_llm_cross_validation_no_anomalies(llm_provider_factory):
    """No anomalies → no extra issues added."""
    llm = llm_provider_factory(default_content=json.dumps({"anomalies": []}))
    agent = FusionAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001")],
        "pi_items": [_make_pi_item("001")],
    }))
    cv_issues = [i for i in result.data["issues"] if i.get("source") == "llm_cross_validation"]
    assert len(cv_issues) == 0


# ── Graceful LLM failures ───────────────────────────────────────────────────


def test_llm_mismatch_resolution_graceful_failure(llm_provider):
    """Non-JSON LLM response for resolution doesn't break execution."""
    agent = FusionAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001")],
        "pi_items": [],
    }))
    # Should still detect the missing PI issue
    assert result.success is False
    assert result.needs_hitl is True
    issues = result.data["issues"]
    assert any(i["message"] == "Missing from PI" for i in issues)


def test_llm_cross_validation_graceful_failure(llm_provider):
    """Non-JSON LLM response for cross-validation doesn't break execution."""
    agent = FusionAgent(llm_provider=llm_provider)
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001")],
        "pi_items": [_make_pi_item("001")],
    }))
    assert result.success is True
    assert len(result.data["fused_items"]) == 1


# ── Cost tracking ────────────────────────────────────────────────────────────


def test_cost_accumulates_from_all_llm_calls(llm_provider_factory):
    """Cost includes material inference + mismatch resolution + cross-validation."""
    llm = llm_provider_factory(
        default_content=json.dumps({"material": "Wood", "finish": "Natural"}),
        cost=0.005,
    )
    agent = FusionAgent(llm_provider=llm)
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001")],
        "pi_items": [_make_pi_item("001")],
    }))
    # material inference + cross-validation = at least 2 LLM calls
    assert result.cost > 0
    assert len(llm.calls) >= 2  # material + cross-validation (no resolution since no issues)
