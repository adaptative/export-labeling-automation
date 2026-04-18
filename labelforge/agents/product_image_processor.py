"""Product Image Processor Agent (Agent 6.8 — TASK-026).

Extracts product images from Purchase-Order PDFs, preprocesses each one
(greyscale + autocontrast + threshold), vectorises the result into a
valid SVG string, and scores confidence per image.  Aggregate confidence
below :data:`CONFIDENCE_HITL_THRESHOLD` triggers HiTL.

Pipeline
--------
1. ``extract_images``  — pull embedded images from a PDF using PyMuPDF.
2. ``preprocess``      — greyscale, autocontrast, threshold to 1-bit.
3. ``vectorize``       — downsample to a small grid and emit one SVG
                         ``<rect>`` per dark cell.  This is deliberately
                         a pure-Python fallback: production installations
                         can swap in potrace by overriding ``vectorize``.
4. ``score_confidence`` — dimensions, aspect ratio, data-coverage,
                         and extraction completeness.

The agent is deterministic — no LLM calls.  ``cost`` is always ``0.0``.
"""
from __future__ import annotations

import hashlib
import io
import logging
import threading
from dataclasses import dataclass
from typing import Optional

from labelforge.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)

# F11 — in-process SHA cache for vectorised line drawings. Keyed by
# sha256(item_no + image_bytes_hash) so repeat orders for the same SKU
# skip the Potrace/downsample pass entirely. Bounded LRU-style to keep
# memory flat across long-running workers.
_VECTORIZE_CACHE: dict[str, str] = {}
_VECTORIZE_CACHE_LOCK = threading.Lock()
_VECTORIZE_CACHE_MAX = 256


def _vectorize_cache_get(key: str) -> Optional[str]:
    with _VECTORIZE_CACHE_LOCK:
        return _VECTORIZE_CACHE.get(key)


def _vectorize_cache_put(key: str, svg: str) -> None:
    with _VECTORIZE_CACHE_LOCK:
        if len(_VECTORIZE_CACHE) >= _VECTORIZE_CACHE_MAX:
            # Drop oldest entry (insertion-ordered dict → FIFO eviction).
            try:
                _VECTORIZE_CACHE.pop(next(iter(_VECTORIZE_CACHE)))
            except StopIteration:  # pragma: no cover
                pass
        _VECTORIZE_CACHE[key] = svg


def _vectorize_cache_key(item_no: str, image_bytes: bytes) -> str:
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    item_hash = hashlib.sha256((item_no or "").encode("utf-8")).hexdigest()
    return hashlib.sha256((item_hash + image_hash).encode("utf-8")).hexdigest()


def vectorize_cache_stats() -> dict:
    """Introspection hook for tests / admin UI."""
    with _VECTORIZE_CACHE_LOCK:
        return {"size": len(_VECTORIZE_CACHE), "max": _VECTORIZE_CACHE_MAX}


def vectorize_cache_clear() -> None:
    with _VECTORIZE_CACHE_LOCK:
        _VECTORIZE_CACHE.clear()

# Aggregate confidence below this threshold routes the item to HiTL.
CONFIDENCE_HITL_THRESHOLD = 0.75

# Per-image quality thresholds.
_MIN_DIMENSION_PX = 50
_MAX_ASPECT_RATIO = 10.0
_MIN_COVERAGE = 0.01
_MAX_COVERAGE = 0.70

# Vectorization grid size — caps SVG complexity regardless of input.
_VECTORIZE_GRID = 64

# Binary threshold — pixels below this greyscale value are considered "ink".
_BINARY_THRESHOLD = 128


@dataclass
class ProcessedImage:
    image_ref: str
    svg: str
    width: int
    height: int
    confidence: float
    needs_hitl: bool
    issues: list[str]

    def to_dict(self) -> dict:
        return {
            "image_ref": self.image_ref,
            "svg": self.svg,
            "width": self.width,
            "height": self.height,
            "confidence": self.confidence,
            "needs_hitl": self.needs_hitl,
            "issues": list(self.issues),
        }


# ── Public extraction helpers ────────────────────────────────────────────────


def extract_images_from_pdf(data: bytes) -> list[tuple[str, bytes]]:
    """Return ``[(image_ref, image_bytes), ...]`` for every image in the PDF.

    ``image_ref`` is formatted ``page{n}-img{idx}`` so callers can correlate
    outputs back to their source page.  Returns an empty list if PyMuPDF is
    unavailable or the PDF is unreadable.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover — library is in pyproject deps
        logger.warning("PyMuPDF not installed — cannot extract PDF images")
        return []

    out: list[tuple[str, bytes]] = []
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page_idx, page in enumerate(doc):
                for img_idx, img in enumerate(page.get_images(full=True)):
                    xref = img[0]
                    try:
                        base = doc.extract_image(xref)
                    except Exception as exc:  # pragma: no cover — malformed
                        logger.warning("extract_image(%s) failed: %s", xref, exc)
                        continue
                    out.append(
                        (f"page{page_idx + 1}-img{img_idx + 1}", base["image"])
                    )
    except Exception as exc:
        logger.warning("PDF image extraction failed: %s", exc)
        return []
    return out


def preprocess_image(data: bytes) -> Optional["_PreparedBitmap"]:
    """Open + greyscale + autocontrast + binarise.

    Returns ``None`` when the bytes aren't a decodable image so callers can
    skip gracefully instead of raising.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover — Pillow is in pyproject deps
        logger.warning("Pillow not installed — cannot preprocess image")
        return None

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        logger.warning("Image decode failed: %s", exc)
        return None

    grey = img.convert("L")
    try:
        grey = ImageOps.autocontrast(grey)
    except Exception:  # pragma: no cover — autocontrast rarely fails
        pass
    binary = grey.point(lambda v: 0 if v < _BINARY_THRESHOLD else 255, "1")
    return _PreparedBitmap(binary=binary, width=img.width, height=img.height)


def vectorize_to_svg(bitmap: "_PreparedBitmap", grid: int = _VECTORIZE_GRID) -> str:
    """Return a valid SVG string approximating the bitmap.

    The bitmap is resampled into a ``grid × grid`` matrix and each "ink"
    cell becomes a ``<rect>`` in the SVG.  Coarse but deterministic, fast,
    and dependency-free beyond Pillow.
    """
    w, h = bitmap.width, bitmap.height
    if w <= 0 or h <= 0:
        return _empty_svg(w, h)

    try:
        thumb = bitmap.binary.resize((grid, grid))
    except Exception:
        return _empty_svg(w, h)

    pixels = thumb.load()
    cell_w = w / grid
    cell_h = h / grid
    rects: list[str] = []
    for row in range(grid):
        for col in range(grid):
            v = pixels[col, row]
            # Mode "1" returns 0/255; treat 0 as ink.
            if v == 0:
                x = col * cell_w
                y = row * cell_h
                rects.append(
                    f'<rect x="{x:.2f}" y="{y:.2f}" '
                    f'width="{cell_w:.2f}" height="{cell_h:.2f}" '
                    f'fill="black"/>'
                )
    body = "".join(rects)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
        f"{body}</svg>"
    )


@dataclass
class _PreparedBitmap:
    binary: object  # PIL.Image.Image in mode "1"
    width: int
    height: int

    def coverage(self) -> float:
        """Fraction of pixels that are "ink" (0 in mode ``1``)."""
        hist = self.binary.histogram()
        if not hist:
            return 0.0
        total = sum(hist)
        if total == 0:
            return 0.0
        ink = hist[0]
        return ink / total


def _empty_svg(w: int, h: int) -> str:
    w = max(1, int(w))
    h = max(1, int(h))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w} {h}" width="{w}" height="{h}"></svg>'
    )


def score_confidence(bitmap: _PreparedBitmap) -> tuple[float, list[str]]:
    """Heuristic confidence + human-readable issues for a prepared bitmap."""
    issues: list[str] = []
    confidence = 1.0

    if bitmap.width < _MIN_DIMENSION_PX or bitmap.height < _MIN_DIMENSION_PX:
        confidence -= 0.5
        issues.append(
            f"Image too small ({bitmap.width}x{bitmap.height}, "
            f"min {_MIN_DIMENSION_PX}px)"
        )

    if bitmap.height > 0:
        aspect = bitmap.width / bitmap.height
        if aspect > _MAX_ASPECT_RATIO or aspect < 1 / _MAX_ASPECT_RATIO:
            confidence -= 0.3
            issues.append(f"Extreme aspect ratio: {aspect:.2f}")

    coverage = bitmap.coverage()
    if coverage < _MIN_COVERAGE:
        confidence -= 0.3
        issues.append(f"Near-empty image (coverage {coverage:.1%})")
    elif coverage > _MAX_COVERAGE:
        confidence -= 0.3
        issues.append(f"Over-inked image (coverage {coverage:.1%})")

    return max(0.0, confidence), issues


# ── Agent ────────────────────────────────────────────────────────────────────


class ProductImageProcessorAgent(BaseAgent):
    """Agent 6.8 — extracts & vectorises PO product images."""

    agent_id = "agent-6.8-product-image-processor"

    async def execute(self, input_data: dict) -> AgentResult:
        """Process product images from a PO.

        Input keys (at least one image source is required):
            - ``pdf_bytes`` (bytes): Purchase-Order PDF to extract images from.
            - ``images`` (list[bytes] | list[dict]): pre-extracted images.
              Dict form: ``{"ref": str, "data": bytes}``.

        Returns:
            :class:`AgentResult` whose ``data`` is::

                {
                    "images": [ProcessedImage.to_dict(), ...],
                    "image_count": int,
                    "aggregate_confidence": float,
                }

            ``success`` is ``False`` and ``needs_hitl`` is ``True`` whenever
            aggregate confidence drops below
            :data:`CONFIDENCE_HITL_THRESHOLD` or no images could be
            processed.
        """
        sources = self._collect_sources(input_data)
        processed: list[ProcessedImage] = []
        item_no = str(input_data.get("item_no") or "")

        for ref, raw in sources:
            bitmap = preprocess_image(raw)
            if bitmap is None:
                processed.append(
                    ProcessedImage(
                        image_ref=ref,
                        svg=_empty_svg(1, 1),
                        width=0,
                        height=0,
                        confidence=0.0,
                        needs_hitl=True,
                        issues=["Could not decode image"],
                    )
                )
                continue

            confidence, issues = score_confidence(bitmap)
            # F11 — SHA cache so repeat orders for the same SKU don't
            # re-run the vectorization path. Cache key combines the
            # item identifier with the raw image bytes so two SKUs that
            # share an identical image still each get a cache entry.
            cache_key = _vectorize_cache_key(item_no, raw)
            cached = _vectorize_cache_get(cache_key)
            if cached is not None:
                svg = cached
            else:
                svg = vectorize_to_svg(bitmap)
                _vectorize_cache_put(cache_key, svg)
            processed.append(
                ProcessedImage(
                    image_ref=ref,
                    svg=svg,
                    width=bitmap.width,
                    height=bitmap.height,
                    confidence=confidence,
                    needs_hitl=confidence < CONFIDENCE_HITL_THRESHOLD,
                    issues=issues,
                )
            )

        if not processed:
            return AgentResult(
                success=False,
                data={"images": [], "image_count": 0, "aggregate_confidence": 0.0},
                confidence=0.0,
                needs_hitl=True,
                hitl_reason="No images could be extracted",
                cost=0.0,
            )

        aggregate = sum(p.confidence for p in processed) / len(processed)
        needs_hitl = aggregate < CONFIDENCE_HITL_THRESHOLD or any(
            p.needs_hitl for p in processed
        )
        hitl_reason = None
        if needs_hitl:
            failing = [p for p in processed if p.needs_hitl]
            reasons = [
                f"{p.image_ref}: {'; '.join(p.issues) or 'low confidence'}"
                for p in failing[:3]
            ]
            if aggregate < CONFIDENCE_HITL_THRESHOLD:
                reasons.append(
                    f"Aggregate confidence {aggregate:.2f} below "
                    f"threshold {CONFIDENCE_HITL_THRESHOLD}"
                )
            hitl_reason = "; ".join(reasons)

        return AgentResult(
            success=not needs_hitl,
            data={
                "images": [p.to_dict() for p in processed],
                "image_count": len(processed),
                "aggregate_confidence": aggregate,
            },
            confidence=aggregate,
            needs_hitl=needs_hitl,
            hitl_reason=hitl_reason,
            cost=0.0,
        )

    # ── Internal helpers ─────────────────────────────────────────────────

    def _collect_sources(self, input_data: dict) -> list[tuple[str, bytes]]:
        """Normalise ``input_data`` into a list of ``(ref, bytes)`` tuples."""
        pdf_bytes: Optional[bytes] = input_data.get("pdf_bytes")
        images = input_data.get("images") or []

        sources: list[tuple[str, bytes]] = []
        if pdf_bytes:
            sources.extend(extract_images_from_pdf(pdf_bytes))

        for idx, entry in enumerate(images):
            if isinstance(entry, dict):
                ref = entry.get("ref") or f"img-{idx + 1}"
                raw = entry.get("data")
                if isinstance(raw, (bytes, bytearray)):
                    sources.append((ref, bytes(raw)))
            elif isinstance(entry, (bytes, bytearray)):
                sources.append((f"img-{idx + 1}", bytes(entry)))
        return sources
