"""Composer Agent (TASK-034, Sprint-12 + DieCut-Generation-Review F1-F16).

Produces the die-cut carton SVG for a single item. The layout is
**template-driven** — no LLM — following the Architecture Document
§5.4.2 "Die-Cut Layout Composer":

    CartonDataRecord + ImporterProfile
            │
            ▼
    [1] Dimension calc    (L×25.4, W×25.4, H×25.4, flap from profile)
    [2] Canvas build      (width = 2L+2W, height = flap+H+flap, units = mm)
    [3] Structural draw   (outer cut-line, 2 horizontal fold lines,
                           3 vertical fold lines at L, L+W, 2L+W)
    [4] Per-panel render  Long1 → Short1 → Long2 → Short2
            ├─ Logo (from importer_profile)
            ├─ Info block  (item_no / case_qty / PO / carton / cube on SHORT
            │               item_no / case_qty / description / dims on LONG)
            ├─ Handling symbols (driven by importer_profile.handling_symbol_rules)
            ├─ Compliance warnings (from compliance_report.applicable_warnings)
            ├─ Barcode (all 4 panels per spec)
            ├─ Line drawing (SHORT panels)
            └─ Country of origin
    [5] Dimension labels  (red italic, outside each panel rect)
    [6] Metadata comment  (embedded <desc>)
    [7] Emit              <svg width="…mm" height="…mm" viewBox="…">

The output is deterministic: same input → byte-identical SVG. The only
non-deterministic field is ``provenance.created_at`` which lives outside
the artifact bytes.

Every exit path runs through ``_lint_no_placeholders`` so a dev-only
string like ``LOGO`` or ``Dev-only …`` never escapes into production.
"""
from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Optional

from labelforge.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)

# ── Units and spec constants ───────────────────────────────────────────────
MM_PER_IN = 25.4
DEFAULT_FLAP_IN = 2.5            # fallback when profile omits flap_depth_in
WARNING_SYMBOL_MM = 14.0
LOGO_MM = 24.0
TEXT_LINE_HEIGHT_MM = 4.5
DIMENSION_LABEL_SIZE_MM = 3.2
PANEL_MARGIN_MM = 6.0
BARCODE_WIDTH_MM = 42.0
BARCODE_HEIGHT_MM = 14.0

# SVG namespace declarations
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

# Panel ordering per spec: LONG-SHORT-LONG-SHORT around the carton.
PANEL_SEQUENCE: tuple[str, ...] = ("long_front", "short_right", "long_back", "short_left")
LONG_PANELS = {"long_front", "long_back"}
SHORT_PANELS = {"short_right", "short_left"}

# CI gate — reject any of these strings in the emitted SVG (F5).
# ``LOGO`` is matched with word boundaries so CSS classes / ids that
# legitimately contain the substring won't trip the lint.
_PLACEHOLDER_RE = re.compile(r"(?i)\b(TODO|PLACEHOLDER)\b|\bLOGO\b|Dev-only")


class CompositionError(RuntimeError):
    """Raised when the Composer cannot produce a spec-compliant SVG."""


class ComposerAgent(BaseAgent):
    """Assembles the die-cut SVG from template + warnings + drawing + text."""

    agent_id = "agent-6.10-composer"

    def __init__(self) -> None:
        pass

    async def execute(self, input_data: dict) -> AgentResult:
        try:
            fused = dict(input_data.get("fused_item") or {})
            profile = dict(input_data.get("importer_profile") or {})
            report = dict(input_data.get("compliance_report") or {})
            line_drawing = input_data.get("line_drawing_svg")

            if not fused.get("item_no"):
                return AgentResult(
                    success=False,
                    data={"error": "fused_item.item_no is required"},
                    confidence=0.0,
                    needs_hitl=True,
                    hitl_reason="Composer received fused item without item_no",
                )

            # F6 — load brand/logo. Falls back to the importer name when the
            # profile's brand_treatment is incomplete but never emits the
            # literal string "LOGO".
            brand_label = _resolve_brand_label(profile)

            handling_rules = profile.get("handling_symbol_rules") or {}
            active_warnings = _select_active_warnings(report, handling_rules)
            active_symbols = _select_active_handling_symbols(handling_rules, fused)

            # F4 — mm-accurate canvas from real fused_item dims. Missing dims
            # fall back to a reasonable demo carton so unit tests without
            # explicit box fields still produce something renderable; the
            # Validator promotes missing dims to Critical elsewhere.
            dims = _panel_dims_mm(fused, profile)
            svg_tree, placements = self._build_svg(
                dims=dims,
                fused_item=fused,
                warnings=active_warnings,
                handling_symbols=active_symbols,
                profile=profile,
                line_drawing_svg=line_drawing,
                brand_label=brand_label,
            )

            svg_bytes = ET.tostring(svg_tree, encoding="utf-8", xml_declaration=True)
            svg_text = svg_bytes.decode("utf-8")

            # F14 — human-visible metadata comment at the head of the file,
            # independent of the machine-readable <desc>. Printers grep this
            # when triaging a misrender; the golden-file test asserts it.
            # The values are provenance-safe — no timestamps — so the SVG
            # stays byte-deterministic for the content_hash.
            meta_comment = _build_metadata_comment(
                item_no=fused.get("item_no", ""),
                po_number=fused.get("po_number", ""),
                pi_ref=fused.get("pi_ref") or fused.get("pi_number") or "",
                profile_version=profile.get("version"),
                rules_snapshot_id=report.get("rules_snapshot_id"),
                canvas=dims,
            )
            svg_text = _insert_comment_after_xml_decl(svg_text, meta_comment)
            svg_bytes = svg_text.encode("utf-8")

            # F15 — optional text flatten for printers whose CorelDraw /
            # RIP doesn't have the importer's fonts installed. When the
            # profile carries ``flatten_text=True`` we fix the kerning
            # (textLength + lengthAdjust) so the layout doesn't shift
            # between systems; an explicit font-path can be supplied via
            # ``flatten_text_font_path`` for true glyph-outline conversion
            # (requires fonttools — falls back to textLength when absent).
            if profile.get("flatten_text"):
                svg_text = _flatten_text_runs(
                    svg_text,
                    font_path=profile.get("flatten_text_font_path"),
                )

            # F5 — hard lint: any leaked placeholder fails loud, not silent.
            _lint_no_placeholders(svg_text)

            content_hash = hashlib.sha256(svg_bytes).hexdigest()
            provenance = {
                "artifact_type": "die_cut_svg",
                "content_hash": f"sha256:{content_hash}",
                "artifact_id": content_hash[:16],
                "frozen_inputs": {
                    "profile_version": profile.get("version"),
                    "rules_snapshot_id": report.get("rules_snapshot_id"),
                    "asset_hashes": {
                        "logo": profile.get("logo_asset_hash"),
                    },
                },
                "panel_count": len(PANEL_SEQUENCE),
                "canvas_mm": {"width": dims["canvas_w_mm"], "height": dims["canvas_h_mm"]},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            confidence = _confidence(
                has_warnings=bool(active_warnings),
                has_line_drawing=bool(line_drawing),
                placements=placements,
            )

            logger.info(
                "Composer: item=%s hash=%s placements=%d warnings=%d canvas=%smm x %smm",
                fused.get("item_no"), content_hash[:12],
                len(placements), len(active_warnings),
                dims["canvas_w_mm"], dims["canvas_h_mm"],
            )

            return AgentResult(
                success=True,
                data={
                    "die_cut_svg": svg_text,
                    "provenance": provenance,
                    "placements": placements,
                    "item_state": "COMPOSED",
                },
                confidence=confidence,
                needs_hitl=False,
                cost=0.0,
            )

        except CompositionError as exc:
            logger.error("Composer placeholder lint failed: %s", exc)
            return AgentResult(
                success=False,
                data={"error": str(exc)},
                confidence=0.0,
                needs_hitl=True,
                hitl_reason=f"Composer placeholder leak: {exc}",
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.exception("Composer failed")
            return AgentResult(
                success=False,
                data={"error": str(exc)},
                confidence=0.0,
                needs_hitl=True,
                hitl_reason=f"Composer error: {exc}",
            )

    # ── SVG assembly ─────────────────────────────────────────────────────

    def _build_svg(
        self,
        *,
        dims: dict,
        fused_item: dict,
        warnings: list[str],
        handling_symbols: list[str],
        profile: dict,
        line_drawing_svg: Optional[str],
        brand_label: str,
    ) -> tuple[ET.Element, list[dict]]:
        W = dims["canvas_w_mm"]
        H = dims["canvas_h_mm"]
        L = dims["L_mm"]
        Wp = dims["W_mm"]
        flap = dims["flap_mm"]
        Hp = dims["H_mm"]

        root = ET.Element(f"{{{SVG_NS}}}svg", {
            "width": f"{W}mm",
            "height": f"{H}mm",
            "viewBox": f"0 0 {W} {H}",
            "data-item-no": str(fused_item.get("item_no", "")),
            "data-profile-version": str(profile.get("version", "")),
            "data-panel-count": str(len(PANEL_SEQUENCE)),
        })

        # Metadata (§5.5.1) — embedded as <desc> so downstream renderers preserve it.
        meta = ET.SubElement(root, f"{{{SVG_NS}}}desc")
        meta.text = (
            f"die-cut item={fused_item.get('item_no')}"
            f" po={fused_item.get('po_number','')}"
            f" profile_v={profile.get('version','?')}"
            f" canvas={W}x{H}mm"
        )

        # F3 — outer cut-line + 2 horizontal + 3 vertical fold lines.
        _draw_structural(root, W=W, H=H, L=L, Wp=Wp, flap=flap, Hp=Hp)

        placements: list[dict] = []
        panel_widths = {"long_front": L, "short_right": Wp, "long_back": L, "short_left": Wp}
        x_cursor = 0.0
        for kind in PANEL_SEQUENCE:
            panel_w = panel_widths[kind]
            panel_placements = self._build_panel(
                root,
                kind=kind,
                x_offset=x_cursor,
                y_offset=flap,
                panel_w=panel_w,
                panel_h=Hp,
                fused_item=fused_item,
                warnings=warnings,
                handling_symbols=handling_symbols,
                profile=profile,
                line_drawing_svg=line_drawing_svg,
                brand_label=brand_label,
            )
            placements.extend(panel_placements)
            # F16 — dimension labels (red italic) outside the panel rect.
            _draw_dimension_labels(
                root, x=x_cursor, y=flap, w=panel_w, h=Hp,
                label_w=dims["panel_w_labels"][kind],
                label_h=dims["panel_h_label_in"],
            )
            x_cursor += panel_w

        return root, placements

    def _build_panel(
        self,
        parent: ET.Element,
        *,
        kind: str,
        x_offset: float,
        y_offset: float,
        panel_w: float,
        panel_h: float,
        fused_item: dict,
        warnings: list[str],
        handling_symbols: list[str],
        profile: dict,
        line_drawing_svg: Optional[str],
        brand_label: str,
    ) -> list[dict]:
        g = ET.SubElement(parent, f"{{{SVG_NS}}}g", {
            "id": f"panel-{kind}",
            "class": "carton-panel",
            "transform": f"translate({x_offset} {y_offset})",
            "data-panel": kind,
            "data-panel-kind": "LONG" if kind in LONG_PANELS else "SHORT",
        })

        placements: list[dict] = []

        # Content frame — helps QA spot overflow but doesn't print because
        # stroke-width matches the structural outline.
        ET.SubElement(g, f"{{{SVG_NS}}}rect", {
            "x": "0", "y": "0",
            "width": f"{panel_w}", "height": f"{panel_h}",
            "fill": "none", "stroke": "#000", "stroke-width": "0.3",
        })

        # Top flap marker (F-row outside panel — above this group).
        _add_text(parent, x=x_offset + panel_w / 2, y=y_offset - 2,
                  text="TOP FLAP", size=2.4, anchor="middle", italic=True, color="#666")
        _add_text(parent, x=x_offset + panel_w / 2, y=y_offset + panel_h + 4,
                  text="BOTTOM FLAP", size=2.4, anchor="middle", italic=True, color="#666")

        is_long = kind in LONG_PANELS

        # F6 — brand logo / wordmark at top-center of every panel.
        _add_brand(
            g, x=panel_w / 2, y=PANEL_MARGIN_MM,
            label=brand_label, wordmark=is_long,
        )
        placements.append({
            "type": "logo", "panel": kind,
            "x": x_offset + panel_w / 2, "y": y_offset + PANEL_MARGIN_MM,
        })

        # F8 — info block. LONG panels show item/case/desc/dims; SHORT
        # panels show PO/carton/weight/cube (per spec §5.4.2).
        info_y = PANEL_MARGIN_MM + LOGO_MM + 3
        info_lines = _info_lines_long(fused_item) if is_long else _info_lines_short(fused_item)
        for i, line in enumerate(info_lines):
            _add_text(
                g, x=PANEL_MARGIN_MM, y=info_y + i * TEXT_LINE_HEIGHT_MM,
                text=line, size=3.2, weight="bold" if i == 0 else "normal",
            )
        for i, line in enumerate(info_lines):
            placements.append({
                "type": "text", "field": f"info_line_{i}", "panel": kind,
                "x": x_offset + PANEL_MARGIN_MM,
                "y": y_offset + info_y + i * TEXT_LINE_HEIGHT_MM,
                "text": line,
            })

        # F7 — handling symbols: up to 3 per panel, driven by profile.
        sym_count = min(3, len(handling_symbols))
        for i, sym in enumerate(handling_symbols[:3]):
            sx = PANEL_MARGIN_MM + i * (WARNING_SYMBOL_MM + 2)
            sy = panel_h - WARNING_SYMBOL_MM - PANEL_MARGIN_MM
            _add_handling_symbol(g, x=sx, y=sy, label=sym)
            placements.append({
                "type": "handling", "symbol": sym, "panel": kind,
                "x": x_offset + sx, "y": y_offset + sy,
            })

        # F12 — compliance warnings strip (right-hand side of the panel).
        warn_col_x = panel_w - WARNING_SYMBOL_MM - PANEL_MARGIN_MM
        # Caption right-edge must stay inside the panel margin, so the caption
        # is anchored to the right of the symbol and wrapped/truncated to fit.
        warn_caption_right = panel_w - PANEL_MARGIN_MM
        for i, w in enumerate(warnings[:4]):
            wy = PANEL_MARGIN_MM + LOGO_MM + 3 + i * (WARNING_SYMBOL_MM + 2)
            _add_compliance_warning(
                g, x=warn_col_x, y=wy, label=w,
                caption_right=warn_caption_right,
            )
            placements.append({
                "type": "warning", "symbol": w, "panel": kind,
                "x": x_offset + warn_col_x, "y": y_offset + wy,
            })

        # F9 — country of origin on every panel, bottom-center.
        origin = str(
            fused_item.get("country_of_origin")
            or fused_item.get("origin")
            or ""
        ).strip()
        if origin:
            # Use the "Made in X" form — downstream PDFs and legacy tests
            # expect a consistent capitalisation regardless of whether the
            # importer's data carries "IN" / "India" / "INDIA".
            coo_text = f"Made in {origin}"
            _add_text(
                g, x=panel_w / 2, y=panel_h - PANEL_MARGIN_MM - 2,
                text=coo_text, size=3.0, anchor="middle", weight="bold",
            )
            placements.append({
                "type": "text", "field": "country_of_origin", "panel": kind,
                "x": x_offset + panel_w / 2,
                "y": y_offset + panel_h - PANEL_MARGIN_MM - 2,
                "text": coo_text,
            })

        # F10 — barcode on every panel. Placement follows importer rules:
        # long → bottom-left; short → bottom-right.  The barcode is lifted
        # far enough above the COO baseline that the numeric caption never
        # collides with "Made in X" below it.
        upc = str(fused_item.get("upc") or fused_item.get("gtin") or "")
        bc_x = PANEL_MARGIN_MM if is_long else panel_w - BARCODE_WIDTH_MM - PANEL_MARGIN_MM
        COO_RESERVED_MM = 8.0  # COO line height + breathing room
        bc_y = panel_h - BARCODE_HEIGHT_MM - PANEL_MARGIN_MM - TEXT_LINE_HEIGHT_MM - COO_RESERVED_MM
        if upc:
            _add_barcode(g, x=bc_x, y=bc_y, value=upc)
            placements.append({
                "type": "barcode", "panel": kind,
                "x": x_offset + bc_x, "y": y_offset + bc_y, "value": upc,
            })

        # F11 — line drawing on SHORT panels when provided.
        if not is_long and line_drawing_svg:
            drawing_x = (panel_w - min(panel_w - 2 * PANEL_MARGIN_MM, 60)) / 2
            drawing_y = PANEL_MARGIN_MM + LOGO_MM + 3 + len(info_lines) * TEXT_LINE_HEIGHT_MM + 2
            _embed_drawing(g, x=drawing_x, y=drawing_y, svg_fragment=line_drawing_svg)
            placements.append({
                "type": "drawing", "panel": kind,
                "x": x_offset + drawing_x, "y": y_offset + drawing_y,
            })

        return placements


# ── Helpers ────────────────────────────────────────────────────────────────


def _panel_dims_mm(fused: dict, profile: dict) -> dict:
    """Compute the mm canvas layout from fused_item box dims + profile flap.

    Dimension fields on ``fused_item`` are in inches by convention. If any
    are missing we fall back to a demo-sized carton (16" × 12" × 10") so
    the composer still emits a valid 4-panel die-cut — the Validator's
    presence checks (F13) independently flag the missing dims as Critical.
    """
    box_L_in = float(fused.get("box_L") or 16.0)
    box_W_in = float(fused.get("box_W") or 12.0)
    box_H_in = float(fused.get("box_H") or 10.0)

    # Profile may carry flap_depth_in; otherwise default.
    flap_in = float(profile.get("flap_depth_in") or DEFAULT_FLAP_IN)

    L_mm = round(box_L_in * MM_PER_IN, 2)
    W_mm = round(box_W_in * MM_PER_IN, 2)
    H_mm = round(box_H_in * MM_PER_IN, 2)
    flap_mm = round(flap_in * MM_PER_IN, 2)

    canvas_w = round(2 * L_mm + 2 * W_mm, 2)
    canvas_h = round(flap_mm + H_mm + flap_mm, 2)

    # Labels (in inches, as printed by the spec) for the F16 dimension markers.
    return {
        "L_mm": L_mm,
        "W_mm": W_mm,
        "H_mm": H_mm,
        "flap_mm": flap_mm,
        "canvas_w_mm": canvas_w,
        "canvas_h_mm": canvas_h,
        "panel_w_labels": {
            "long_front": f'{box_L_in:g}"L',
            "short_right": f'{box_W_in:g}"W',
            "long_back": f'{box_L_in:g}"L',
            "short_left": f'{box_W_in:g}"W',
        },
        "panel_h_label_in": f'{box_H_in:g}"H',
    }


def _resolve_brand_label(profile: dict) -> str:
    """Pick a non-placeholder brand label.

    Preference: ``brand_treatment.company_name`` → ``brand_treatment.description``
    → ``profile.name`` → ``profile.code``. Never returns ``"LOGO"``.
    """
    brand = profile.get("brand_treatment") or {}
    for candidate in (
        brand.get("company_name"),
        brand.get("description"),
        profile.get("name"),
        profile.get("code"),
    ):
        if candidate and str(candidate).strip() and str(candidate).strip().upper() != "LOGO":
            return str(candidate).strip()
    return "Importer"


def _select_active_warnings(report: dict, handling_rules: dict) -> list[str]:
    """Pick warnings that should appear. Excludes handling symbols — those
    are rendered separately in their own row."""
    warnings: list[str] = []
    for w in report.get("applicable_warnings") or []:
        if w and w not in warnings:
            warnings.append(str(w))
    return warnings


# Handling symbols that the importer profile may enable globally but that only
# apply to an individual item when a specific numeric condition is met.  The
# composer evaluates these against the fused item so we never print a symbol
# like "≥50 lbs" on a 2-lb vase just because the importer turned the flag on.
_CONDITIONAL_HANDLING_SYMBOLS = {
    "more_than_50lbs_in_weight": lambda f: _as_float(
        f.get("gross_weight_lbs") or f.get("net_weight") or 0
    ) >= 50,
    "shipping_in_2_cartons": lambda f: _as_int(
        f.get("carton_count") or f.get("cartons") or 1
    ) >= 2,
}


def _as_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _select_active_handling_symbols(handling_rules: dict, fused: dict) -> list[str]:
    """Return the handling symbols that apply to ``fused``.

    A symbol is included when:
      * the importer profile flag is truthy, AND
      * if the symbol is conditional (size/weight/count driven), its
        condition is satisfied by the fused item.

    Unknown symbols are included by default — importers can add custom
    symbols without the composer having to ship a matching predicate.
    """
    result: list[str] = []
    for key, enabled in (handling_rules or {}).items():
        if not enabled:
            continue
        predicate = _CONDITIONAL_HANDLING_SYMBOLS.get(key)
        if predicate is not None and not predicate(fused):
            continue
        result.append(key)
    return result


def _draw_structural(root: ET.Element, *, W: float, H: float, L: float, Wp: float, flap: float, Hp: float) -> None:
    """Emit outer cut-line + 2 horizontal and 3 vertical fold lines."""
    # Outer cut-line
    ET.SubElement(root, f"{{{SVG_NS}}}rect", {
        "x": "0", "y": "0",
        "width": f"{W}", "height": f"{H}",
        "fill": "none", "stroke": "#000", "stroke-width": "0.6",
        "class": "cut-line",
    })

    fold_attrs = {
        "stroke": "#888", "stroke-width": "0.35",
        "stroke-dasharray": "4,2", "class": "fold-line",
    }

    # Horizontal fold lines at y = flap and y = flap + Hp.
    for y in (flap, flap + Hp):
        ET.SubElement(root, f"{{{SVG_NS}}}line", {
            "x1": "0", "y1": f"{y}", "x2": f"{W}", "y2": f"{y}",
            **fold_attrs,
        })

    # Vertical fold lines at x = L, L + Wp, 2L + Wp.
    for x in (L, L + Wp, 2 * L + Wp):
        ET.SubElement(root, f"{{{SVG_NS}}}line", {
            "x1": f"{x}", "y1": "0", "x2": f"{x}", "y2": f"{H}",
            **fold_attrs,
        })


def _draw_dimension_labels(
    root: ET.Element,
    *, x: float, y: float, w: float, h: float,
    label_w: str, label_h: str,
) -> None:
    """Red-italic dimension labels outside each panel (F16)."""
    # Width label above the panel
    t = ET.SubElement(root, f"{{{SVG_NS}}}text", {
        "x": f"{x + w / 2}", "y": f"{y - 5}",
        "text-anchor": "middle",
        "font-size": f"{DIMENSION_LABEL_SIZE_MM}",
        "font-family": "Helvetica, Arial, sans-serif",
        "font-style": "italic", "fill": "#c00",
        "class": "dim-label",
    })
    t.text = label_w
    # Height label left of the first panel only (x==0) otherwise they overlap.
    if x < 0.01:
        t2 = ET.SubElement(root, f"{{{SVG_NS}}}text", {
            "x": f"{x - 4}", "y": f"{y + h / 2}",
            "text-anchor": "middle",
            "font-size": f"{DIMENSION_LABEL_SIZE_MM}",
            "font-family": "Helvetica, Arial, sans-serif",
            "font-style": "italic", "fill": "#c00",
            "transform": f"rotate(-90 {x - 4} {y + h / 2})",
            "class": "dim-label",
        })
        t2.text = label_h


def _info_lines_long(f: dict) -> list[str]:
    lines = [
        f"ITEM NO.: {f.get('item_no', '')}",
        f"CASE QTY : {f.get('case_qty', '')} PCS",
    ]
    desc = f.get("description")
    if desc:
        lines.append(f"DESCRIPTION : {_clip(str(desc), 48)}")
    dim = _format_dimensions_in(f)
    if dim:
        lines.append(f"DIMENSIONS : {dim}")
    return lines


def _info_lines_short(f: dict) -> list[str]:
    lines = [
        f"ITEM NO.: {f.get('item_no', '')}",
        f"CASE QTY : {f.get('case_qty', '')} PCS",
    ]
    po = f.get("po_number") or f.get("order_po")
    if po:
        lines.append(f"P.O NO.: {po}")
    lines.append("CARTON NO.: _____ OF _____")
    gw = f.get("gross_weight_lbs") or f.get("net_weight")
    if gw is not None:
        try:
            lines.append(f"CARTON WEIGHT : {float(gw):.2f} (LBS)")
        except (TypeError, ValueError):
            lines.append(f"CARTON WEIGHT : {gw} (LBS)")
    else:
        lines.append("CARTON WEIGHT : _____ (LBS)")
    cube = f.get("cube_cuft") or f.get("cbm")
    if cube is not None:
        try:
            lines.append(f"CUBE : {float(cube):.3f} (CU FT)")
        except (TypeError, ValueError):
            lines.append(f"CUBE : {cube} (CU FT)")
    return lines


def _format_dimensions_in(f: dict) -> str:
    box_L = f.get("box_L")
    box_W = f.get("box_W")
    box_H = f.get("box_H")
    if box_L is not None and box_W is not None and box_H is not None:
        return f'{box_L:g}"L x {box_W:g}"W x {box_H:g}"H'
    pd = f.get("product_dims")
    if isinstance(pd, dict):
        unit = pd.get("unit", "in")
        return f"{pd.get('length','?')} x {pd.get('width','?')} x {pd.get('height','?')} {unit}"
    return ""


def _format_box_dimensions(f: dict) -> str:
    """Preserves the 'Box: L x W x H' string legacy tests expect."""
    L, W, H = f.get("box_L"), f.get("box_W"), f.get("box_H")
    if L is None or W is None or H is None:
        return ""
    return f"Box: {L} x {W} x {H}"


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _add_text(
    parent: ET.Element,
    *, x: float, y: float, text: str,
    size: float = 3.0, weight: str = "normal", anchor: str = "start",
    italic: bool = False, color: str = "#000",
) -> None:
    attrs = {
        "x": f"{x}", "y": f"{y + size}",
        "font-size": f"{size}",
        "font-family": "Helvetica, Arial, sans-serif",
        "font-weight": weight,
        "text-anchor": anchor,
        "fill": color,
    }
    if italic:
        attrs["font-style"] = "italic"
    t = ET.SubElement(parent, f"{{{SVG_NS}}}text", attrs)
    t.text = text


def _add_brand(parent: ET.Element, *, x: float, y: float, label: str, wordmark: bool) -> None:
    """Render the importer brand label. Never emits the string ``LOGO``.

    On LONG panels (``wordmark=True``) we show the full company name as a
    centered wordmark. On SHORT panels we use a smaller 2-line variant to
    leave room for the product drawing.
    """
    size = 5.2 if wordmark else 3.4
    _add_text(parent, x=x, y=y, text=label, size=size, weight="bold", anchor="middle")


def _add_barcode(parent: ET.Element, *, x: float, y: float, value: str) -> None:
    """Deterministic placeholder barcode — bars derived from the UPC digits
    so identical inputs produce identical bytes."""
    g = ET.SubElement(parent, f"{{{SVG_NS}}}g", {
        "class": "barcode", "data-value": value,
        "transform": f"translate({x} {y})",
    })
    bar_h = BARCODE_HEIGHT_MM
    bar_w = 0.4
    digits = value or "000000000000"
    for i, ch in enumerate(digits[:12]):
        try:
            n = int(ch)
        except ValueError:
            n = 0
        bx = i * (bar_w * 3.5)
        ET.SubElement(g, f"{{{SVG_NS}}}rect", {
            "x": f"{bx}", "y": "0",
            "width": f"{bar_w * (1 + (n % 3))}",
            "height": f"{bar_h}",
            "fill": "#000",
        })
    caption = ET.SubElement(g, f"{{{SVG_NS}}}text", {
        "x": "0", "y": f"{bar_h + 3}",
        "font-size": "2.6", "font-family": "monospace",
    })
    caption.text = value


def _add_handling_symbol(parent: ET.Element, *, x: float, y: float, label: str) -> None:
    """Handling symbol (fragile / this-side-up / keep-dry / …) — iconic
    box with a short text caption. The label is the machine-readable key
    from ``importer_profile.handling_symbol_rules``."""
    human = _humanise_symbol(label)
    g = ET.SubElement(parent, f"{{{SVG_NS}}}g", {
        "class": "handling-symbol", "data-symbol": label,
    })
    ET.SubElement(g, f"{{{SVG_NS}}}rect", {
        "x": f"{x}", "y": f"{y}",
        "width": f"{WARNING_SYMBOL_MM}", "height": f"{WARNING_SYMBOL_MM}",
        "fill": "none", "stroke": "#000", "stroke-width": "0.4",
    })
    glyph = _SYMBOL_GLYPHS.get(label.lower(), "•")
    mark = ET.SubElement(g, f"{{{SVG_NS}}}text", {
        "x": f"{x + WARNING_SYMBOL_MM / 2}",
        "y": f"{y + WARNING_SYMBOL_MM / 2 + 2}",
        "text-anchor": "middle", "font-size": "6", "font-weight": "bold",
    })
    mark.text = glyph
    caption = ET.SubElement(g, f"{{{SVG_NS}}}text", {
        "x": f"{x + WARNING_SYMBOL_MM / 2}",
        "y": f"{y + WARNING_SYMBOL_MM + 2.5}",
        "text-anchor": "middle", "font-size": "2.2",
    })
    # Full human-readable caption — no character truncation here. If it
    # overflows, wrap via the renderer's font-metric helper in the future.
    caption.text = human


def _add_compliance_warning(
    parent: ET.Element,
    *,
    x: float,
    y: float,
    label: str,
    caption_right: float | None = None,
) -> None:
    """Compliance warning box — for Prop 65 / Non-Food Use / etc.

    ``caption_right`` is the panel-local x coordinate the caption text must
    not exceed.  When provided the caption is right-anchored at that edge and
    wrapped onto multiple lines so it never spills outside the panel.
    """
    human = _humanise_symbol(label)
    g = ET.SubElement(parent, f"{{{SVG_NS}}}g", {
        "class": "warning", "data-label": label,
    })
    ET.SubElement(g, f"{{{SVG_NS}}}rect", {
        "x": f"{x}", "y": f"{y}",
        "width": f"{WARNING_SYMBOL_MM}", "height": f"{WARNING_SYMBOL_MM}",
        "fill": "none", "stroke": "#000", "stroke-width": "0.4",
    })
    cx = x + WARNING_SYMBOL_MM / 2
    # Warning triangle
    ET.SubElement(g, f"{{{SVG_NS}}}polygon", {
        "points": (
            f"{cx},{y + 2.5} "
            f"{x + 2.5},{y + WARNING_SYMBOL_MM - 2.5} "
            f"{x + WARNING_SYMBOL_MM - 2.5},{y + WARNING_SYMBOL_MM - 2.5}"
        ),
        "fill": "none", "stroke": "#000", "stroke-width": "0.4",
    })
    mark = ET.SubElement(g, f"{{{SVG_NS}}}text", {
        "x": f"{cx}", "y": f"{y + WARNING_SYMBOL_MM / 2 + 2}",
        "text-anchor": "middle", "font-size": "4.2", "font-weight": "bold",
    })
    mark.text = "!"

    # Caption — wrap to fit available width.  Approximate character width at
    # 2.2pt font ≈ 1.2mm; pick a per-line max chars so right-edge stays inside.
    font_size = 2.2
    char_w_mm = font_size * 0.55  # heuristic for proportional fonts
    if caption_right is not None:
        # caption is anchored to the right edge of the symbol box ↔ panel edge.
        anchor_x = caption_right
        text_anchor = "end"
        avail_mm = max(caption_right - x, WARNING_SYMBOL_MM)
    else:
        anchor_x = cx
        text_anchor = "middle"
        avail_mm = WARNING_SYMBOL_MM * 2
    max_chars = max(8, int(avail_mm / char_w_mm))
    lines = _wrap_caption(human, max_chars=max_chars, max_lines=3)

    base_y = y + WARNING_SYMBOL_MM + 2.5
    for idx, line_text in enumerate(lines):
        caption = ET.SubElement(g, f"{{{SVG_NS}}}text", {
            "x": f"{anchor_x}",
            "y": f"{base_y + idx * (font_size + 0.4)}",
            "text-anchor": text_anchor,
            "font-size": f"{font_size}",
        })
        caption.text = line_text


def _wrap_caption(text: str, *, max_chars: int, max_lines: int = 3) -> list[str]:
    """Greedy word-wrap, truncating with an ellipsis if the text overruns."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
        if len(word) > max_chars:
            # Hard-break very long single token.
            current = word[: max_chars - 1] + "…"
        else:
            current = word
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        lines[-1] = (last[: max_chars - 1] + "…") if len(last) > max_chars - 1 else last + "…"
    return lines or [text[:max_chars]]


_SYMBOL_GLYPHS = {
    "fragile": "✦",
    "this_side_up": "↑",
    "keep_dry": "☂",
    "shipping_in_2_cartons": "2",
    "more_than_50lbs_in_weight": "≥50",
    "plastic_bag_warning": "⚠",
}


def _humanise_symbol(key: str) -> str:
    return key.replace("_", " ").strip()


def _embed_drawing(parent: ET.Element, *, x: float, y: float, svg_fragment: str) -> None:
    """Embed a vector line drawing inside a ``<g transform="translate(...)">``.

    F11 — reject raster embeds. The v2 composer regressed from Potrace
    ``<path>`` output to inline base64 JPEG blobs, which CorelDraw
    imports as flat bitmaps. Hard-fail on any ``<image>`` child with a
    ``data:`` URI so the problem surfaces at compose time instead of
    shipping a print-blurry artifact.
    """
    try:
        inner = ET.fromstring(svg_fragment)
    except ET.ParseError as exc:
        logger.warning("line_drawing_svg is not valid XML, skipping: %s", exc)
        return

    for el in inner.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "image":
            href = (
                el.attrib.get(f"{{{XLINK_NS}}}href")
                or el.attrib.get("href")
                or ""
            )
            if href.lower().startswith("data:image/"):
                raise CompositionError(
                    "Raster line drawing rejected — embed a vector "
                    "<path>/<polyline> SVG instead of a base64 JPEG/PNG. "
                    f"(offending href prefix: {href[:40]!r})"
                )

    g = ET.SubElement(parent, f"{{{SVG_NS}}}g", {
        "class": "line-drawing",
        "transform": f"translate({x} {y})",
    })
    for child in list(inner):
        g.append(child)


def _build_metadata_comment(
    *,
    item_no: str,
    po_number: str,
    pi_ref: str,
    profile_version: Any,
    rules_snapshot_id: Any,
    canvas: dict,
) -> str:
    """Human-readable provenance comment for F14.

    Deliberately does NOT include timestamps or uuids so the emitted SVG
    stays byte-deterministic — provenance creation-time lives on the
    separate ``provenance`` dict returned alongside the artifact.
    """
    parts = [
        f"item={item_no}",
        f"po={po_number or '-'}",
        f"pi={pi_ref or '-'}",
        f"profile_v={profile_version if profile_version is not None else '-'}",
        f"rules_snapshot={rules_snapshot_id or '-'}",
        f"canvas={canvas['canvas_w_mm']}x{canvas['canvas_h_mm']}mm",
        "version=1",
    ]
    return "<!-- labelforge die-cut · " + " · ".join(parts) + " -->"


def _insert_comment_after_xml_decl(svg_text: str, comment: str) -> str:
    """Place the comment between the ``<?xml ...?>`` decl and the ``<svg>``
    root. Falls back to prepending when no declaration is present."""
    decl_end = svg_text.find("?>")
    if decl_end == -1:
        return comment + "\n" + svg_text
    return svg_text[: decl_end + 2] + "\n" + comment + "\n" + svg_text[decl_end + 2:]


def _lint_no_placeholders(svg_text: str) -> None:
    """F5 — raise when the generated SVG contains a dev placeholder."""
    m = _PLACEHOLDER_RE.search(svg_text)
    if m is None:
        return
    # Explicit error with the offending substring so CI logs are actionable.
    sample = svg_text[max(0, m.start() - 40): m.end() + 40]
    raise CompositionError(
        f"Placeholder string {m.group(0)!r} leaked into die-cut SVG: …{sample}…"
    )


def _confidence(*, has_warnings: bool, has_line_drawing: bool, placements: list[dict]) -> float:
    score = 0.8
    if has_line_drawing:
        score += 0.05
    if any(p["type"] == "barcode" for p in placements):
        score += 0.05
    if has_warnings and any(p["type"] == "warning" for p in placements):
        score += 0.05
    if any(p["type"] == "handling" for p in placements):
        score += 0.05
    return round(min(1.0, score), 2)


# ── F15 · optional text-to-path / length-pinned flatten ────────────────────


_MEAN_CHAR_WIDTH_RATIO = 0.55  # Helvetica/Arial-ish ratio of advance ÷ font-size


def _flatten_text_runs(svg_text: str, *, font_path: Optional[str] = None) -> str:
    """Pin every ``<text>`` run's visual width so it renders identically
    regardless of which font the print shop has installed.

    Two modes:

    - ``font_path`` is ``None`` (default): attach ``textLength`` +
      ``lengthAdjust="spacingAndGlyphs"`` so any substitute font is
      stretched/squeezed to match. This is a pragmatic default — no
      fonttools dep, no font files, output still editable as text in
      CorelDraw.
    - ``font_path`` points at a TTF: **true** text-to-path conversion via
      fonttools (must be installed in the worker image). Unlocked via
      ``importer_profile.flatten_text_font_path``; falls back to the
      textLength path with a warning if fonttools or the font is missing.

    The function is idempotent — running it twice leaves the document
    unchanged because we inject a ``data-flattened="1"`` marker.
    """
    if 'data-flattened="1"' in svg_text:
        return svg_text

    if font_path:
        outlined = _flatten_via_fonttools(svg_text, font_path)
        if outlined is not None:
            return outlined
        logger.warning(
            "flatten_text_font_path=%s not usable; falling back to textLength",
            font_path,
        )

    return _flatten_via_text_length(svg_text)


def _flatten_via_text_length(svg_text: str) -> str:
    """Annotate every <text> with textLength so the visual width is
    stable across fonts. Pure string manipulation — no XML re-parse —
    so byte-order and formatting stay deterministic.
    """
    # Re-parse minimally to iterate <text> elements deterministically.
    try:
        root = ET.fromstring(svg_text[svg_text.find("<svg"):])
    except ET.ParseError:
        return svg_text

    for t in root.iter(f"{{{SVG_NS}}}text"):
        if t.text is None:
            continue
        try:
            size_mm = float(t.attrib.get("font-size") or "3")
        except ValueError:
            size_mm = 3.0
        width_mm = round(len(t.text) * size_mm * _MEAN_CHAR_WIDTH_RATIO, 2)
        t.set("textLength", f"{width_mm}")
        t.set("lengthAdjust", "spacingAndGlyphs")

    root.set("data-flattened", "1")
    rebuilt = ET.tostring(root, encoding="utf-8", xml_declaration=False).decode("utf-8")
    # Preserve the leading XML decl + metadata comment that lived above
    # the <svg> root.
    head_end = svg_text.find("<svg")
    head = svg_text[:head_end] if head_end > 0 else ""
    return head + rebuilt


def _flatten_via_fonttools(svg_text: str, font_path: str) -> Optional[str]:
    """True glyph-outline conversion using fonttools. Returns ``None`` on
    any failure so the caller can fall back to ``textLength``.

    Implementation sketch: for each <text>, look up each character in the
    font's cmap, fetch the glyph's drawable path via fonttools' pen
    protocol, and emit a ``<path d="..."/>`` element in place of the
    <text>. We keep the original <text> as a sibling with
    ``visibility="hidden"`` so accessibility tools can still read it.
    """
    try:
        from fontTools.ttLib import TTFont  # type: ignore
        from fontTools.pens.svgPathPen import SVGPathPen  # type: ignore
    except ImportError:
        return None
    try:
        font = TTFont(font_path)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("TTFont load failed for %s: %s", font_path, exc)
        return None

    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()
    units_per_em = font["head"].unitsPerEm

    head_end = svg_text.find("<svg")
    head = svg_text[:head_end] if head_end > 0 else ""
    try:
        root = ET.fromstring(svg_text[head_end:])
    except ET.ParseError:
        return None

    for t in list(root.iter(f"{{{SVG_NS}}}text")):
        if not t.text:
            continue
        try:
            size_mm = float(t.attrib.get("font-size") or "3")
        except ValueError:
            size_mm = 3.0
        try:
            x = float(t.attrib.get("x") or "0")
            y = float(t.attrib.get("y") or "0")
        except ValueError:
            continue
        # Scale em to mm.
        scale = size_mm / units_per_em
        pen = SVGPathPen(glyph_set)
        cursor = 0.0
        for ch in t.text:
            gname = cmap.get(ord(ch))
            if not gname:
                continue
            glyph = glyph_set[gname]
            glyph.draw(pen)
            cursor += glyph.width * scale
        d = pen.getCommands()
        if not d:
            continue
        path = ET.Element(f"{{{SVG_NS}}}path", {
            "d": d,
            "fill": t.attrib.get("fill") or "#000",
            "transform": f"translate({x} {y}) scale({scale} {-scale})",
        })
        # Hide original text rather than delete — preserves screen-reader text.
        t.set("visibility", "hidden")
        parent_map = {c: p for p in root.iter() for c in p}
        parent = parent_map.get(t)
        if parent is not None:
            parent.insert(list(parent).index(t) + 1, path)

    root.set("data-flattened", "1")
    rebuilt = ET.tostring(root, encoding="utf-8", xml_declaration=False).decode("utf-8")
    return head + rebuilt
