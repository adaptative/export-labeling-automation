"""Composer v2 reference-generator path — when the fused item carries
item_no + description + upc + box dimensions, the Composer delegates
to :mod:`labelforge.agents.diecut_reference` which matches the
approval-PDF layout the operator signs off on (title banner, 4-panel
LONG-SHORT-LONG-SHORT, real Sagebrook logo, handling-symbol icons,
UPC-A barcode, red dimension callouts, MADE IN INDIA, warnings).
"""
from __future__ import annotations

import pytest

from labelforge.agents.composer import ComposerAgent
from labelforge.agents.diecut_reference import (
    generate_diecut_for_payload,
    infer_drawing_key,
)


def _fused_with_upc(**overrides):
    base = {
        "item_no": "18236-08",
        "description": '15X12" PAPER MACHE VASE WITH HANDLES, TAUPE',
        "upc": "677478725232",
        "case_qty": 2,
        "total_qty": 600,
        "total_cartons": 300,
        "box_L": 26.5,
        "box_W": 13.5,
        "box_H": 17.0,
        "po_number": "ORD-2026-1AE7",
        "material": "paper mache",
        "finish": "taupe",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("desc,expected", [
    ("15X12 PAPER MACHE VASE WITH HANDLES, TAUPE", "vase_handles"),
    ("24 PAPER MACHE JUG WITH HANDLES, WHITE", "jug_handles"),
    ("S/3 14/18/22 PAPER MACHE BOWLS, TAUPE", "bowls_s3"),
    ("16 RECLAIMED WOOD RISER WITH HANDLE", "wood_riser"),
    ("12 FLUTED PAPER MACHE BOWL, BROWN", "fluted_bowl"),
    ("12X12 PAPER MACHE KNOBBY FOOTED BOWL", "knobby_bowl"),
    ("26X15 TALL PAPER MACHE HANDLE VASE, TAUPE", "tall_handle_vase"),
    ("mystery gadget", "vase_handles"),  # default fallback
])
def test_infer_drawing_key_maps_descriptions(desc, expected):
    assert infer_drawing_key(desc) == expected


def test_generate_diecut_for_payload_produces_v2_svg():
    svg = generate_diecut_for_payload(_fused_with_upc())
    # Reference-generator hallmarks:
    assert '<?xml version="1.0"' in svg
    assert 'width="2052.0mm"' in svg  # 2*26.5 + 2*13.5 = 80" + margins in mm
    # Title banner with red item-no + box dimensions:
    assert "18236-08" in svg
    assert "26.5 X 13.5 X 17.0 INCH" in svg
    # 4 panels worth of "MADE IN INDIA":
    assert svg.count("MADE IN INDIA") >= 4
    # Barcode digits are written below the bars on each panel:
    assert svg.count("677478725232") >= 2


@pytest.mark.asyncio
async def test_composer_agent_delegates_to_v2_when_inputs_complete():
    agent = ComposerAgent()
    result = await agent.execute({
        "fused_item": _fused_with_upc(),
        "importer_profile": {"name": "Sagebrook Home", "version": 4},
        "compliance_report": {},
    })
    assert result.success
    assert result.data["item_state"] == "COMPOSED"
    assert result.data["provenance"]["generator"] == "diecut_reference.v2"
    svg = result.data["die_cut_svg"]
    # v2 output has the red title banner + reference layout:
    assert "MADE IN INDIA" in svg
    assert "677478725232" in svg  # UPC rendered


@pytest.mark.asyncio
async def test_composer_agent_falls_back_to_legacy_without_upc():
    """No upc on the fused item → legacy _build_svg path, not v2."""
    agent = ComposerAgent()
    fused = _fused_with_upc()
    del fused["upc"]
    result = await agent.execute({
        "fused_item": fused,
        "importer_profile": {"name": "Sagebrook Home", "version": 4},
        "compliance_report": {},
    })
    assert result.success
    provenance = result.data.get("provenance") or {}
    assert provenance.get("generator") != "diecut_reference.v2"
