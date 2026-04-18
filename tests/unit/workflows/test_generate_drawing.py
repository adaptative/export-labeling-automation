"""generate_drawing_activity — wires ProductImageProcessorAgent into
the pipeline so Composer actually receives line_drawing SVGs.

Before this wiring the activity was a no-op stub that just flipped
state to DRAWING_GENERATED and passed the payload through. Composer
then ran with ``line_drawing_svg=None`` and emitted die-cut labels
with a blank drawing frame.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from labelforge.workflows.order_processor import (
    ActivityInput,
    ItemState,
    generate_drawing_activity,
)


def _fake_result(images):
    r = MagicMock()
    r.data = {"images": images}
    return r


@pytest.mark.asyncio
async def test_no_pdf_docs_returns_success_with_empty_drawings():
    """No PDFs on the order: activity succeeds, drawings dict is empty,
    state advances to DRAWING_GENERATED — pipeline keeps moving."""
    with patch(
        "labelforge.db.session.async_session_factory",
    ) as mock_factory:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_factory.return_value.__aenter__.return_value = mock_session

        out = await generate_drawing_activity(ActivityInput(
            item_id="itm-1",
            order_id="ORD-X",
            tenant_id="t1",
            payload={"fused_items": [{"item_no": "A1"}]},
        ))

    assert out.success is True
    assert out.new_state == ItemState.DRAWING_GENERATED.value
    assert out.data.get("line_drawings_svg") == {}


@pytest.mark.asyncio
async def test_positional_assignment_when_no_item_no_in_ref():
    """Drawings get assigned by sorted item_no ↔ image index when
    image_ref doesn't embed the item_no."""
    doc = MagicMock()
    doc.filename = "po.pdf"
    doc.s3_key = "ORD-X/po.pdf"

    with patch("labelforge.db.session.async_session_factory") as mock_factory, \
         patch("labelforge.api.v1.documents.get_blob_store") as mock_store_f, \
         patch(
             "labelforge.agents.product_image_processor.ProductImageProcessorAgent.execute",
             new=AsyncMock(return_value=_fake_result([
                 {"image_ref": "page-1-img-1", "svg": "<svg>A</svg>"},
                 {"image_ref": "page-2-img-1", "svg": "<svg>B</svg>"},
             ])),
         ):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [doc]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_factory.return_value.__aenter__.return_value = mock_session

        store = MagicMock()
        store.download = AsyncMock(return_value=b"%PDF-stub")
        mock_store_f.return_value = store

        out = await generate_drawing_activity(ActivityInput(
            item_id="itm-1",
            order_id="ORD-X",
            tenant_id="t1",
            payload={
                "fused_items": [
                    {"item_no": "B2"},
                    {"item_no": "A1"},
                ],
            },
        ))

    assert out.success
    draws = out.data["line_drawings_svg"]
    # Sorted item_no order is A1, B2 — positional with 2 images:
    assert draws["A1"] == "<svg>A</svg>"
    assert draws["B2"] == "<svg>B</svg>"


@pytest.mark.asyncio
async def test_item_no_substring_in_ref_takes_precedence():
    """When an image_ref contains the item_no, that image sticks to
    that item regardless of position."""
    doc = MagicMock()
    doc.filename = "po.pdf"
    doc.s3_key = "ORD-X/po.pdf"

    with patch("labelforge.db.session.async_session_factory") as mock_factory, \
         patch("labelforge.api.v1.documents.get_blob_store") as mock_store_f, \
         patch(
             "labelforge.agents.product_image_processor.ProductImageProcessorAgent.execute",
             new=AsyncMock(return_value=_fake_result([
                 {"image_ref": "B2-hero", "svg": "<svg>B-HERO</svg>"},
                 {"image_ref": "img-A1", "svg": "<svg>A-HERO</svg>"},
             ])),
         ):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [doc]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_factory.return_value.__aenter__.return_value = mock_session

        store = MagicMock()
        store.download = AsyncMock(return_value=b"%PDF-stub")
        mock_store_f.return_value = store

        out = await generate_drawing_activity(ActivityInput(
            item_id="itm-1",
            order_id="ORD-X",
            tenant_id="t1",
            payload={
                "fused_items": [
                    {"item_no": "A1"},
                    {"item_no": "B2"},
                ],
            },
        ))

    draws = out.data["line_drawings_svg"]
    assert draws["A1"] == "<svg>A-HERO</svg>"
    assert draws["B2"] == "<svg>B-HERO</svg>"


@pytest.mark.asyncio
async def test_existing_drawings_are_preserved():
    """Re-running Drawings after a chat-driven patch on
    line_drawing_svg must NOT overwrite operator edits."""
    existing = {"A1": "<svg>OPERATOR-EDIT</svg>"}
    # No patches needed — short-circuit returns immediately.
    out = await generate_drawing_activity(ActivityInput(
        item_id="itm-1",
        order_id="ORD-X",
        tenant_id="t1",
        payload={
            "fused_items": [{"item_no": "A1"}],
            "line_drawings_svg": existing,
        },
    ))
    assert out.data["line_drawings_svg"] == existing
    assert out.new_state == ItemState.DRAWING_GENERATED.value
