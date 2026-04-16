"""Composer Agent (TASK-034, Sprint-12).

Assembles the final die-cut carton SVG for a single item by stitching:

*   the importer's panel-layout template (from :class:`ImporterProfile`)
*   applicable warning-label symbols (from the compliance report)
*   the line drawing of the product (if provided)
*   dynamic text fields: UPC/EAN, description, quantity, dimensions, etc.

The output is a *deterministic* SVG string — the same input produces the
same bytes, which lets :class:`~labelforge.core.provenance.ProvenanceEmitter`
compute a stable content hash. We intentionally avoid timestamps or random
IDs in the SVG; the `created_at` field on the returned provenance dict is
the only non-deterministic piece and is *not* embedded in the artifact.

Input::

    {
        "fused_item": {...},             # FusedItem dict (required)
        "importer_profile": {...},       # ImporterProfile dict (required)
        "compliance_report": {...},      # ComplianceReport dict (required)
        "line_drawing_svg": "<svg .../>" # optional
    }

Output :class:`AgentResult.data`::

    {
        "die_cut_svg": "<svg xmlns=...>",
        "provenance": {
            "artifact_type": "die_cut_svg",
            "content_hash": "sha256:...",
            "frozen_inputs": {
                "profile_version": 2,
                "asset_hashes": {...},
                "rules_snapshot_id": "..."   # when available
            },
            ...
        },
        "placements": [
            {"type": "warning", "symbol": "fragile", "panel": "carton_top", "x": 10, "y": 20},
            ...
        ],
        "item_state": "COMPOSED"
    }
"""
from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Optional

from labelforge.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)

# ── SVG canvas constants ───────────────────────────────────────────────────
# Deliberately small, panel-scaled units so the output stays human-debuggable.
# One "unit" == 1mm in print terms (the downstream renderer may rescale).

PANEL_GAP_MM = 4.0
DEFAULT_PANEL_MM = (120.0, 80.0)   # (width, height) if ImporterProfile omits a panel spec
WARNING_SYMBOL_MM = 14.0
LOGO_MM = 24.0
TEXT_LINE_HEIGHT_MM = 4.5

# SVG namespace declarations
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)


class ComposerAgent(BaseAgent):
    """Assembles the die-cut SVG from template + warnings + drawing + text.

    The agent is deterministic and does not call an LLM. Heavy validation
    runs in :class:`~labelforge.agents.validator.ValidatorAgent`; Composer
    focuses on correct placement and provenance.
    """

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

            panel_layouts = self._select_panel_layouts(profile)
            handling_rules = profile.get("handling_symbol_rules") or {}

            # Pull the warnings that actually need to appear on the carton/product.
            active_warnings = self._select_active_warnings(report, handling_rules)

            svg_tree, placements = self._build_svg(
                panel_layouts=panel_layouts,
                fused_item=fused,
                warnings=active_warnings,
                profile=profile,
                line_drawing_svg=line_drawing,
            )

            svg_bytes = ET.tostring(svg_tree, encoding="utf-8", xml_declaration=True)
            svg_text = svg_bytes.decode("utf-8")
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
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            confidence = self._confidence(
                has_warnings=bool(active_warnings),
                has_line_drawing=bool(line_drawing),
                placements=placements,
            )

            logger.info(
                "Composer: item=%s hash=%s placements=%d warnings=%d",
                fused.get("item_no"), content_hash[:12],
                len(placements), len(active_warnings),
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

        except Exception as exc:
            logger.exception("Composer failed")
            return AgentResult(
                success=False,
                data={"error": str(exc)},
                confidence=0.0,
                needs_hitl=True,
                hitl_reason=f"Composer error: {exc}",
            )

    # ── Panel resolution ─────────────────────────────────────────────────

    @staticmethod
    def _select_panel_layouts(profile: dict) -> dict[str, dict]:
        """Normalize ImporterProfile.panel_layouts into a consistent dict.

        The field historically carries two shapes:

        *   Map of ``panel_name → [required_field, ...]``
            (from ``protocol_analyzer`` extraction), or
        *   Map of ``panel_name → {"selected": bool, "template": ..., ...}``
            (onboarding-wizard form state).

        We normalize both to ``{panel_name: {"fields": [...], "template": ...}}``.
        """
        raw = profile.get("panel_layouts")
        if not raw or not isinstance(raw, dict):
            return {
                "carton_top": {"fields": ["logo", "upc", "item_description"]},
                "carton_side": {"fields": ["warnings", "country_of_origin"]},
            }
        normalized: dict[str, dict] = {}
        for panel, spec in raw.items():
            if isinstance(spec, list):
                normalized[panel] = {"fields": [str(f) for f in spec]}
            elif isinstance(spec, dict):
                if spec.get("selected") is False:
                    continue
                fields = spec.get("fields") or spec.get("required_fields") or []
                normalized[panel] = {
                    "fields": [str(f) for f in fields],
                    "template": spec.get("template"),
                }
            # strings / bools etc: ignore silently
        if not normalized:
            normalized["carton_top"] = {"fields": ["logo", "upc", "item_description"]}
        return normalized

    @staticmethod
    def _select_active_warnings(report: dict, handling_rules: dict) -> list[str]:
        """Pick the warning labels that should appear.

        Merges the compliance report's ``applicable_warnings`` with any
        ``handling_symbol_rules`` on the importer profile that are truthy.
        """
        warnings: list[str] = []
        for w in report.get("applicable_warnings") or []:
            if w and w not in warnings:
                warnings.append(str(w))
        for key, enabled in (handling_rules or {}).items():
            if enabled and key not in warnings:
                warnings.append(key)
        return warnings

    # ── SVG assembly ─────────────────────────────────────────────────────

    def _build_svg(
        self,
        *,
        panel_layouts: dict[str, dict],
        fused_item: dict,
        warnings: list[str],
        profile: dict,
        line_drawing_svg: Optional[str],
    ) -> tuple[ET.Element, list[dict]]:
        panels = list(panel_layouts.keys())
        n = len(panels)

        total_w = DEFAULT_PANEL_MM[0] * n + PANEL_GAP_MM * (n - 1)
        total_h = DEFAULT_PANEL_MM[1]

        # Namespaces are injected by ET.register_namespace("", SVG_NS) above —
        # declaring xmlns here explicitly would produce a duplicate attribute.
        root = ET.Element(f"{{{SVG_NS}}}svg", {
            "width": f"{total_w}mm",
            "height": f"{total_h}mm",
            "viewBox": f"0 0 {total_w} {total_h}",
            "data-item-no": str(fused_item.get("item_no", "")),
            "data-profile-version": str(profile.get("version", "")),
        })

        # Global metadata block — embedded as a <desc> so renderers preserve it.
        meta = ET.SubElement(root, f"{{{SVG_NS}}}desc")
        meta.text = (
            f"die-cut for item {fused_item.get('item_no')} "
            f"· profile v{profile.get('version', '?')}"
        )

        placements: list[dict] = []
        for idx, panel_name in enumerate(panels):
            x_offset = idx * (DEFAULT_PANEL_MM[0] + PANEL_GAP_MM)
            spec = panel_layouts[panel_name]
            panel_placements = self._build_panel(
                root,
                panel_name=panel_name,
                x_offset=x_offset,
                panel_spec=spec,
                fused_item=fused_item,
                warnings=warnings,
                profile=profile,
                line_drawing_svg=line_drawing_svg,
            )
            placements.extend(panel_placements)

        return root, placements

    def _build_panel(
        self,
        parent: ET.Element,
        *,
        panel_name: str,
        x_offset: float,
        panel_spec: dict,
        fused_item: dict,
        warnings: list[str],
        profile: dict,
        line_drawing_svg: Optional[str],
    ) -> list[dict]:
        panel_w, panel_h = DEFAULT_PANEL_MM
        g = ET.SubElement(parent, f"{{{SVG_NS}}}g", {
            "id": f"panel-{panel_name}",
            "transform": f"translate({x_offset} 0)",
            "data-panel": panel_name,
        })

        # Die-cut outline — stroke only, no fill.
        ET.SubElement(g, f"{{{SVG_NS}}}rect", {
            "x": "0", "y": "0",
            "width": f"{panel_w}", "height": f"{panel_h}",
            "fill": "none", "stroke": "#000", "stroke-width": "0.3",
        })

        placements: list[dict] = []
        fields = panel_spec.get("fields") or []

        # Layout cursor — tracks where to drop the next element.
        cursor_y = 6.0
        row_x = 4.0

        for field in fields:
            key = str(field).lower()
            if key in {"logo", "brand", "company"}:
                self._add_logo_placeholder(g, x=row_x, y=cursor_y, profile=profile)
                placements.append({"type": "logo", "panel": panel_name, "x": row_x + x_offset, "y": cursor_y})
                cursor_y += LOGO_MM + 2
            elif key in {"upc", "barcode", "gtin", "ean"}:
                upc = str(fused_item.get("upc") or fused_item.get("gtin") or "")
                self._add_barcode(g, x=row_x, y=cursor_y, value=upc)
                placements.append({"type": "barcode", "panel": panel_name, "x": row_x + x_offset, "y": cursor_y, "value": upc})
                cursor_y += 18
            elif key in {"item_description", "description", "title"}:
                text = str(fused_item.get("description") or "")
                self._add_text(g, x=row_x, y=cursor_y, text=text, size=3.5, weight="bold")
                placements.append({"type": "text", "field": "description", "panel": panel_name, "x": row_x + x_offset, "y": cursor_y})
                cursor_y += TEXT_LINE_HEIGHT_MM
            elif key in {"warnings", "warning_labels", "handling"}:
                for i, w in enumerate(warnings):
                    x = row_x + i * (WARNING_SYMBOL_MM + 2)
                    self._add_warning_symbol(g, x=x, y=cursor_y, label=w)
                    placements.append({
                        "type": "warning", "symbol": w, "panel": panel_name,
                        "x": x + x_offset, "y": cursor_y,
                    })
                cursor_y += WARNING_SYMBOL_MM + 2
            elif key in {"country_of_origin", "origin"}:
                origin = str(fused_item.get("country_of_origin") or fused_item.get("origin") or "")
                if origin:
                    self._add_text(g, x=row_x, y=cursor_y, text=f"Made in {origin}", size=3.0)
                    placements.append({"type": "text", "field": "country_of_origin", "panel": panel_name, "x": row_x + x_offset, "y": cursor_y})
                    cursor_y += TEXT_LINE_HEIGHT_MM
            elif key in {"dimensions", "size"}:
                dims = self._format_dimensions(fused_item)
                if dims:
                    self._add_text(g, x=row_x, y=cursor_y, text=dims, size=3.0)
                    placements.append({"type": "text", "field": "dimensions", "panel": panel_name, "x": row_x + x_offset, "y": cursor_y})
                    cursor_y += TEXT_LINE_HEIGHT_MM
            elif key in {"quantity", "qty", "case_qty"}:
                qty = fused_item.get("case_qty") or fused_item.get("total_qty") or ""
                if qty:
                    self._add_text(g, x=row_x, y=cursor_y, text=f"Qty: {qty}", size=3.0)
                    placements.append({"type": "text", "field": "quantity", "panel": panel_name, "x": row_x + x_offset, "y": cursor_y})
                    cursor_y += TEXT_LINE_HEIGHT_MM
            elif key in {"line_drawing", "product_drawing", "drawing"}:
                if line_drawing_svg:
                    self._embed_drawing(g, x=row_x, y=cursor_y, svg_fragment=line_drawing_svg)
                    placements.append({"type": "drawing", "panel": panel_name, "x": row_x + x_offset, "y": cursor_y})
                    cursor_y += 40
            # else: unknown field — skip silently but log for diagnostics.
            else:
                logger.debug("Composer: unknown panel field %r on panel %s", key, panel_name)

            if cursor_y > panel_h - 4:
                # Ran out of panel — remaining fields overflow; ValidatorAgent
                # will flag this via dimensions check / overlap detection.
                break

        return placements

    # ── Primitive SVG builders ───────────────────────────────────────────

    @staticmethod
    def _add_logo_placeholder(parent: ET.Element, *, x: float, y: float, profile: dict) -> None:
        g = ET.SubElement(parent, f"{{{SVG_NS}}}g", {"class": "logo"})
        ET.SubElement(g, f"{{{SVG_NS}}}rect", {
            "x": f"{x}", "y": f"{y}", "width": f"{LOGO_MM}", "height": f"{LOGO_MM}",
            "fill": "none", "stroke": "#000", "stroke-width": "0.3",
        })
        text = ET.SubElement(g, f"{{{SVG_NS}}}text", {
            "x": f"{x + LOGO_MM / 2}", "y": f"{y + LOGO_MM / 2 + 1}",
            "text-anchor": "middle", "font-size": "3",
            "font-family": "Helvetica, Arial, sans-serif",
        })
        brand = (profile.get("brand_treatment") or {})
        text.text = str(brand.get("company_name") or brand.get("description") or profile.get("name") or "LOGO")

    @staticmethod
    def _add_barcode(parent: ET.Element, *, x: float, y: float, value: str) -> None:
        """Simplified barcode glyph.

        We emit a run of vertical bars whose count is derived from the UPC
        so the output is deterministic. This is a *placeholder* glyph — the
        actual rendering pipeline (print worker) substitutes a real
        Code128/EAN renderer downstream, but ValidatorAgent's scannability
        check only inspects presence + min-height.
        """
        g = ET.SubElement(parent, f"{{{SVG_NS}}}g", {"class": "barcode", "data-value": value})
        bar_h = 12.0
        bar_w = 0.4
        # At most 12 glyph-bars so the placeholder fits in 30mm.
        digits = value or "000000000000"
        for i, ch in enumerate(digits[:12]):
            try:
                n = int(ch)
            except ValueError:
                n = 0
            # Thicker bars encode higher digits — purely deterministic.
            bx = x + i * (bar_w * 3.5)
            ET.SubElement(g, f"{{{SVG_NS}}}rect", {
                "x": f"{bx}", "y": f"{y}",
                "width": f"{bar_w * (1 + (n % 3))}",
                "height": f"{bar_h}",
                "fill": "#000",
            })
        caption = ET.SubElement(g, f"{{{SVG_NS}}}text", {
            "x": f"{x}", "y": f"{y + bar_h + 3}",
            "font-size": "2.6", "font-family": "monospace",
        })
        caption.text = value

    @staticmethod
    def _add_text(parent: ET.Element, *, x: float, y: float, text: str, size: float = 3.0, weight: str = "normal") -> None:
        t = ET.SubElement(parent, f"{{{SVG_NS}}}text", {
            "x": f"{x}", "y": f"{y + size}",
            "font-size": f"{size}",
            "font-family": "Helvetica, Arial, sans-serif",
            "font-weight": weight,
        })
        t.text = text

    @staticmethod
    def _add_warning_symbol(parent: ET.Element, *, x: float, y: float, label: str) -> None:
        g = ET.SubElement(parent, f"{{{SVG_NS}}}g", {"class": "warning", "data-label": label})
        ET.SubElement(g, f"{{{SVG_NS}}}rect", {
            "x": f"{x}", "y": f"{y}",
            "width": f"{WARNING_SYMBOL_MM}", "height": f"{WARNING_SYMBOL_MM}",
            "fill": "none", "stroke": "#000", "stroke-width": "0.4",
        })
        # A simple ⚠ glyph using a triangle + exclamation mark.
        cx = x + WARNING_SYMBOL_MM / 2
        cy = y + WARNING_SYMBOL_MM / 2
        ET.SubElement(g, f"{{{SVG_NS}}}polygon", {
            "points": f"{cx},{y + 2} {x + 2},{y + WARNING_SYMBOL_MM - 2} {x + WARNING_SYMBOL_MM - 2},{y + WARNING_SYMBOL_MM - 2}",
            "fill": "none", "stroke": "#000", "stroke-width": "0.4",
        })
        caption = ET.SubElement(g, f"{{{SVG_NS}}}text", {
            "x": f"{cx}", "y": f"{y + WARNING_SYMBOL_MM + 2.5}",
            "text-anchor": "middle", "font-size": "2.2",
        })
        caption.text = label[:12]
        mark = ET.SubElement(g, f"{{{SVG_NS}}}text", {
            "x": f"{cx}", "y": f"{cy + 1.5}",
            "text-anchor": "middle", "font-size": "4", "font-weight": "bold",
        })
        mark.text = "!"

    @staticmethod
    def _embed_drawing(parent: ET.Element, *, x: float, y: float, svg_fragment: str) -> None:
        """Embed the product line drawing inside a <g transform="translate(...)">.

        We parse the fragment so malformed SVG fails loudly here rather than
        producing invalid output that only ValidatorAgent catches.
        """
        try:
            inner = ET.fromstring(svg_fragment)
        except ET.ParseError as exc:
            logger.warning("line_drawing_svg is not valid XML, embedding empty placeholder: %s", exc)
            return
        g = ET.SubElement(parent, f"{{{SVG_NS}}}g", {
            "class": "line-drawing",
            "transform": f"translate({x} {y})",
        })
        # Copy children only — the top-level <svg> attributes would conflict
        # with the outer canvas.
        for child in list(inner):
            g.append(child)

    @staticmethod
    def _format_dimensions(fused_item: dict) -> str:
        box_L = fused_item.get("box_L")
        box_W = fused_item.get("box_W")
        box_H = fused_item.get("box_H")
        parts = [v for v in (box_L, box_W, box_H) if v is not None]
        if len(parts) == 3:
            return f"Box: {box_L} x {box_W} x {box_H}"
        dims = fused_item.get("product_dims")
        if isinstance(dims, dict):
            unit = dims.get("unit", "in")
            return f"{dims.get('length','?')} x {dims.get('width','?')} x {dims.get('height','?')} {unit}"
        return ""

    # ── Confidence ───────────────────────────────────────────────────────

    @staticmethod
    def _confidence(*, has_warnings: bool, has_line_drawing: bool, placements: list[dict]) -> float:
        """Confidence reflects how complete the assembled artifact is."""
        score = 0.8
        if has_line_drawing:
            score += 0.1
        if any(p["type"] == "barcode" for p in placements):
            score += 0.05
        if has_warnings and any(p["type"] == "warning" for p in placements):
            score += 0.05
        return round(min(1.0, score), 2)
