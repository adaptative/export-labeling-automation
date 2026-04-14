"""Tests for Fusion Agent (Agent 6.7) — rewritten with correct validation."""
import asyncio
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


# ── Join by item_no (backward compat) ───────────────────────────────────────


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


# ── New validations ──────────────────────────────────────────────────────────


def test_upc_luhn_revalidation():
    """Invalid UPC in PO item generates warning issue (not critical)."""
    agent = FusionAgent()
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001", upc="111111111111")],  # invalid Luhn
        "pi_items": [_make_pi_item("001")],
    }))
    upc_issues = [i for i in result.data["issues"] if i["field"] == "upc"]
    assert len(upc_issues) == 1
    assert upc_issues[0]["severity"] == "warning"
    # Warning only — should NOT trigger HiTL
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
        "po_items": [_make_po_item("001", net_weight=10.0, case_qty="100")],  # 1000kg per carton!
        "pi_items": [_make_pi_item("001")],
    }))
    weight_issues = [i for i in result.data["issues"] if i["field"] == "net_weight"]
    assert len(weight_issues) == 1
    assert weight_issues[0]["severity"] == "warning"


def test_material_inference_with_llm(llm_provider_factory):
    """When LLM provided, material inference is attempted."""
    # StubLLMProvider returns "PURCHASE_ORDER" which isn't valid JSON,
    # so material will be None (graceful failure)
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
    agent = FusionAgent()  # no llm
    result = asyncio.run(agent.execute({
        "po_items": [_make_po_item("001")],
        "pi_items": [_make_pi_item("001")],
    }))
    fused = result.data["fused_items"]
    assert fused[0].get("material") is None


def test_confidence_degrades_with_warnings():
    """Each warning reduces confidence by 0.05."""
    agent = FusionAgent()
    # Two items with invalid UPCs → 2 warnings
    result = asyncio.run(agent.execute({
        "po_items": [
            _make_po_item("001", upc="111111111111"),
            _make_po_item("002", upc="222222222222"),
        ],
        "pi_items": [_make_pi_item("001"), _make_pi_item("002")],
    }))
    assert result.confidence < 0.95
    assert result.confidence == 0.85  # 0.95 - 2*0.05


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
