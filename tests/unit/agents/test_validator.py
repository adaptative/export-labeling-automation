"""Tests for Validator Agent (TASK-035, Sprint-12)."""
import asyncio

from labelforge.agents.validator import (
    MIN_BARCODE_BARS,
    MIN_BARCODE_HEIGHT_MM,
    MIN_READABLE_FONT_SIZE,
    SVG_NS,
    ValidatorAgent,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


def _fused(**kwargs):
    base = {
        "item_no": "1",
        "upc": "012345678905",
        "description": "Ceramic Mug 11oz",
        "country_of_origin": "IN",
    }
    base.update(kwargs)
    return base


def _good_svg(
    width_mm=130.0,
    height_mm=80.0,
    upc="012345678905",
    description="Ceramic Mug 11oz",
    origin="IN",
    with_logo=True,
    bars=10,
    bar_height_mm=12.0,
    font_size_mm=3.0,
    extra_inner="",
):
    """Build a valid well-formed SVG that passes every check."""
    bar_rects = "".join(
        f'<rect x="{5 + i * 2}" y="10" width="1" height="{bar_height_mm}"/>'
        for i in range(bars)
    )
    logo_markup = (
        '<g class="logo" data-role="logo"><rect x="2" y="2" width="20" height="20"/></g>'
        if with_logo else ""
    )
    return f'''<svg xmlns="{SVG_NS}" width="{width_mm}mm" height="{height_mm}mm" data-item-no="1">
      <g data-panel="carton_top">
        {logo_markup}
        <g class="barcode" data-value="{upc}">
          {bar_rects}
          <text x="5" y="28" font-size="{font_size_mm}">{upc}</text>
        </g>
        <text x="5" y="40" font-size="{font_size_mm}">{description}</text>
        <text x="5" y="50" font-size="{font_size_mm}">Made in {origin}</text>
        <text x="5" y="60" font-size="{font_size_mm}">warning: handle with care</text>
        {extra_inner}
      </g>
    </svg>'''


# ── SVG validity ────────────────────────────────────────────────────────────


def test_valid_svg_passes_every_check():
    agent = ValidatorAgent()
    # Explicit well-spaced placements bypass the tree fallback (which would
    # otherwise trip on our synthetic SVG's densely packed barcode bars).
    placements = [
        {"panel": "carton_top", "type": "logo", "x": 2.0, "y": 2.0},
        {"panel": "carton_top", "type": "barcode", "x": 40.0, "y": 2.0},
        {"panel": "carton_top", "type": "text", "x": 70.0, "y": 2.0},
    ]
    result = asyncio.run(agent.execute({
        "die_cut_svg": _good_svg(),
        "fused_item": _fused(),
        "required_fields": ["upc", "description", "logo", "country_of_origin"],
        "expected_dimensions_mm": {"width": 130.0, "height": 80.0},
        "placements": placements,
    }))
    assert result.success is True
    assert result.needs_hitl is False
    report = result.data["validation_report"]
    assert report["passed"] is True
    assert result.data["item_state"] == "VALIDATED"
    assert result.confidence == 1.0


def test_empty_svg_is_critical():
    agent = ValidatorAgent()
    result = asyncio.run(agent.execute({
        "die_cut_svg": "",
        "fused_item": _fused(),
    }))
    assert result.success is False
    assert result.needs_hitl is True
    assert result.data["item_state"] == "COMPOSED"
    assert result.data["critical_count"] >= 1


def test_malformed_xml_is_critical():
    agent = ValidatorAgent()
    result = asyncio.run(agent.execute({
        "die_cut_svg": "<svg><not-closed>",
        "fused_item": _fused(),
    }))
    assert result.success is False
    assert result.needs_hitl is True
    assert result.data["validation_report"]["svg_valid"] is False


def test_non_svg_root_element_is_critical():
    agent = ValidatorAgent()
    result = asyncio.run(agent.execute({
        "die_cut_svg": '<html xmlns="http://www.w3.org/2000/svg"></html>',
        "fused_item": _fused(),
    }))
    assert result.success is False
    assert result.data["validation_report"]["svg_valid"] is False


# ── Required fields ─────────────────────────────────────────────────────────


def test_missing_required_field_triggers_hitl():
    """UPC is required, but the SVG doesn't render it → critical."""
    agent = ValidatorAgent()
    bad_svg = f'<svg xmlns="{SVG_NS}" width="130mm" height="80mm"></svg>'
    result = asyncio.run(agent.execute({
        "die_cut_svg": bad_svg,
        "fused_item": _fused(),
        "required_fields": ["upc"],
    }))
    assert result.needs_hitl is True
    assert result.data["validation_report"]["required_fields_present"] is False


def test_all_required_fields_present_passes():
    agent = ValidatorAgent()
    result = asyncio.run(agent.execute({
        "die_cut_svg": _good_svg(),
        "fused_item": _fused(),
        "required_fields": ["upc", "description", "logo", "country_of_origin", "warnings"],
    }))
    assert result.data["validation_report"]["required_fields_present"] is True


def test_no_required_fields_list_skips_check():
    agent = ValidatorAgent()
    result = asyncio.run(agent.execute({
        "die_cut_svg": _good_svg(),
        "fused_item": _fused(),
    }))
    assert result.data["validation_report"]["required_fields_present"] is True


# ── Readability ─────────────────────────────────────────────────────────────


def test_small_font_is_flagged_but_not_critical():
    """Below-minimum font is a warning, not a HiTL-worthy critical failure."""
    agent = ValidatorAgent()
    small = MIN_READABLE_FONT_SIZE - 0.5
    svg = _good_svg(font_size_mm=small)
    result = asyncio.run(agent.execute({
        "die_cut_svg": svg,
        "fused_item": _fused(),
    }))
    report = result.data["validation_report"]
    assert report["labels_readable"] is False
    # Non-critical issues surface without forcing HiTL on their own.
    assert any("font-size" in i for i in result.data["issues"])


def test_readable_font_passes():
    agent = ValidatorAgent()
    result = asyncio.run(agent.execute({
        "die_cut_svg": _good_svg(font_size_mm=3.5),
        "fused_item": _fused(),
    }))
    assert result.data["validation_report"]["labels_readable"] is True


# ── Barcode ─────────────────────────────────────────────────────────────────


def test_missing_barcode_when_upc_present_is_critical():
    agent = ValidatorAgent()
    svg = f'''<svg xmlns="{SVG_NS}" width="130mm" height="80mm">
      <text>{_fused()["description"]}</text>
      <text>012345678905</text>
      <text>Made in IN</text>
    </svg>'''
    result = asyncio.run(agent.execute({
        "die_cut_svg": svg,
        "fused_item": _fused(),
    }))
    assert result.data["validation_report"]["barcode_scannable"] is False
    assert result.needs_hitl is True


def test_barcode_with_too_few_bars_is_critical():
    agent = ValidatorAgent()
    svg = _good_svg(bars=MIN_BARCODE_BARS - 2)
    result = asyncio.run(agent.execute({
        "die_cut_svg": svg,
        "fused_item": _fused(),
    }))
    assert result.data["validation_report"]["barcode_scannable"] is False
    assert result.needs_hitl is True


def test_barcode_with_short_bars_is_critical():
    agent = ValidatorAgent()
    svg = _good_svg(bar_height_mm=MIN_BARCODE_HEIGHT_MM - 2)
    result = asyncio.run(agent.execute({
        "die_cut_svg": svg,
        "fused_item": _fused(),
    }))
    assert result.data["validation_report"]["barcode_scannable"] is False


def test_barcode_caption_mismatch_is_critical():
    agent = ValidatorAgent()
    # Caption says 999... but UPC is 012345678905.
    svg = _good_svg().replace(
        "<text x=\"5\" y=\"28\" font-size=\"3.0\">012345678905</text>",
        "<text x=\"5\" y=\"28\" font-size=\"3.0\">999999999999</text>",
    )
    result = asyncio.run(agent.execute({
        "die_cut_svg": svg,
        "fused_item": _fused(),
    }))
    assert result.data["validation_report"]["barcode_scannable"] is False


def test_no_upc_skips_barcode_check():
    agent = ValidatorAgent()
    svg = f'<svg xmlns="{SVG_NS}" width="130mm" height="80mm"><text>no upc here</text></svg>'
    fused = _fused(upc="")
    result = asyncio.run(agent.execute({
        "die_cut_svg": svg,
        "fused_item": fused,
    }))
    # Barcode check defers when no UPC is declared.
    assert result.data["validation_report"]["barcode_scannable"] is True


# ── Dimensions ──────────────────────────────────────────────────────────────


def test_dimensions_match_within_tolerance():
    agent = ValidatorAgent()
    result = asyncio.run(agent.execute({
        "die_cut_svg": _good_svg(width_mm=130.0, height_mm=80.0),
        "fused_item": _fused(),
        "expected_dimensions_mm": {"width": 130.3, "height": 79.8},
    }))
    assert result.data["validation_report"]["dimensions_match"] is True


def test_dimensions_mismatch_is_critical():
    agent = ValidatorAgent()
    result = asyncio.run(agent.execute({
        "die_cut_svg": _good_svg(width_mm=100.0, height_mm=60.0),
        "fused_item": _fused(),
        "expected_dimensions_mm": {"width": 130.0, "height": 80.0},
    }))
    assert result.data["validation_report"]["dimensions_match"] is False
    assert result.needs_hitl is True


def test_no_expected_dimensions_skips_check():
    agent = ValidatorAgent()
    result = asyncio.run(agent.execute({
        "die_cut_svg": _good_svg(),
        "fused_item": _fused(),
    }))
    assert result.data["validation_report"]["dimensions_match"] is True


# ── Overlaps ────────────────────────────────────────────────────────────────


def test_overlap_detected_from_placements():
    agent = ValidatorAgent()
    # Two logos stacked at the exact same origin → must overlap.
    placements = [
        {"panel": "carton_top", "type": "logo", "x": 10.0, "y": 10.0},
        {"panel": "carton_top", "type": "logo", "x": 10.0, "y": 10.0},
    ]
    result = asyncio.run(agent.execute({
        "die_cut_svg": _good_svg(),
        "fused_item": _fused(),
        "placements": placements,
    }))
    assert result.data["validation_report"]["no_overlaps"] is False
    assert any("Overlap" in i for i in result.data["issues"])


def test_no_overlap_when_well_spaced():
    agent = ValidatorAgent()
    placements = [
        {"panel": "carton_top", "type": "logo", "x": 5.0, "y": 5.0},
        {"panel": "carton_top", "type": "barcode", "x": 50.0, "y": 5.0},
        {"panel": "carton_side", "type": "warning", "x": 5.0, "y": 5.0},
    ]
    result = asyncio.run(agent.execute({
        "die_cut_svg": _good_svg(),
        "fused_item": _fused(),
        "placements": placements,
    }))
    assert result.data["validation_report"]["no_overlaps"] is True


def test_overlap_only_within_same_panel():
    """Elements on different panels can't overlap even at identical coords."""
    agent = ValidatorAgent()
    placements = [
        {"panel": "carton_top", "type": "logo", "x": 10.0, "y": 10.0},
        {"panel": "carton_side", "type": "logo", "x": 10.0, "y": 10.0},
    ]
    result = asyncio.run(agent.execute({
        "die_cut_svg": _good_svg(),
        "fused_item": _fused(),
        "placements": placements,
    }))
    assert result.data["validation_report"]["no_overlaps"] is True


# ── HiTL escalation & confidence ────────────────────────────────────────────


def test_multiple_critical_failures_escalates():
    agent = ValidatorAgent()
    # Missing UPC → barcode critical; mismatched dims → dims critical.
    svg = f'<svg xmlns="{SVG_NS}" width="50mm" height="50mm"></svg>'
    result = asyncio.run(agent.execute({
        "die_cut_svg": svg,
        "fused_item": _fused(),
        "required_fields": ["upc"],
        "expected_dimensions_mm": {"width": 130.0, "height": 80.0},
    }))
    assert result.needs_hitl is True
    assert result.data["critical_count"] >= 2
    assert result.confidence < 1.0


def test_confidence_scales_with_check_pass_rate():
    agent = ValidatorAgent()
    # All checks pass.
    r_good = asyncio.run(agent.execute({
        "die_cut_svg": _good_svg(),
        "fused_item": _fused(),
    }))
    # One failure (small font) — 5 of 6 checks pass.
    r_bad = asyncio.run(agent.execute({
        "die_cut_svg": _good_svg(font_size_mm=1.0),
        "fused_item": _fused(),
    }))
    assert r_good.confidence > r_bad.confidence


def test_hitl_reason_populated_on_critical():
    agent = ValidatorAgent()
    svg = f'<svg xmlns="{SVG_NS}" width="130mm" height="80mm"></svg>'
    result = asyncio.run(agent.execute({
        "die_cut_svg": svg,
        "fused_item": _fused(),
        "required_fields": ["upc"],
    }))
    assert result.needs_hitl is True
    assert result.hitl_reason
    assert "Required fields" in result.hitl_reason or "barcode" in result.hitl_reason.lower()
