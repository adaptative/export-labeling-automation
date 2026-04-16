"""Tests for BundleGenerator (TASK-037 + TASK-053, Sprint-13)."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

from labelforge.services.bundle import bundle_storage_key, generate_bundle


# ── Fixtures ────────────────────────────────────────────────────────────────


_ORDER = {
    "id": "ORD-2026-0042",
    "po_number": "PO-88210",
    "importer_id": "IMP-ACME",
    "tenant_id": "tnt-nakoda-001",
}

_IMPORTER = {"id": "IMP-ACME", "name": "Acme Trading Co.", "code": "ACME"}


def _items():
    return [
        {"item_no": "A1001", "description": "Mug 11oz", "upc": "012345678905"},
        {"item_no": "A1002", "description": "Mug 15oz", "upc": "012345678912"},
    ]


def _composed():
    return {
        "A1001": {
            "die_cut_svg": '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>',
            "provenance": {"content_hash": "sha256:svg1", "profile_version": 3},
        },
        "A1002": {
            "die_cut_svg": '<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"/>',
            "provenance": {"content_hash": "sha256:svg2", "profile_version": 3},
        },
    }


def _run_date():
    return datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)


def _unzip(zip_bytes: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


# ── Structure ───────────────────────────────────────────────────────────────


def test_bundle_is_valid_zip_with_manifest():
    pdf = b"%PDF-1.4\n% fake approval pdf"
    zip_bytes, prov = generate_bundle(
        order=_ORDER,
        items=_items(),
        composed_artifacts=_composed(),
        approval_pdf_bytes=pdf,
        approval_pdf_provenance={"artifact_type": "approval_pdf",
                                  "content_hash": "sha256:pdf1"},
        importer=_IMPORTER,
        run_date=_run_date(),
    )
    files = _unzip(zip_bytes)
    assert "manifest.json" in files
    assert any(n.endswith("_approval.pdf") for n in files)
    assert sum(1 for n in files if n.endswith("_diecut.svg")) == 2
    assert prov["artifact_type"] == "bundle_zip"
    assert prov["mime_type"] == "application/zip"
    assert prov["size_bytes"] == len(zip_bytes)


def test_naming_uses_importer_code_and_po():
    zip_bytes, _ = generate_bundle(
        order=_ORDER,
        items=_items(),
        composed_artifacts=_composed(),
        approval_pdf_bytes=b"%PDF-1.4\nx",
        importer=_IMPORTER,
    )
    names = list(_unzip(zip_bytes).keys())
    assert "ACME_PO-88210_approval.pdf" in names
    assert "ACME_PO-88210_A1001_diecut.svg" in names
    assert "ACME_PO-88210_A1002_diecut.svg" in names


def test_manifest_lists_all_files_with_hashes():
    pdf = b"%PDF-1.4\nfake pdf body"
    zip_bytes, _ = generate_bundle(
        order=_ORDER,
        items=_items(),
        composed_artifacts=_composed(),
        approval_pdf_bytes=pdf,
        importer=_IMPORTER,
    )
    manifest = json.loads(_unzip(zip_bytes)["manifest.json"])
    assert manifest["schema_version"] == 1
    # 1 approval PDF + 2 SVGs = 3 file entries (manifest itself isn't listed).
    assert len(manifest["files"]) == 3
    # Each file entry must carry a sha256 hash that matches the blob.
    archive = _unzip(zip_bytes)
    for entry in manifest["files"]:
        raw = archive[entry["name"]]
        assert entry["content_hash"] == f"sha256:{hashlib.sha256(raw).hexdigest()}"
        assert entry["size_bytes"] == len(raw)


# ── Reproducibility ─────────────────────────────────────────────────────────


def test_identical_inputs_produce_identical_bytes():
    pdf = b"%PDF-1.4\nfixed"
    a, _ = generate_bundle(
        order=_ORDER, items=_items(),
        composed_artifacts=_composed(),
        approval_pdf_bytes=pdf, importer=_IMPORTER,
        run_date=_run_date(),
    )
    b, _ = generate_bundle(
        order=_ORDER, items=_items(),
        composed_artifacts=_composed(),
        approval_pdf_bytes=pdf, importer=_IMPORTER,
        run_date=_run_date(),
    )
    assert a == b
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


def test_content_hash_in_provenance_matches_body():
    zip_bytes, prov = generate_bundle(
        order=_ORDER, items=_items()[:1],
        composed_artifacts=_composed(),
        approval_pdf_bytes=b"%PDF-1.4\n", importer=_IMPORTER,
    )
    assert prov["content_hash"] == f"sha256:{hashlib.sha256(zip_bytes).hexdigest()}"


# ── Edge cases ──────────────────────────────────────────────────────────────


def test_extra_files_included_with_safe_names():
    zip_bytes, _ = generate_bundle(
        order=_ORDER, items=[], importer=_IMPORTER,
        extra_files={"../evil name.bin": b"data", "cut.dxf": b"DXF"},
    )
    names = set(_unzip(zip_bytes).keys())
    # Path-traversal attempt is sanitized, no `..` appears.
    assert not any(".." in n for n in names)
    assert any(n.endswith("cut.dxf") for n in names)


def test_missing_svg_items_skipped_without_crash():
    """Items without a composed SVG are silently skipped."""
    zip_bytes, prov = generate_bundle(
        order=_ORDER, items=_items(),
        composed_artifacts={"A1001": {"die_cut_svg": "<svg/>", "provenance": {}}},
        importer=_IMPORTER,
    )
    names = list(_unzip(zip_bytes).keys())
    # Only A1001 has an SVG.
    assert sum(1 for n in names if n.endswith("_diecut.svg")) == 1
    # Manifest `items` still lists both to preserve order context.
    manifest = json.loads(_unzip(zip_bytes)["manifest.json"])
    assert len(manifest["items"]) == 2


def test_fallback_importer_code_when_unknown():
    zip_bytes, _ = generate_bundle(
        order={"id": "o1", "po_number": "po1"},
        items=_items()[:1],
        composed_artifacts=_composed(),
    )
    names = list(_unzip(zip_bytes).keys())
    # Importer code defaults to `unknown`.
    assert any("unknown_po1" in n for n in names)


def test_manifest_written_last_in_zip():
    """Ensures the manifest can truthfully reference every prior file."""
    pdf = b"%PDF-1.4\nxx"
    zip_bytes, _ = generate_bundle(
        order=_ORDER, items=_items()[:1],
        composed_artifacts=_composed(),
        approval_pdf_bytes=pdf, importer=_IMPORTER,
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert zf.namelist()[-1] == "manifest.json"


def test_empty_bundle_is_still_valid():
    zip_bytes, prov = generate_bundle(
        order=_ORDER, items=[], importer=_IMPORTER,
    )
    files = _unzip(zip_bytes)
    # Only manifest should be present.
    assert list(files.keys()) == ["manifest.json"]
    assert prov["size_bytes"] > 0


def test_bundle_storage_key_format():
    assert bundle_storage_key(
        tenant_id="tnt-1", order_id="ORD-42",
    ) == "tnt-1/bundles/ORD-42/bundle.zip"


def test_bundle_storage_key_sanitizes_segments():
    key = bundle_storage_key(
        tenant_id="../t", order_id="../bad/id",
    )
    assert ".." not in key
    assert key.startswith("_t/bundles/") or key.startswith("t/bundles/")
