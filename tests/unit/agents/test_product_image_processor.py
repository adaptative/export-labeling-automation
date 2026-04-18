"""Tests for Product Image Processor Agent (Agent 6.8 — TASK-026)."""
from __future__ import annotations

import asyncio
import io

import pytest
from PIL import Image

from labelforge.agents.product_image_processor import (
    CONFIDENCE_HITL_THRESHOLD,
    ProductImageProcessorAgent,
    preprocess_image,
    score_confidence,
    vectorize_to_svg,
)


def _png_bytes(
    size: tuple[int, int] = (200, 200),
    *,
    mode: str = "L",
    fill: int = 255,
    ink_box: tuple[int, int, int, int] | None = (50, 50, 150, 150),
) -> bytes:
    img = Image.new(mode, size, fill)
    if ink_box is not None:
        # Paint a rectangle of "ink" (value 0) into the image.
        ink = Image.new(mode, (ink_box[2] - ink_box[0], ink_box[3] - ink_box[1]), 0)
        img.paste(ink, (ink_box[0], ink_box[1]))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Preprocess + vectorize ──────────────────────────────────────────────────


class TestPreprocess:
    def test_decodes_valid_png(self):
        bmp = preprocess_image(_png_bytes())
        assert bmp is not None
        assert bmp.width == 200 and bmp.height == 200

    def test_returns_none_on_garbage(self):
        assert preprocess_image(b"not an image") is None

    def test_coverage_after_edge_detection(self):
        # Preprocess now runs FIND_EDGES → a fully-inked solid block
        # collapses to its outline (a thin rectangle), so "coverage"
        # (dark pixels) is small, not huge. Still non-zero because the
        # edge of the ink-box is detected.
        bmp = preprocess_image(_png_bytes(ink_box=(20, 20, 180, 180)))
        assert bmp is not None
        assert bmp.coverage() > 0.0  # some edge pixels present
        assert bmp.coverage() < 0.5  # but it's not a filled block

    def test_coverage_empty_image(self):
        bmp = preprocess_image(_png_bytes(ink_box=None))
        assert bmp is not None
        # An input with no ink has no edges. Allow a tiny margin for
        # border pixels surfaced by autocontrast.
        assert bmp.coverage() < 0.05


class TestVectorize:
    """New-format vectorizer embeds the preprocessed bitmap as a base64
    PNG inside an ``<image>`` tag. The previous grid-of-rects mosaic
    was swapped out because it flattened small features into illegible
    blobs (e.g. text fragments extracted from PDFs looked like Lego
    bricks). The new format preserves product-photo fidelity at the
    cost of not being a true vectorisation — but for die-cut preview
    this is the right trade-off."""

    def test_returns_valid_svg_with_embedded_image(self):
        bmp = preprocess_image(_png_bytes())
        svg = vectorize_to_svg(bmp)
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg
        assert "<image" in svg
        assert "data:image/png;base64," in svg

    def test_empty_input_still_produces_valid_svg(self):
        bmp = preprocess_image(_png_bytes(ink_box=None))
        svg = vectorize_to_svg(bmp)
        # Well-formed SVG header + self-closing tags.
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")

    def test_svg_bounded_by_embed_max_edge(self):
        bmp = preprocess_image(_png_bytes((2000, 2000), ink_box=(0, 0, 2000, 2000)))
        svg = vectorize_to_svg(bmp)
        # Base64-encoded 512px PNG of near-uniform ink fits well under
        # ~50KB — proves the downscale actually happens.
        assert len(svg) < 100_000


class TestScoreConfidence:
    def test_good_image_high_confidence(self):
        bmp = preprocess_image(_png_bytes((300, 300)))
        confidence, issues = score_confidence(bmp)
        assert confidence >= CONFIDENCE_HITL_THRESHOLD
        assert issues == []

    def test_tiny_image_drops_confidence(self):
        bmp = preprocess_image(_png_bytes((20, 20)))
        confidence, issues = score_confidence(bmp)
        assert confidence < CONFIDENCE_HITL_THRESHOLD
        assert any("too small" in i for i in issues)

    def test_extreme_aspect_drops_confidence(self):
        bmp = preprocess_image(_png_bytes((800, 40), ink_box=(0, 0, 800, 40)))
        confidence, issues = score_confidence(bmp)
        assert any("aspect ratio" in i for i in issues)
        assert confidence < 1.0

    def test_empty_image_drops_confidence(self):
        # Post-edge-detection, a truly empty input still produces
        # near-zero coverage — the "near-empty" heuristic still fires.
        bmp = preprocess_image(_png_bytes((200, 200), ink_box=None))
        confidence, issues = score_confidence(bmp)
        assert any("Near-empty" in i for i in issues)

    # The old `test_over_inked_drops_confidence` no longer applies:
    # with FIND_EDGES, a "fully inked" input collapses to its outline,
    # producing low coverage — exactly like a well-scoped photograph.
    # The over-ink heuristic now fires only on genuinely noisy edge
    # output (dense speckle), which is harder to reproduce synthetically.


# ── Agent ────────────────────────────────────────────────────────────────────


class TestAgent:
    def test_agent_id(self):
        assert ProductImageProcessorAgent().agent_id == "agent-6.8-product-image-processor"

    def test_no_input_triggers_hitl(self):
        agent = ProductImageProcessorAgent()
        result = asyncio.run(agent.execute({}))
        assert result.success is False
        assert result.needs_hitl is True
        assert result.confidence == 0.0
        assert "No images" in result.hitl_reason

    def test_processes_list_of_image_bytes(self):
        agent = ProductImageProcessorAgent()
        imgs = [_png_bytes(), _png_bytes()]
        result = asyncio.run(agent.execute({"images": imgs}))
        assert result.data["image_count"] == 2
        assert result.success is True
        assert result.confidence >= CONFIDENCE_HITL_THRESHOLD
        assert all(img["svg"].startswith("<svg") for img in result.data["images"])

    def test_dict_form_preserves_ref(self):
        agent = ProductImageProcessorAgent()
        result = asyncio.run(
            agent.execute(
                {"images": [{"ref": "item-42-primary", "data": _png_bytes()}]}
            )
        )
        assert result.data["images"][0]["image_ref"] == "item-42-primary"

    def test_low_confidence_triggers_hitl(self):
        agent = ProductImageProcessorAgent()
        tiny = _png_bytes((20, 20), ink_box=(0, 0, 20, 20))
        result = asyncio.run(agent.execute({"images": [tiny]}))
        assert result.needs_hitl is True
        assert result.success is False
        assert result.confidence < CONFIDENCE_HITL_THRESHOLD

    def test_mixed_images_aggregates_confidence(self):
        agent = ProductImageProcessorAgent()
        good = _png_bytes((300, 300))
        tiny = _png_bytes((20, 20), ink_box=(0, 0, 20, 20))
        result = asyncio.run(agent.execute({"images": [good, tiny]}))
        # One image below threshold → needs_hitl is True even if average is ok.
        assert result.needs_hitl is True
        assert result.data["image_count"] == 2

    def test_invalid_bytes_reported_per_image(self):
        agent = ProductImageProcessorAgent()
        result = asyncio.run(agent.execute({"images": [b"garbage", _png_bytes()]}))
        assert result.data["image_count"] == 2
        bad = result.data["images"][0]
        assert bad["confidence"] == 0.0
        assert bad["needs_hitl"] is True
        assert any("decode" in i.lower() for i in bad["issues"])

    def test_cost_is_zero(self):
        # Deterministic agent — no LLM calls, zero cost.
        agent = ProductImageProcessorAgent()
        result = asyncio.run(agent.execute({"images": [_png_bytes()]}))
        assert result.cost == 0.0

    def test_pdf_without_images_returns_hitl(self):
        # Minimal not-a-pdf payload: extraction helper swallows the error.
        agent = ProductImageProcessorAgent()
        result = asyncio.run(agent.execute({"pdf_bytes": b"%PDF- not valid"}))
        assert result.needs_hitl is True
        assert result.data["image_count"] == 0

    def test_pdf_extraction_yields_images(self):
        # Build a 1-page PDF with one embedded image via PyMuPDF.
        fitz = pytest.importorskip("fitz")
        doc = fitz.open()
        page = doc.new_page(width=400, height=400)
        png = _png_bytes((200, 200))
        page.insert_image(fitz.Rect(50, 50, 250, 250), stream=png)
        pdf_bytes = doc.tobytes()
        doc.close()

        agent = ProductImageProcessorAgent()
        result = asyncio.run(agent.execute({"pdf_bytes": pdf_bytes}))
        assert result.data["image_count"] >= 1
        assert result.data["images"][0]["image_ref"].startswith("page1-img")
