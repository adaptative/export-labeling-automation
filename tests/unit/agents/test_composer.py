"""Tests for Composer Agent (TASK-034, Sprint-12)."""
import asyncio
import hashlib
import xml.etree.ElementTree as ET

from labelforge.agents.composer import ComposerAgent, SVG_NS


def _fused(item_no="1", **kwargs):
    base = {
        "item_no": item_no,
        "upc": "012345678905",
        "description": "Ceramic Mug 11oz",
        "case_qty": "24",
        "total_qty": 480,
        "total_cartons": 20,
        "box_L": 12.5, "box_W": 10.0, "box_H": 8.5,
        "net_weight": 0.75,
        "country_of_origin": "IN",
        "confidence": 0.95,
    }
    base.update(kwargs)
    return base


def _profile(**kwargs):
    base = {
        "importer_id": "IMP-ACME-001",
        "name": "Acme Trading Co",
        "version": 2,
        "panel_layouts": {
            "carton_top": ["logo", "upc", "item_description"],
            "carton_side": ["warnings", "country_of_origin"],
        },
        "handling_symbol_rules": {"fragile": True, "this_side_up": True},
        "brand_treatment": {"company_name": "Acme"},
        "logo_asset_hash": "sha256:abc123",
    }
    base.update(kwargs)
    return base


def _report(warnings=None):
    return {
        "item_no": "1",
        "verdicts": [],
        "applicable_warnings": warnings or ["California Proposition 65"],
        "passed": True,
    }


# ── SVG validity ────────────────────────────────────────────────────────────


def test_produces_valid_svg():
    agent = ComposerAgent()
    result = asyncio.run(agent.execute({
        "fused_item": _fused(),
        "importer_profile": _profile(),
        "compliance_report": _report(),
    }))
    assert result.success is True
    svg = result.data["die_cut_svg"]
    # Parses without error
    root = ET.fromstring(svg)
    assert root.tag == f"{{{SVG_NS}}}svg"
    # Has the item_no attribute baked in
    assert root.attrib["data-item-no"] == "1"


def test_deterministic_output_same_hash():
    """Same input → byte-identical SVG → same content hash."""
    agent = ComposerAgent()
    kwargs = dict(fused_item=_fused(), importer_profile=_profile(), compliance_report=_report())
    r1 = asyncio.run(agent.execute(kwargs))
    r2 = asyncio.run(agent.execute(kwargs))
    # Strip the only non-deterministic field (provenance.created_at).
    assert r1.data["die_cut_svg"] == r2.data["die_cut_svg"]
    h1 = hashlib.sha256(r1.data["die_cut_svg"].encode()).hexdigest()
    h2 = hashlib.sha256(r2.data["die_cut_svg"].encode()).hexdigest()
    assert h1 == h2


# ── Label placement ─────────────────────────────────────────────────────────


def test_warning_labels_placed():
    agent = ComposerAgent()
    result = asyncio.run(agent.execute({
        "fused_item": _fused(),
        "importer_profile": _profile(),
        "compliance_report": _report(warnings=["FRAGILE", "THIS SIDE UP"]),
    }))
    placements = result.data["placements"]
    warning_placements = [p for p in placements if p["type"] == "warning"]
    # Expect both compliance warning + handling_symbol_rules symbols.
    symbols = {p["symbol"] for p in warning_placements}
    assert "FRAGILE" in symbols
    assert "fragile" in symbols or "FRAGILE" in symbols


def test_warnings_rendered_on_every_panel():
    """After DieCut-Review F12 the composer uses a fixed L-W-L-W panel
    layout and warnings appear on every panel rather than being scoped
    to a single named slot."""
    agent = ComposerAgent()
    result = asyncio.run(agent.execute({
        "fused_item": _fused(),
        "importer_profile": _profile(),
        "compliance_report": _report(warnings=["Prop 65", "Non-Food Use"]),
    }))
    warning_panels = {p["panel"] for p in result.data["placements"] if p["type"] == "warning"}
    assert warning_panels == {"long_front", "short_right", "long_back", "short_left"}


# ── Drawing insertion ──────────────────────────────────────────────────────


def test_line_drawing_inserted():
    agent = ComposerAgent()
    drawing = '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="5" cy="5" r="2"/></svg>'
    profile = _profile(panel_layouts={"carton_top": ["logo", "line_drawing"]})
    result = asyncio.run(agent.execute({
        "fused_item": _fused(),
        "importer_profile": profile,
        "compliance_report": _report(),
        "line_drawing_svg": drawing,
    }))
    svg = result.data["die_cut_svg"]
    assert "line-drawing" in svg
    assert "<circle" in svg


def test_malformed_drawing_does_not_crash():
    agent = ComposerAgent()
    profile = _profile(panel_layouts={"carton_top": ["line_drawing"]})
    result = asyncio.run(agent.execute({
        "fused_item": _fused(),
        "importer_profile": profile,
        "compliance_report": _report(),
        "line_drawing_svg": "<not-svg><broken",
    }))
    # Should complete and produce an otherwise valid SVG.
    assert result.success is True
    ET.fromstring(result.data["die_cut_svg"])


# ── Text fields ─────────────────────────────────────────────────────────────


def test_text_fields_filled():
    agent = ComposerAgent()
    result = asyncio.run(agent.execute({
        "fused_item": _fused(description="Ceramic Mug 11oz", country_of_origin="IN"),
        "importer_profile": _profile(),
        "compliance_report": _report(),
    }))
    svg = result.data["die_cut_svg"]
    assert "Ceramic Mug 11oz" in svg
    assert "Made in IN" in svg
    # UPC caption
    assert "012345678905" in svg


def test_quantity_field_renders():
    agent = ComposerAgent()
    profile = _profile(panel_layouts={"carton_top": ["quantity"]})
    result = asyncio.run(agent.execute({
        "fused_item": _fused(case_qty="24"),
        "importer_profile": profile,
        "compliance_report": _report(),
    }))
    # The long-panel info block now uses the importer-standard
    # "CASE QTY : <N> PCS" phrasing — the legacy "Qty: N" shorthand was
    # dropped because it duplicated the CASE QTY line and confused reviewers.
    svg = result.data["die_cut_svg"]
    assert "CASE QTY : 24 PCS" in svg
    assert "Qty: 24" not in svg


def test_dimensions_field_renders():
    agent = ComposerAgent()
    profile = _profile(panel_layouts={"carton_top": ["dimensions"]})
    result = asyncio.run(agent.execute({
        "fused_item": _fused(),
        "importer_profile": profile,
        "compliance_report": _report(),
    }))
    # The long-panel info block now emits a single "DIMENSIONS : ..." line
    # with inch units; the older "Box: L x W x H" shorthand was dropped
    # because it duplicated DIMENSIONS and used mixed units.
    svg = result.data["die_cut_svg"]
    assert 'DIMENSIONS : 12.5"L x 10"W x 8.5"H' in svg
    assert "Box: 12.5 x 10.0 x 8.5" not in svg


# ── Provenance ──────────────────────────────────────────────────────────────


def test_provenance_tracked():
    agent = ComposerAgent()
    result = asyncio.run(agent.execute({
        "fused_item": _fused(),
        "importer_profile": _profile(version=7),
        "compliance_report": _report(),
    }))
    prov = result.data["provenance"]
    assert prov["artifact_type"] == "die_cut_svg"
    assert prov["content_hash"].startswith("sha256:")
    # Hash matches the actual SVG bytes.
    svg_hash = hashlib.sha256(result.data["die_cut_svg"].encode()).hexdigest()
    assert prov["content_hash"] == f"sha256:{svg_hash}"
    # Frozen inputs captured.
    assert prov["frozen_inputs"]["profile_version"] == 7
    assert prov["frozen_inputs"]["asset_hashes"]["logo"] == "sha256:abc123"


# ── Error handling ──────────────────────────────────────────────────────────


def test_missing_item_no_fails_to_hitl():
    agent = ComposerAgent()
    result = asyncio.run(agent.execute({
        "fused_item": {"description": "no item_no"},
        "importer_profile": _profile(),
        "compliance_report": _report(),
    }))
    assert result.success is False
    assert result.needs_hitl is True


def test_panel_layout_is_always_four_panels():
    """After DieCut-Review F2 the composer no longer forwards the
    profile's named panels to the canvas — it always emits the spec's
    four-panel LONG-SHORT-LONG-SHORT carton. The profile's
    ``panel_layouts`` contribute to the validator's required-fields set
    but not to panel count."""
    agent = ComposerAgent()
    profile = _profile(panel_layouts={
        "carton_top": {"selected": True, "fields": ["upc", "item_description"]},
        "carton_back": {"selected": False, "fields": ["logo"]},
    })
    result = asyncio.run(agent.execute({
        "fused_item": _fused(),
        "importer_profile": profile,
        "compliance_report": _report(),
    }))
    placements = result.data["placements"]
    assert {p["panel"] for p in placements} == {
        "long_front", "short_right", "long_back", "short_left",
    }
