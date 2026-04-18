"""Regression tests for the die-cut Composer — F17 from the Die-Cut
Generation Review (T1–T7).

These tests guard the specification-compliant 4-panel die-cut layout
(§5.4.2 of the System Architecture Document). They exist so the class
of regression that produced a 2-panel HTML-mockup with a ``LOGO``
placeholder and a ``Dev-only alw`` warning can never ship again.
"""
from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET

import pytest

from labelforge.agents.composer import (
    ComposerAgent,
    CompositionError,
    PANEL_SEQUENCE,
    SVG_NS,
    _lint_no_placeholders,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


def _fused(**overrides):
    base = {
        "item_no": "18236-01",
        "po_number": "PO-2026-0001",
        "upc": "677478725232",
        "description": '15X12" PAPER MACHE VASE WITH HANDLES, TAUPE',
        "case_qty": "2",
        "total_qty": 600,
        "total_cartons": 300,
        "box_L": 26.5,
        "box_W": 13.5,
        "box_H": 17.0,
        "gross_weight_lbs": 8.5,
        "cube_cuft": 3.52,
        "country_of_origin": "INDIA",
    }
    base.update(overrides)
    return base


def _profile(**overrides):
    base = {
        "importer_id": "IMP-SBH",
        "name": "Sagebrook Home",
        "version": 3,
        "brand_treatment": {"company_name": "Sagebrook Home"},
        "panel_layouts": {
            # Real extracted shape — Composer treats this as pure metadata;
            # the 4-panel L-W-L-W structure is fixed by the spec.
            "item_prop65_warning_label_for_furniture": ["warning"],
            "fragile_warning": ["warning"],
        },
        "handling_symbol_rules": {
            "fragile": True,
            "this_side_up": True,
            "keep_dry": True,
        },
        "logo_asset_hash": "sha256:demo",
    }
    base.update(overrides)
    return base


def _report(**overrides):
    base = {
        "item_no": "18236-01",
        "applicable_warnings": [
            "Prop 65",
            "Non-Food Use",
        ],
        "passed": True,
    }
    base.update(overrides)
    return base


def _compose(**kwargs):
    agent = ComposerAgent()
    result = asyncio.run(agent.execute({
        "fused_item": kwargs.get("fused") or _fused(),
        "importer_profile": kwargs.get("profile") or _profile(),
        "compliance_report": kwargs.get("report") or _report(),
        "line_drawing_svg": kwargs.get("line_drawing"),
    }))
    assert result.success, result.data
    return result


# ── T1 — golden-ish structural equality ────────────────────────────────────


def test_T1_structural_invariant_seed_order():
    """T1 proxy — for a fixed seed order we assert the structural
    fingerprint (panel count, fold lines, canvas mm) rather than full
    byte equality so the test isn't tied to font-size micro-tweaks."""
    result = _compose()
    root = ET.fromstring(result.data["die_cut_svg"])
    assert root.tag == f"{{{SVG_NS}}}svg"

    # mm canvas dimensions match the fused_item times MM_PER_IN.
    assert root.attrib["width"] == "2032.0mm"   # (2 * 26.5 + 2 * 13.5) × 25.4
    assert root.attrib["height"] == "558.8mm"   # (2.5 + 17 + 2.5) × 25.4
    assert root.attrib["data-item-no"] == "18236-01"
    assert root.attrib["data-panel-count"] == "4"


# ── T2 — panel-count invariant ─────────────────────────────────────────────


def test_T2_panel_count_and_fold_lines():
    result = _compose()
    root = ET.fromstring(result.data["die_cut_svg"])
    panels = root.findall(f".//{{{SVG_NS}}}g[@class='carton-panel']")
    assert len(panels) == 4

    # 4 panels in LONG-SHORT-LONG-SHORT order.
    kinds = [p.attrib["data-panel-kind"] for p in panels]
    assert kinds == ["LONG", "SHORT", "LONG", "SHORT"]

    # 3 vertical fold lines (x1 == x2, x > 0).
    folds = root.findall(f".//{{{SVG_NS}}}line[@class='fold-line']")
    verticals = [f for f in folds if f.attrib["x1"] == f.attrib["x2"]]
    horizontals = [f for f in folds if f.attrib["y1"] == f.attrib["y2"]]
    assert len(verticals) == 3, f"expected 3 vertical folds, got {len(verticals)}"
    assert len(horizontals) == 2, f"expected 2 horizontal folds, got {len(horizontals)}"


# ── T3 — field presence on every panel ────────────────────────────────────


def test_T3_required_fields_on_every_panel():
    result = _compose()
    root = ET.fromstring(result.data["die_cut_svg"])
    panels = root.findall(f".//{{{SVG_NS}}}g[@class='carton-panel']")
    assert len(panels) == 4
    for panel in panels:
        panel_text = ET.tostring(panel, encoding="unicode").lower()
        assert "item no." in panel_text, panel.attrib["data-panel"]
        assert "case qty" in panel_text, panel.attrib["data-panel"]
        assert "made in" in panel_text or "india" in panel_text, panel.attrib["data-panel"]

    # At least one handling symbol rendered on every panel.
    for panel in panels:
        symbols = panel.findall(f".//{{{SVG_NS}}}g[@class='handling-symbol']")
        assert len(symbols) >= 1, f"handling symbols missing on {panel.attrib['data-panel']}"


# ── T4 — mm units on canvas ───────────────────────────────────────────────


def test_T4_canvas_width_ends_in_mm():
    result = _compose()
    root = ET.fromstring(result.data["die_cut_svg"])
    assert root.attrib["width"].endswith("mm")
    assert root.attrib["height"].endswith("mm")


# ── T5 — no placeholder strings ───────────────────────────────────────────


def test_T5_no_placeholder_strings():
    result = _compose()
    svg = result.data["die_cut_svg"]
    # The lint function would have raised if anything matched; double-check here.
    for needle in (r"\bLOGO\b", r"\bTODO\b", r"\bPLACEHOLDER\b", r"Dev-only"):
        assert re.search(needle, svg) is None, f"leaked: {needle}"


def test_T5_lint_catches_leaked_placeholder():
    """Sanity check on the lint function itself."""
    good = '<svg xmlns="http://www.w3.org/2000/svg"><g class="brand">Acme</g></svg>'
    _lint_no_placeholders(good)

    for bad in (
        '<svg><text>LOGO</text></svg>',
        '<svg><text>Dev-only preview</text></svg>',
        '<svg><text>TODO replace this</text></svg>',
    ):
        with pytest.raises(CompositionError):
            _lint_no_placeholders(bad)


# ── T6 — barcode on all 4 panels ──────────────────────────────────────────


def test_T6_barcode_on_every_panel():
    result = _compose()
    root = ET.fromstring(result.data["die_cut_svg"])
    barcodes = root.findall(f".//{{{SVG_NS}}}g[@class='barcode']")
    assert len(barcodes) == 4, f"expected 4 barcodes (one per panel), got {len(barcodes)}"


# ── T7 — no inline JPEG drawings ──────────────────────────────────────────


def test_T7_no_inline_jpeg_line_drawing():
    drawing = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<path d="M0 0 L10 10" stroke="#000"/></svg>'
    )
    result = _compose(line_drawing=drawing)
    svg = result.data["die_cut_svg"]
    # Positive: vector path survived embedding.
    assert '<path' in svg or 'ns0:path' in svg
    # Negative: no base64 JPEG leaked in.
    assert "data:image/jpeg" not in svg
    assert "data:image/png;base64" not in svg


# ── Extra spec checks ─────────────────────────────────────────────────────


def test_composer_raises_on_leaked_logo_placeholder():
    """If the profile has no brand info AND no fallback, Composer falls
    back to 'Importer' — never the literal string 'LOGO'."""
    result = _compose(profile=_profile(name="", code="", brand_treatment={}))
    svg = result.data["die_cut_svg"]
    # Lint passed → no LOGO leak; brand label became 'Importer'.
    assert "Importer" in svg


def test_panel_sequence_constant():
    assert PANEL_SEQUENCE == ("long_front", "short_right", "long_back", "short_left")


def test_info_blocks_differ_between_long_and_short():
    """LONG panels carry DESCRIPTION / DIMENSIONS; SHORT panels carry
    P.O NO. / CARTON NO. / WEIGHT / CUBE."""
    result = _compose()
    root = ET.fromstring(result.data["die_cut_svg"])
    long_panel = root.findall(f".//{{{SVG_NS}}}g[@data-panel-kind='LONG']")[0]
    short_panel = root.findall(f".//{{{SVG_NS}}}g[@data-panel-kind='SHORT']")[0]
    long_text = ET.tostring(long_panel, encoding="unicode").lower()
    short_text = ET.tostring(short_panel, encoding="unicode").lower()
    assert "description" in long_text
    assert "dimensions" in long_text
    assert "p.o no." in short_text
    assert "carton no." in short_text
    assert "carton weight" in short_text
    assert "cube" in short_text


def test_deterministic_output_same_hash():
    """Same input → byte-identical SVG (the created_at field lives on
    the provenance dict, not inside the artifact)."""
    agent = ComposerAgent()
    kwargs = dict(
        fused_item=_fused(),
        importer_profile=_profile(),
        compliance_report=_report(),
    )
    r1 = asyncio.run(agent.execute(kwargs))
    r2 = asyncio.run(agent.execute(kwargs))
    assert r1.data["die_cut_svg"] == r2.data["die_cut_svg"]


# ── F14 — metadata comment at SVG head ─────────────────────────────────────


def test_F14_metadata_comment_precedes_svg_root():
    result = _compose(
        fused=_fused(po_number="PO-2026-0001", pi_ref="PI-A"),
        profile=_profile(version=7),
        report={"applicable_warnings": ["Prop 65"], "rules_snapshot_id": "rs-2026-04"},
    )
    svg = result.data["die_cut_svg"]
    # Comment sits between the XML declaration and the <svg> root.
    assert "<!-- labelforge die-cut" in svg
    assert svg.index("<!--") < svg.index("<svg")
    # Contains the provenance-safe fields we advertise.
    for needle in ("item=18236-01", "po=PO-2026-0001", "pi=PI-A",
                   "profile_v=7", "rules_snapshot=rs-2026-04", "canvas="):
        assert needle in svg, f"missing {needle!r}"


def test_F14_metadata_comment_is_deterministic():
    """The metadata block must not embed timestamps — otherwise the
    SVG's content_hash would change on every compose, breaking dedup."""
    agent = ComposerAgent()
    kwargs = dict(
        fused_item=_fused(),
        importer_profile=_profile(),
        compliance_report=_report(),
    )
    r1 = asyncio.run(agent.execute(kwargs))
    r2 = asyncio.run(agent.execute(kwargs))
    assert r1.data["die_cut_svg"] == r2.data["die_cut_svg"]


# ── F11 — reject raster line drawings ──────────────────────────────────────


def test_F11_raster_line_drawing_rejected():
    raster = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<image xlink:href="data:image/jpeg;base64,AAAA" x="0" y="0" '
        'width="10" height="10"/></svg>'
    )
    agent = ComposerAgent()
    result = asyncio.run(agent.execute({
        "fused_item": _fused(),
        "importer_profile": _profile(),
        "compliance_report": _report(),
        "line_drawing_svg": raster,
    }))
    assert result.success is False
    assert result.needs_hitl is True
    assert "raster" in (result.hitl_reason or "").lower()


def test_F11_vector_line_drawing_accepted():
    drawing = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<path d="M0 0 L10 10 L20 0" stroke="#000" fill="none"/></svg>'
    )
    result = _compose(line_drawing=drawing)
    svg = result.data["die_cut_svg"]
    # Vector path round-trips into the embedded <g class="line-drawing">.
    assert '<path' in svg or 'ns0:path' in svg
    assert "data:image/jpeg" not in svg


# ── F11 — SHA cache on the product image processor ─────────────────────────


def test_F11_vectorize_cache_reuses_for_repeat_item():
    """Second processing of the same (item_no, image) pair hits the cache."""
    # Minimal 1x1 PNG — decodes under PIL.
    import base64
    from labelforge.agents.product_image_processor import (
        ProductImageProcessorAgent,
        vectorize_cache_clear,
        vectorize_cache_stats,
    )
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    vectorize_cache_clear()
    agent = ProductImageProcessorAgent()
    kwargs = {"item_no": "X-1", "images": [{"ref": "a.png", "data": tiny_png}]}
    r1 = asyncio.run(agent.execute(kwargs))
    assert r1.data["image_count"] == 1
    before = vectorize_cache_stats()["size"]
    r2 = asyncio.run(agent.execute(kwargs))
    after = vectorize_cache_stats()["size"]
    # Cache entry persisted; second run didn't grow the cache and returned
    # byte-identical SVG.
    assert before == after >= 1
    assert r1.data["images"][0]["svg"] == r2.data["images"][0]["svg"]


# ── F15 — text flatten mode ────────────────────────────────────────────────


def test_F15_flatten_text_annotates_textLength():
    profile = _profile()
    profile["flatten_text"] = True
    result = _compose(profile=profile)
    svg = result.data["die_cut_svg"]
    assert 'textLength="' in svg
    assert 'lengthAdjust="spacingAndGlyphs"' in svg
    assert 'data-flattened="1"' in svg


def test_F15_flatten_text_idempotent():
    """Running the pipeline twice shouldn't keep rewrapping text runs."""
    profile = _profile()
    profile["flatten_text"] = True
    r1 = _compose(profile=profile)
    r2 = _compose(profile=profile)
    assert r1.data["die_cut_svg"] == r2.data["die_cut_svg"]
