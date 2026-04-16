"""Printer-Ready Bundle Generator (TASK-037 + TASK-053, Sprint-13).

Packages the full per-order deliverable: approval PDF, one die-cut SVG per
item, an optional line-drawing reference PDF, and a ``manifest.json`` that
records deterministic sha256 checksums plus full provenance for every file.
The result is a ZIP blob the printer can download directly from the bundle
endpoint or from a presigned S3 URL.

Naming convention follows TASK-037:

    {importer_code}_{po_number}_{item_no}_{type}.{ext}

with order-level files falling back to ``{importer_code}_{po_number}_*`` and
sensible defaults when a field is missing (``unknown`` placeholder) so the
bundle remains inspectable even for malformed inputs.

Design goals
------------

* **Deterministic content hash** — identical inputs produce identical ZIP
  bytes. ZipFile entries are written in sorted order with a fixed mtime
  (``_EPOCH_ANCHOR``) so sha256 matches across runs, which lets the
  ApprovalPDF manifest and the downstream printer scanner compare bundles
  to a known-good baseline.
* **Manifest-first** — the ``manifest.json`` is added *last* so it can
  reference every other file's sha256 hash. Reviewers verify the bundle by
  recomputing each hash and comparing against the manifest.
* **No LLM calls** — pure structural packaging. All content comes from the
  caller (already-rendered PDFs and SVGs) and from the approval PDF's own
  provenance dict.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Fixed mtime used for every ZipInfo entry to keep the ZIP's byte stream
# reproducible. The wall-clock time is always captured separately in the
# returned provenance dict so operational telemetry isn't lost.
_EPOCH_ANCHOR = (2000, 1, 1, 0, 0, 0)

_SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]+")


# ── Public API ──────────────────────────────────────────────────────────────


def generate_bundle(
    *,
    order: dict,
    items: list[dict],
    composed_artifacts: Optional[dict[str, dict]] = None,
    approval_pdf_bytes: Optional[bytes] = None,
    approval_pdf_provenance: Optional[dict] = None,
    line_drawing_pdf_bytes: Optional[bytes] = None,
    line_drawing_provenance: Optional[dict] = None,
    importer: Optional[dict] = None,
    extra_files: Optional[dict[str, bytes]] = None,
    run_date: Optional[datetime] = None,
) -> tuple[bytes, dict]:
    """Package every per-order artifact into a single reproducible ZIP.

    Args:
        order: Order dict (``id``, ``po_number``, ``importer_id`` …).
        items: Fused item dicts (``item_no``, ``description`` …).
        composed_artifacts: Optional map ``item_no → {die_cut_svg, provenance}``.
        approval_pdf_bytes: Pre-rendered approval PDF (from
            :func:`labelforge.services.approval_pdf.generate_approval_pdf`).
        approval_pdf_provenance: Provenance dict for the approval PDF.
        line_drawing_pdf_bytes: Optional pre-rendered line-drawing reference.
        line_drawing_provenance: Optional provenance dict for the line drawing.
        importer: Optional importer dict for the naming prefix
            (falls back to ``order.importer_id`` then ``"unknown"``).
        extra_files: Optional map of ``filename → bytes`` for anything not
            covered above (e.g. printer-specific cut files, Protocol PDFs).
        run_date: Optional override for the manifest's ``created_at``.

    Returns:
        ``(zip_bytes, manifest)`` — the serialized ZIP and a manifest dict
        suitable for persistence as an ``Artifact`` row. The manifest's
        ``content_hash`` is the sha256 of the ZIP body; individual file
        hashes live under ``files[].content_hash``.
    """
    composed_artifacts = composed_artifacts or {}
    importer = importer or {}
    extra_files = extra_files or {}
    run_date_display = run_date or datetime.now(timezone.utc)

    importer_code = _safe(
        importer.get("code")
        or importer.get("slug")
        or importer.get("name")
        or order.get("importer_id")
        or "unknown"
    )
    po_number = _safe(order.get("po_number") or order.get("external_ref") or order.get("id") or "unknown")

    # Collect (filename, content, provenance) tuples.  We stage them first
    # so the manifest can hash each entry before they're committed to the
    # ZIP body.
    entries: list[tuple[str, bytes, dict]] = []

    if approval_pdf_bytes:
        entries.append((
            f"{importer_code}_{po_number}_approval.pdf",
            approval_pdf_bytes,
            dict(approval_pdf_provenance or {"artifact_type": "approval_pdf"}),
        ))

    if line_drawing_pdf_bytes:
        entries.append((
            f"{importer_code}_{po_number}_line_drawing.pdf",
            line_drawing_pdf_bytes,
            dict(line_drawing_provenance or {"artifact_type": "line_drawing"}),
        ))

    for item in items:
        item_no = _safe(str(item.get("item_no", "?")))
        artifact = composed_artifacts.get(str(item.get("item_no", ""))) or {}
        svg = artifact.get("die_cut_svg")
        if not svg:
            continue
        svg_bytes = svg.encode("utf-8") if isinstance(svg, str) else bytes(svg)
        prov = dict(artifact.get("provenance") or {})
        prov.setdefault("artifact_type", "die_cut_svg")
        prov.setdefault("item_no", item.get("item_no"))
        entries.append((
            f"{importer_code}_{po_number}_{item_no}_diecut.svg",
            svg_bytes,
            prov,
        ))

    for name, data in extra_files.items():
        safe_name = _safe(name) or "extra.bin"
        entries.append((
            f"{importer_code}_{po_number}_{safe_name}",
            data,
            {"artifact_type": "extra", "source_filename": name},
        ))

    # Sort for reproducibility; the manifest will list files in this order.
    entries.sort(key=lambda e: e[0])

    manifest = _build_manifest(
        order=order, items=items, importer=importer, entries=entries,
        approval_pdf_provenance=approval_pdf_provenance,
        run_date=run_date_display, importer_code=importer_code,
        po_number=po_number,
    )
    manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")

    # ── Serialize the ZIP ───────────────────────────────────────────────
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for name, data, _prov in entries:
            info = zipfile.ZipInfo(filename=name, date_time=_EPOCH_ANCHOR)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
        # Manifest written LAST so every referenced hash is accurate.
        info = zipfile.ZipInfo(filename="manifest.json", date_time=_EPOCH_ANCHOR)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        zf.writestr(info, manifest_bytes)

    zip_bytes = buffer.getvalue()
    buffer.close()
    zip_hash = hashlib.sha256(zip_bytes).hexdigest()

    provenance = {
        "artifact_type": "bundle_zip",
        "content_hash": f"sha256:{zip_hash}",
        "artifact_id": zip_hash[:16],
        "frozen_inputs": {
            "order_id": order.get("id"),
            "po_number": order.get("po_number"),
            "importer_id": order.get("importer_id"),
            "importer_code": importer_code,
            "item_count": len(items),
            "file_count": len(entries) + 1,  # +1 for manifest
            "file_hashes": {name: _hash(data) for name, data, _ in entries}
                           | {"manifest.json": _hash(manifest_bytes)},
        },
        "created_at": run_date_display.isoformat(),
        "mime_type": "application/zip",
        "size_bytes": len(zip_bytes),
        "manifest": manifest,
    }

    logger.info(
        "Bundle: order=%s importer=%s files=%d size=%d hash=%s",
        order.get("id"), importer_code, len(entries) + 1,
        len(zip_bytes), zip_hash[:12],
    )
    return zip_bytes, provenance


# ── Storage helpers ─────────────────────────────────────────────────────────


def bundle_storage_key(
    *, tenant_id: str, order_id: str, filename: str = "bundle.zip",
) -> str:
    """Canonical S3 / blob key for a bundle: ``{tenant}/bundles/{order}/{name}``."""
    safe_tenant = _safe(tenant_id or "unknown")
    safe_order = _safe(order_id or "unknown")
    safe_name = _safe(filename or "bundle.zip") or "bundle.zip"
    return f"{safe_tenant}/bundles/{safe_order}/{safe_name}"


# ── Internal ────────────────────────────────────────────────────────────────


def _build_manifest(
    *, order: dict, items: list[dict], importer: dict,
    entries: list[tuple[str, bytes, dict]],
    approval_pdf_provenance: Optional[dict],
    run_date: datetime, importer_code: str, po_number: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generator": "labelforge.services.bundle",
        "created_at": run_date.isoformat(),
        "order": {
            "id": order.get("id"),
            "po_number": order.get("po_number"),
            "external_ref": order.get("external_ref"),
            "importer_id": order.get("importer_id"),
            "importer_code": importer_code,
            "item_count": len(items),
        },
        "importer": {
            "id": importer.get("id") or order.get("importer_id"),
            "code": importer_code,
            "name": importer.get("name"),
        },
        "files": [
            {
                "name": name,
                "size_bytes": len(data),
                "content_hash": _hash(data),
                "artifact_type": prov.get("artifact_type"),
                "item_no": prov.get("item_no"),
                "provenance": _minimal_prov(prov),
            }
            for name, data, prov in entries
        ],
        "items": [
            {
                "item_no": it.get("item_no"),
                "description": it.get("description"),
                "upc": it.get("upc") or it.get("gtin"),
            }
            for it in items
        ],
        "approval_pdf": _minimal_prov(approval_pdf_provenance or {}),
        "naming_convention": "{importer_code}_{po_number}_{item_no?}_{type}.{ext}",
    }


def _minimal_prov(prov: dict) -> dict:
    """Keep only the fields the printer/auditor needs — drops verbose nested
    provenance so the manifest stays small and stable."""
    if not prov:
        return {}
    keep = {
        "artifact_type", "content_hash", "artifact_id",
        "created_at", "size_bytes", "mime_type",
    }
    out = {k: v for k, v in prov.items() if k in keep}
    if "frozen_inputs" in prov:
        fi = prov["frozen_inputs"] or {}
        out["frozen_inputs"] = {
            k: fi.get(k) for k in (
                "profile_version", "rules_snapshot_id", "code_sha",
                "order_id", "po_number", "importer_id", "item_count",
            ) if k in fi
        }
    return out


def _hash(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _safe(s: Any) -> str:
    """Sanitize a token for use in a filename / S3 key — keeps filenames
    portable and prevents path traversal (``../``)."""
    if s is None:
        return ""
    text = str(s).strip()
    text = _SAFE_CHARS_RE.sub("_", text)
    text = text.strip("._-")
    return text or "unknown"
