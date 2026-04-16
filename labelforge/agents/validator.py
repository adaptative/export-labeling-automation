"""Validator Agent (TASK-035, Sprint-12).

Runs a suite of quality checks on the composed die-cut SVG and produces a
:class:`ValidationReport`. Advances the item to ``VALIDATED`` on success;
triggers HiTL on any *critical* failure (SVG invalid, required field
missing, barcode unreadable, carton dimensions mismatched).

The agent is fully deterministic — zero LLM calls. Every check is pure
XPath / XML-tree inspection plus a handful of geometric assertions
expressed as axis-aligned bounding-box overlap tests.

Input::

    {
        "die_cut_svg": "<svg .../>",        # Output of ComposerAgent (required)
        "fused_item": {...},                 # FusedItem dict (required)
        "required_fields": ["upc", ...],     # from ImporterProfile / rules
        "expected_dimensions_mm": {"width": 130.0, "height": 80.0},
        "placements": [{...}, ...],          # Output of ComposerAgent (optional, improves overlap check)
    }

Output :class:`AgentResult.data`::

    {
        "validation_report": ValidationReport.dict(),
        "item_state": "VALIDATED",
        "issues": [str, ...],
        "critical_count": int,
    }
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Optional

from labelforge.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)

SVG_NS = "http://www.w3.org/2000/svg"
_SVG_NS_PREFIX = f"{{{SVG_NS}}}"

# A barcode glyph is considered scannable when it has at least this many bars
# AND they are at least this tall. Both numbers line up with Code128 minimums.
MIN_BARCODE_BARS = 8
MIN_BARCODE_HEIGHT_MM = 10.0

# Minimum legible font size for regulatory-text fields (matches 6pt rule
# used by most label compliance regimes).
MIN_READABLE_FONT_SIZE = 2.1  # mm ≈ 6pt

# Tolerance for carton dimension comparisons, in mm.
DIMENSION_TOLERANCE_MM = 1.0


class ValidatorAgent(BaseAgent):
    """Final QA checks on the composed SVG."""

    agent_id = "agent-6.11-validator"

    def __init__(self) -> None:
        pass

    async def execute(self, input_data: dict) -> AgentResult:
        svg_text: str = input_data.get("die_cut_svg") or ""
        fused: dict = input_data.get("fused_item") or {}
        required_fields: list[str] = [str(f).lower() for f in (input_data.get("required_fields") or [])]
        expected_dims: dict = input_data.get("expected_dimensions_mm") or {}
        placements: list[dict] = list(input_data.get("placements") or [])

        item_no = str(fused.get("item_no") or "UNKNOWN")

        issues: list[str] = []
        critical: list[str] = []

        # 1. SVG validity ────────────────────────────────────────────────
        svg_valid, root = self._parse_svg(svg_text, critical)

        # 2. Required fields ─────────────────────────────────────────────
        required_fields_present = True
        if svg_valid and root is not None:
            required_fields_present = self._check_required_fields(
                root, required_fields, fused, critical
            )

        # 3. Label readability ───────────────────────────────────────────
        labels_readable = True
        if svg_valid and root is not None:
            labels_readable = self._check_readability(root, issues)

        # 4. Barcode scannability ────────────────────────────────────────
        barcode_scannable = True
        if svg_valid and root is not None:
            barcode_scannable = self._check_barcode(root, fused, critical)

        # 5. Dimensions match ────────────────────────────────────────────
        dimensions_match = True
        if svg_valid and root is not None:
            dimensions_match = self._check_dimensions(root, expected_dims, critical)

        # 6. Overlap detection ───────────────────────────────────────────
        no_overlaps = True
        if placements:
            no_overlaps = self._check_overlaps(placements, issues)
        elif svg_valid and root is not None:
            no_overlaps = self._check_overlaps_from_tree(root, issues)

        passed = all([
            svg_valid, required_fields_present, labels_readable,
            barcode_scannable, dimensions_match, no_overlaps,
        ])

        report = {
            "item_no": item_no,
            "svg_valid": svg_valid,
            "required_fields_present": required_fields_present,
            "labels_readable": labels_readable,
            "barcode_scannable": barcode_scannable,
            "dimensions_match": dimensions_match,
            "no_overlaps": no_overlaps,
            "passed": passed,
            "issues": issues + critical,
        }

        needs_hitl = bool(critical)
        confidence = self._confidence(report)

        logger.info(
            "Validator: item=%s passed=%s critical=%d issues=%d confidence=%.2f",
            item_no, passed, len(critical), len(issues), confidence,
        )

        return AgentResult(
            success=passed and not needs_hitl,
            data={
                "validation_report": report,
                "item_state": "VALIDATED" if passed else "COMPOSED",
                "issues": issues,
                "critical_count": len(critical),
            },
            confidence=confidence,
            needs_hitl=needs_hitl,
            hitl_reason="; ".join(critical) if critical else None,
            cost=0.0,
        )

    # ── Check helpers ────────────────────────────────────────────────────

    @staticmethod
    def _parse_svg(svg_text: str, critical: list[str]) -> tuple[bool, Optional[ET.Element]]:
        if not svg_text.strip():
            critical.append("SVG is empty")
            return False, None
        try:
            root = ET.fromstring(svg_text)
        except ET.ParseError as exc:
            critical.append(f"SVG is not valid XML: {exc}")
            return False, None
        tag = root.tag
        if not (tag == f"{_SVG_NS_PREFIX}svg" or tag == "svg"):
            critical.append(f"Root element is <{tag}>, expected <svg>")
            return False, None
        return True, root

    @staticmethod
    def _iter_all(root: ET.Element) -> list[ET.Element]:
        return list(root.iter())

    def _check_required_fields(
        self, root: ET.Element, required: list[str], fused: dict, critical: list[str]
    ) -> bool:
        if not required:
            return True
        all_text = " ".join(
            (e.text or "") + " " + " ".join(f"{k}={v}" for k, v in e.attrib.items())
            for e in self._iter_all(root)
        ).lower()

        missing: list[str] = []
        for field in required:
            key = field.lower()
            # Special-case the fields we know how to probe.
            if key in {"upc", "gtin", "ean", "barcode"}:
                value = str(fused.get("upc") or fused.get("gtin") or "").strip()
                if value and value.lower() not in all_text:
                    missing.append(key)
                elif not value:
                    missing.append(key)
            elif key in {"description", "item_description"}:
                desc = str(fused.get("description") or "").strip()
                if desc and desc.lower() not in all_text:
                    missing.append(key)
            elif key in {"logo", "brand"}:
                if "logo" not in all_text and "brand" not in all_text:
                    missing.append(key)
            elif key in {"warnings", "warning_labels", "handling"}:
                if "warning" not in all_text:
                    missing.append(key)
            elif key in {"country_of_origin", "origin"}:
                origin = str(fused.get("country_of_origin") or fused.get("origin") or "").lower()
                if origin and origin not in all_text:
                    missing.append(key)
                elif not origin:
                    # Regulator requires origin even if profile didn't provide one.
                    missing.append(key)
            else:
                # Generic fall-back: look for the field keyword anywhere.
                if key.replace("_", " ") not in all_text and key not in all_text:
                    missing.append(key)

        if missing:
            critical.append(f"Required fields missing: {', '.join(sorted(set(missing)))}")
            return False
        return True

    @staticmethod
    def _check_readability(root: ET.Element, issues: list[str]) -> bool:
        ok = True
        for text in root.iter(f"{_SVG_NS_PREFIX}text"):
            size_str = text.attrib.get("font-size")
            if size_str is None:
                continue
            try:
                size = float(re.sub(r"[^0-9.\-]", "", size_str) or "0")
            except ValueError:
                continue
            if 0 < size < MIN_READABLE_FONT_SIZE:
                issues.append(
                    f"Text '{(text.text or '').strip()[:30]}' uses font-size {size}mm "
                    f"below {MIN_READABLE_FONT_SIZE}mm minimum"
                )
                ok = False
        return ok

    @staticmethod
    def _check_barcode(root: ET.Element, fused: dict, critical: list[str]) -> bool:
        upc = str(fused.get("upc") or fused.get("gtin") or "").strip()
        if not upc:
            # Not every item has a barcode; only flag when present but bad.
            return True

        # Find the barcode group (class="barcode" or data-value attr).
        barcodes = [
            g for g in root.iter(f"{_SVG_NS_PREFIX}g")
            if g.attrib.get("class") == "barcode"
            or g.attrib.get("data-value") == upc
        ]
        if not barcodes:
            critical.append(f"No barcode glyph found for UPC {upc}")
            return False

        for bc in barcodes:
            bars = [r for r in bc.iter(f"{_SVG_NS_PREFIX}rect")]
            if len(bars) < MIN_BARCODE_BARS:
                critical.append(
                    f"Barcode for UPC {upc} has {len(bars)} bars, below {MIN_BARCODE_BARS} minimum"
                )
                return False
            # Heights
            heights: list[float] = []
            for r in bars:
                try:
                    heights.append(float(r.attrib.get("height", "0") or "0"))
                except ValueError:
                    continue
            if not heights or max(heights, default=0.0) < MIN_BARCODE_HEIGHT_MM:
                critical.append(
                    f"Barcode for UPC {upc} max bar height {max(heights, default=0.0)}mm "
                    f"below {MIN_BARCODE_HEIGHT_MM}mm minimum"
                )
                return False
            # Caption value must match the UPC.
            caption_ok = False
            for t in bc.iter(f"{_SVG_NS_PREFIX}text"):
                if (t.text or "").strip() == upc:
                    caption_ok = True
                    break
            if not caption_ok:
                critical.append(f"Barcode caption does not match UPC {upc}")
                return False
        return True

    @staticmethod
    def _check_dimensions(root: ET.Element, expected: dict, critical: list[str]) -> bool:
        if not expected:
            return True
        exp_w = expected.get("width")
        exp_h = expected.get("height")
        try:
            actual_w = ValidatorAgent._parse_mm(root.attrib.get("width", ""))
            actual_h = ValidatorAgent._parse_mm(root.attrib.get("height", ""))
        except ValueError:
            critical.append("SVG width/height attributes are not parseable")
            return False

        mismatches: list[str] = []
        if exp_w is not None and abs((actual_w or 0) - float(exp_w)) > DIMENSION_TOLERANCE_MM:
            mismatches.append(f"width {actual_w}mm vs expected {exp_w}mm")
        if exp_h is not None and abs((actual_h or 0) - float(exp_h)) > DIMENSION_TOLERANCE_MM:
            mismatches.append(f"height {actual_h}mm vs expected {exp_h}mm")
        if mismatches:
            critical.append("Dimensions mismatch: " + "; ".join(mismatches))
            return False
        return True

    @staticmethod
    def _parse_mm(value: str) -> Optional[float]:
        if not value:
            return None
        match = re.match(r"^\s*([0-9.]+)\s*mm?\s*$", value)
        if not match:
            # Try plain float (viewBox units, treated as mm since Composer uses mm)
            try:
                return float(value)
            except ValueError:
                return None
        return float(match.group(1))

    @staticmethod
    def _check_overlaps(placements: list[dict], issues: list[str]) -> bool:
        ok = True
        by_panel: dict[str, list[dict]] = {}
        for p in placements:
            by_panel.setdefault(str(p.get("panel", "")), []).append(p)

        for panel, items in by_panel.items():
            for i, a in enumerate(items):
                for b in items[i + 1:]:
                    if ValidatorAgent._bboxes_overlap(a, b):
                        issues.append(
                            f"Overlap on panel '{panel}': "
                            f"{a.get('type')} @ ({a.get('x')}, {a.get('y')}) "
                            f"vs {b.get('type')} @ ({b.get('x')}, {b.get('y')})"
                        )
                        ok = False
        return ok

    @staticmethod
    def _bboxes_overlap(a: dict, b: dict) -> bool:
        def _box(p: dict) -> tuple[float, float, float, float]:
            x = float(p.get("x", 0) or 0)
            y = float(p.get("y", 0) or 0)
            # Rough element sizes per type — good enough to catch gross collisions.
            size_map = {
                "logo":    (24.0, 24.0),
                "barcode": (24.0, 15.0),
                "warning": (14.0, 14.0),
                "text":    (40.0, 4.5),
                "drawing": (40.0, 30.0),
            }
            w, h = size_map.get(str(p.get("type")), (8.0, 4.5))
            return (x, y, x + w, y + h)

        ax1, ay1, ax2, ay2 = _box(a)
        bx1, by1, bx2, by2 = _box(b)
        # Allow touching edges (strict inequality on overlap).
        return not (ax2 <= bx1 or bx2 <= ax1 or ay2 <= by1 or by2 <= ay1)

    @staticmethod
    def _check_overlaps_from_tree(root: ET.Element, issues: list[str]) -> bool:
        """Fallback overlap detection from <rect> bounding boxes when no
        explicit placement list is passed.

        We look at every `<rect>` inside a panel `<g>` and compare pairwise —
        O(n²) but n is small (typically <30 elements per panel).
        """
        ok = True
        for panel_g in root.iter(f"{_SVG_NS_PREFIX}g"):
            if not panel_g.attrib.get("data-panel"):
                continue
            rects: list[tuple[float, float, float, float]] = []
            for r in panel_g.iter(f"{_SVG_NS_PREFIX}rect"):
                try:
                    x = float(r.attrib.get("x", 0) or 0)
                    y = float(r.attrib.get("y", 0) or 0)
                    w = float(r.attrib.get("width", 0) or 0)
                    h = float(r.attrib.get("height", 0) or 0)
                except ValueError:
                    continue
                # Ignore the panel outline itself (it's the full panel size).
                if w > 100 or h > 70:
                    continue
                rects.append((x, y, x + w, y + h))
            for i, a in enumerate(rects):
                for b in rects[i + 1:]:
                    if not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]):
                        issues.append(
                            f"Overlapping rects on panel "
                            f"{panel_g.attrib.get('data-panel')}: {a} vs {b}"
                        )
                        ok = False
        return ok

    @staticmethod
    def _confidence(report: dict) -> float:
        checks = [
            report["svg_valid"], report["required_fields_present"],
            report["labels_readable"], report["barcode_scannable"],
            report["dimensions_match"], report["no_overlaps"],
        ]
        passed = sum(1 for c in checks if c)
        return round(passed / len(checks), 2)
