"""Tests for ApprovalPDFGenerator (TASK-036, Sprint-13)."""
from __future__ import annotations

from datetime import datetime, timezone

from labelforge.services.approval_pdf import generate_approval_pdf


# ── Fixtures ────────────────────────────────────────────────────────────────


def _order():
    return {
        "id": "ORD-2026-0042",
        "po_number": "PO-88210",
        "importer_id": "IMP-ACME",
        "tenant_id": "tnt-nakoda-001",
        "external_ref": "ACME-ER-4021",
    }


def _items():
    return [
        {
            "item_no": "A1001",
            "description": "Ceramic Mug 11oz Blue",
            "upc": "012345678905",
            "country_of_origin": "IN",
            "case_qty": 24, "total_qty": 240,
            "box_L": 30, "box_W": 20, "box_H": 15,
            "net_weight": 0.35, "weight_unit": "kg",
        },
        {
            "item_no": "A1002",
            "description": "Ceramic Mug 11oz Red",
            "upc": "012345678912",
            "country_of_origin": "IN",
        },
    ]


def _composed_artifacts():
    return {
        "A1001": {
            "die_cut_svg": (
                '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="60">'
                '<rect x="1" y="1" width="98" height="58" fill="none" stroke="black"/>'
                '</svg>'
            ),
            "provenance": {
                "content_hash": "sha256:abc1234567890def",
                "artifact_type": "die_cut_svg",
                "frozen_inputs": {"profile_version": 3},
            },
        },
    }


# ── Happy path ──────────────────────────────────────────────────────────────


def test_generates_pdf_bytes_and_provenance():
    pdf, prov = generate_approval_pdf(
        order=_order(),
        items=_items(),
        composed_artifacts=_composed_artifacts(),
        importer={"id": "IMP-ACME", "name": "Acme Trading Co.", "code": "ACME"},
        reviewer="ops@nakoda",
        run_date=datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert isinstance(pdf, bytes)
    # Any PDF must start with the %PDF- header.
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000  # cover + 2 item pages → non-trivial size
    assert prov["artifact_type"] == "approval_pdf"
    assert prov["content_hash"].startswith("sha256:")
    assert prov["size_bytes"] == len(pdf)
    assert prov["mime_type"] == "application/pdf"
    assert prov["frozen_inputs"]["item_count"] == 2
    assert prov["frozen_inputs"]["po_number"] == "PO-88210"


def test_minimal_inputs_still_produces_pdf():
    """Works with the bare minimum — no composed artifacts, no importer."""
    pdf, prov = generate_approval_pdf(
        order={"id": "ORD-X", "po_number": "PO-X"},
        items=[{"item_no": "1", "description": "Test"}],
    )
    assert pdf.startswith(b"%PDF-")
    assert prov["frozen_inputs"]["item_count"] == 1


def test_no_items_still_renders_cover():
    pdf, prov = generate_approval_pdf(
        order={"id": "ORD-EMPTY", "po_number": "PO-EMPTY"},
        items=[],
    )
    assert pdf.startswith(b"%PDF-")
    assert prov["frozen_inputs"]["item_count"] == 0


# ── Provenance integrity ────────────────────────────────────────────────────


def test_provenance_records_per_item_hashes():
    pdf, prov = generate_approval_pdf(
        order=_order(),
        items=_items(),
        composed_artifacts=_composed_artifacts(),
    )
    hashes = prov["frozen_inputs"]["item_hashes"]
    assert "A1001" in hashes
    assert hashes["A1001"] == "sha256:abc1234567890def"
    # Items without composed artifacts surface as None (no crash).
    assert hashes["A1002"] is None


def test_content_hash_is_sha256_of_body():
    import hashlib
    pdf, prov = generate_approval_pdf(
        order=_order(),
        items=_items()[:1],
        run_date=datetime(2026, 4, 15, tzinfo=timezone.utc),
    )
    expected = f"sha256:{hashlib.sha256(pdf).hexdigest()}"
    assert prov["content_hash"] == expected


# ── Resilience ──────────────────────────────────────────────────────────────


def test_malformed_svg_falls_back_to_placeholder():
    """A broken SVG must not crash PDF generation."""
    bad = {"A1001": {"die_cut_svg": "<not really svg", "provenance": {}}}
    pdf, prov = generate_approval_pdf(
        order=_order(),
        items=_items()[:1],
        composed_artifacts=bad,
    )
    assert pdf.startswith(b"%PDF-")
    assert prov["size_bytes"] > 0


def test_runs_without_svglib_installed(monkeypatch):
    """If svglib isn't importable, we still produce a PDF with a placeholder."""
    import sys
    monkeypatch.setitem(sys.modules, "svglib", None)
    monkeypatch.setitem(sys.modules, "svglib.svglib", None)
    pdf, _ = generate_approval_pdf(
        order=_order(),
        items=_items()[:1],
        composed_artifacts=_composed_artifacts(),
    )
    assert pdf.startswith(b"%PDF-")


def test_handles_missing_item_fields():
    """Item dicts with missing common fields shouldn't blow up."""
    pdf, _ = generate_approval_pdf(
        order={"id": "o"},
        items=[{"item_no": "x"}, {"description": "no item_no"}],
    )
    assert pdf.startswith(b"%PDF-")
