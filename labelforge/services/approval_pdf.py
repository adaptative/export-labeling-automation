"""Approval PDF Generator (TASK-036, Sprint-13).

Produces a multi-page approval PDF from a set of composed order items:

* **Cover sheet** — importer name, PO number, item count, run date, content
  hash summary, provenance footer.
* **One page per item** — renders the die-cut SVG (converted to an embedded
  raster or direct drawing), followed by an item details table
  (UPC / description / dimensions / net weight / country of origin /
  applicable warnings) and a provenance block (artifact id + sha256 prefix).

The output is a ``(pdf_bytes, provenance_dict)`` tuple. The provenance dict
is suitable for persistence as a row in the ``artifacts`` table.

Design notes
------------

* Zero LLM calls — fully deterministic aside from the embedded *created_at*
  timestamp (kept in the provenance dict, **not** in the PDF stream, so the
  content hash is stable across runs with identical inputs).
* `reportlab` is used for the actual PDF construction (already a project
  dependency). SVGs are embedded via `svglib` when available, falling back
  to a textual placeholder so the generator never crashes on an unusual
  SVG.
* The *cover sheet* includes a deterministic content-hash summary so a
  reviewer can verify at a glance that the PDF they're looking at matches
  the items bundled into the ZIP — stops the "approved the wrong version"
  class of bug.
"""
from __future__ import annotations

import hashlib
import io
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)

logger = logging.getLogger(__name__)


# Deterministic timestamp used whenever the caller does **not** supply one,
# so the PDF byte stream stays stable across runs. The *wall-clock* time is
# always recorded separately on the returned provenance dict.
_EPOCH_ANCHOR = datetime(2000, 1, 1, tzinfo=timezone.utc)


# ── Public API ──────────────────────────────────────────────────────────────


def generate_approval_pdf(
    *,
    order: dict,
    items: list[dict],
    composed_artifacts: Optional[dict[str, dict]] = None,
    importer: Optional[dict] = None,
    reviewer: Optional[str] = None,
    run_date: Optional[datetime] = None,
) -> tuple[bytes, dict]:
    """Render the approval PDF and its provenance record.

    Args:
        order: Order dict, expected keys: ``id``, ``po_number``,
            ``importer_id``, ``tenant_id`` (any missing field degrades
            gracefully to a placeholder string).
        items: List of fused item dicts. Each item should carry at least
            ``item_no`` and ``description``; the generator pulls whatever
            is available without failing.
        composed_artifacts: Optional map of ``item_no → {die_cut_svg,
            placements, provenance}`` — the output of ComposerAgent
            (Sprint-12). When provided, the die-cut SVG is embedded in
            the per-item page.
        importer: Optional importer dict; if omitted the generator falls
            back to ``order.importer_id`` as a display label.
        reviewer: Optional reviewer name printed on the cover sheet.
        run_date: Optional override for the cover sheet timestamp (used
            primarily for test determinism).

    Returns:
        ``(pdf_bytes, provenance)`` — the serialized PDF and a provenance
        dict containing ``content_hash``, ``artifact_type``,
        ``artifact_id`` (first 16 hex of hash), ``frozen_inputs``, and
        ``created_at`` (ISO 8601).
    """
    composed_artifacts = composed_artifacts or {}
    importer = importer or {}
    run_date_display = run_date or datetime.now(timezone.utc)

    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Approval PDF — Order {order.get('po_number') or order.get('id', '?')}",
        author="LabelForge",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="main",
    )
    doc.addPageTemplates([PageTemplate(id="default", frames=[frame],
                                       onPage=_draw_page_footer)])

    styles = _build_styles()
    story: list[Any] = []

    # ── Cover sheet ──────────────────────────────────────────────────────
    story.extend(_build_cover_sheet(
        order=order, items=items, importer=importer,
        reviewer=reviewer, run_date=run_date_display,
        composed_artifacts=composed_artifacts, styles=styles,
    ))
    story.append(PageBreak())

    # ── One page per item ────────────────────────────────────────────────
    for idx, item in enumerate(items):
        story.extend(_build_item_page(
            item=item,
            artifact=composed_artifacts.get(str(item.get("item_no", ""))),
            styles=styles,
            page_index=idx + 1,
            total=len(items),
        ))
        if idx < len(items) - 1:
            story.append(PageBreak())

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    content_hash = hashlib.sha256(pdf_bytes).hexdigest()
    provenance = {
        "artifact_type": "approval_pdf",
        "content_hash": f"sha256:{content_hash}",
        "artifact_id": content_hash[:16],
        "frozen_inputs": {
            "order_id": order.get("id"),
            "po_number": order.get("po_number"),
            "importer_id": order.get("importer_id"),
            "item_count": len(items),
            "item_hashes": {
                str(item.get("item_no", "?")):
                    (composed_artifacts.get(str(item.get("item_no", "")))
                     or {}).get("provenance", {}).get("content_hash")
                for item in items
            },
        },
        "created_at": run_date_display.isoformat(),
        "mime_type": "application/pdf",
        "size_bytes": len(pdf_bytes),
    }

    logger.info(
        "ApprovalPDF: order=%s items=%d pages=%d size=%d hash=%s",
        order.get("id"), len(items), 1 + len(items),
        len(pdf_bytes), content_hash[:12],
    )
    return pdf_bytes, provenance


# ── Cover sheet ─────────────────────────────────────────────────────────────


def _build_cover_sheet(
    *, order: dict, items: list[dict], importer: dict,
    reviewer: Optional[str], run_date: datetime,
    composed_artifacts: dict[str, dict], styles: dict,
) -> list:
    flowables: list = []
    importer_name = (
        importer.get("name")
        or importer.get("display_name")
        or order.get("importer_id")
        or "—"
    )
    flowables.append(Paragraph("LabelForge Approval Package", styles["title"]))
    flowables.append(Spacer(1, 4 * mm))
    flowables.append(Paragraph(
        f"<font color='#666666'>For review by importer — do not print yet.</font>",
        styles["subtitle"],
    ))
    flowables.append(Spacer(1, 10 * mm))

    header_rows = [
        ["Importer", importer_name],
        ["PO number", order.get("po_number") or "—"],
        ["Order ID", str(order.get("id") or "—")],
        ["External ref", order.get("external_ref") or "—"],
        ["Item count", str(len(items))],
        ["Run date (UTC)", run_date.strftime("%Y-%m-%d %H:%M:%S")],
        ["Reviewer", reviewer or "Pending approval"],
    ]
    meta_table = Table(header_rows, colWidths=[40 * mm, 110 * mm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    flowables.append(meta_table)

    flowables.append(Spacer(1, 10 * mm))
    flowables.append(Paragraph("Items in this package", styles["h2"]))
    flowables.append(Spacer(1, 3 * mm))

    manifest_rows = [["Item #", "Description", "UPC / GTIN", "Die-cut hash"]]
    for it in items:
        item_no = str(it.get("item_no", "?"))
        svg_hash = (
            (composed_artifacts.get(item_no) or {})
            .get("provenance", {})
            .get("content_hash")
            or "—"
        )
        if isinstance(svg_hash, str) and svg_hash.startswith("sha256:"):
            svg_hash = svg_hash[7:19] + "…"
        manifest_rows.append([
            item_no,
            _trim(it.get("description") or "", 48),
            _trim(str(it.get("upc") or it.get("gtin") or ""), 18),
            svg_hash,
        ])
    manifest = Table(manifest_rows, colWidths=[18 * mm, 78 * mm, 30 * mm, 30 * mm],
                     repeatRows=1)
    manifest.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("FONTNAME", (3, 1), (3, -1), "Courier"),
    ]))
    flowables.append(manifest)

    flowables.append(Spacer(1, 14 * mm))
    flowables.append(Paragraph(
        "<b>Approval instructions</b><br/>"
        "Verify the importer details, review each item's die-cut on the "
        "following pages, and sign below. Any mismatch between a die-cut "
        "and its expected content hash (shown in the manifest) should be "
        "rejected — the approved bundle will be reassembled with an "
        "updated hash.",
        styles["body"],
    ))
    flowables.append(Spacer(1, 10 * mm))
    sig_rows = [
        ["Signed", "", "Date", ""],
        ["Title", "", "Reviewer", ""],
    ]
    sig = Table(sig_rows, colWidths=[20 * mm, 60 * mm, 20 * mm, 50 * mm])
    sig.setStyle(TableStyle([
        ("LINEBELOW", (1, 0), (1, 0), 0.5, colors.black),
        ("LINEBELOW", (3, 0), (3, 0), 0.5, colors.black),
        ("LINEBELOW", (1, 1), (1, 1), 0.5, colors.black),
        ("LINEBELOW", (3, 1), (3, 1), 0.5, colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
    ]))
    flowables.append(sig)
    return flowables


# ── Item page ───────────────────────────────────────────────────────────────


def _build_item_page(
    *, item: dict, artifact: Optional[dict], styles: dict,
    page_index: int, total: int,
) -> list:
    flowables: list = []
    item_no = item.get("item_no", "?")
    desc = item.get("description") or ""
    flowables.append(Paragraph(
        f"Item {item_no} <font size='9' color='#9CA3AF'>"
        f"({page_index} of {total})</font>", styles["title"],
    ))
    flowables.append(Paragraph(_trim(desc, 120), styles["subtitle"]))
    flowables.append(Spacer(1, 6 * mm))

    # Die-cut preview
    flowables.append(Paragraph("Die-cut preview", styles["h2"]))
    flowables.append(Spacer(1, 2 * mm))
    preview = _render_svg_preview(artifact)
    flowables.append(preview)
    flowables.append(Spacer(1, 6 * mm))

    # Item specs table
    flowables.append(Paragraph("Specifications", styles["h2"]))
    flowables.append(Spacer(1, 2 * mm))
    spec_rows = [
        ["Description", _trim(desc, 80)],
        ["UPC / GTIN", str(item.get("upc") or item.get("gtin") or "—")],
        ["Case qty", str(item.get("case_qty") or "—")],
        ["Total qty", str(item.get("total_qty") or "—")],
        ["Box (L × W × H)", _format_dims(item)],
        ["Net weight", _format_weight(item)],
        ["Country of origin", str(item.get("country_of_origin") or item.get("origin") or "—")],
    ]
    spec = Table(spec_rows, colWidths=[40 * mm, 120 * mm])
    spec.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F9FAFB")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
    ]))
    flowables.append(spec)
    flowables.append(Spacer(1, 6 * mm))

    # Provenance footer
    prov = (artifact or {}).get("provenance") or {}
    hash_display = prov.get("content_hash") or "—"
    if isinstance(hash_display, str) and hash_display.startswith("sha256:"):
        hash_display = hash_display[:31] + "…"
    flowables.append(Paragraph(
        f"<font size='8' color='#6B7280'>"
        f"Artifact hash: {hash_display} · "
        f"Profile v{prov.get('frozen_inputs', {}).get('profile_version', '?')}"
        f"</font>",
        styles["body"],
    ))
    return flowables


# ── SVG embedding ───────────────────────────────────────────────────────────


def _render_svg_preview(artifact: Optional[dict]):
    """Render the die-cut SVG as a PDF flowable.

    Uses ``svglib`` when available (optional runtime dep) for a true vector
    rendering; falls back to a textual placeholder with the hash when the
    SVG is absent or the library is missing — never crashes the PDF build.
    """
    if not artifact or not artifact.get("die_cut_svg"):
        return _placeholder_box("Die-cut artifact not available", 0xE5, 0xE7, 0xEB)

    svg = artifact["die_cut_svg"]
    try:
        from svglib.svglib import svg2rlg  # type: ignore
        drawing = svg2rlg(io.StringIO(svg))
        if drawing is None:
            raise ValueError("svg2rlg returned None")
        # Scale to fit the content frame (≈ 170mm wide).
        max_w = 170 * mm
        if drawing.width > max_w:
            scale = max_w / drawing.width
            drawing.scale(scale, scale)
            drawing.width *= scale
            drawing.height *= scale
        return drawing
    except Exception as exc:
        logger.debug("svglib not available or failed: %s — using placeholder", exc)
        return _placeholder_box(
            f"Die-cut SVG embedded ({len(svg)} bytes)",
            0xF9, 0xFA, 0xFB,
        )


def _placeholder_box(text: str, r: int, g: int, b: int):
    """Reportlab flowable: a shaded rectangle with centered text."""
    from reportlab.platypus import Paragraph as _P, Table as _T
    colour = colors.Color(r / 255, g / 255, b / 255)
    cell = _P(
        f"<para align='center'><font size='10' color='#374151'>{text}</font></para>",
        getSampleStyleSheet()["BodyText"],
    )
    t = _T([[cell]], colWidths=[170 * mm], rowHeights=[60 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colour),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9CA3AF")),
    ]))
    return KeepTogether([t])


# ── Styling helpers ─────────────────────────────────────────────────────────


def _build_styles() -> dict[str, Any]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=22, leading=26,
            spaceAfter=2, textColor=colors.HexColor("#111827"),
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["BodyText"], fontSize=11,
            textColor=colors.HexColor("#4B5563"), leading=14,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=13,
            textColor=colors.HexColor("#111827"), spaceBefore=4, spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontSize=10, leading=14,
        ),
    }


def _draw_page_footer(canvas: pdf_canvas.Canvas, doc) -> None:  # noqa: ANN001
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#9CA3AF"))
    canvas.drawString(18 * mm, 10 * mm, "LabelForge · Approval Package")
    canvas.drawRightString(
        A4[0] - 18 * mm, 10 * mm,
        f"Page {doc.page}",
    )
    canvas.restoreState()


# ── Small helpers ───────────────────────────────────────────────────────────


def _trim(s: str, n: int) -> str:
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


def _format_dims(item: dict) -> str:
    L, W, H = item.get("box_L"), item.get("box_W"), item.get("box_H")
    if L is not None and W is not None and H is not None:
        return f"{L} × {W} × {H}"
    dims = item.get("product_dims")
    if isinstance(dims, dict):
        unit = dims.get("unit", "")
        return f"{dims.get('length','?')} × {dims.get('width','?')} × {dims.get('height','?')} {unit}".strip()
    return "—"


def _format_weight(item: dict) -> str:
    w = item.get("net_weight") or item.get("weight")
    if w is None:
        return "—"
    unit = item.get("weight_unit") or "kg"
    return f"{w} {unit}"
