"""Operator-override path for ``validate_output_activity``.

Operators hit duplicate 'Required fields missing' HiTL threads on every
item that shares the same gap (e.g. prop65 warning on items shipping
outside CA). The chat bot's validator handler advertises "(b) accept
the failure with an override note" as a resolution option, and the
``_VALIDATOR_PATCH_KEYS`` allowlist now includes ``validation_override``
and ``override_note``. This test pins the activity-side behaviour: when
the fused item carries ``validation_override=True``, the validator
activity must skip HiTL for that item, record the override in the
per-item report, and allow the overall activity to succeed (so the item
transitions to VALIDATED instead of staying HUMAN_BLOCKED).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from labelforge.workflows.order_processor import (
    ActivityInput,
    validate_output_activity,
)


class _FakeResult:
    def __init__(self) -> None:
        self.data = {
            "validation_report": {"failures": ["required field missing"]},
            "critical_count": 1,
        }
        self.needs_hitl = True
        self.hitl_reason = "required field missing"


@pytest.mark.asyncio
async def test_validation_override_short_circuits_hitl():
    """With ``validation_override=True`` on the item, the activity
    reports success even though the underlying ValidatorAgent would
    have raised HiTL — the override note is preserved in the report.
    """
    payload = {
        "fused_items": [
            {
                "item_no": "21496-02",
                "validation_override": True,
                "override_note": "duplicate issue, accepted by operator",
            },
        ],
        "composed_artifacts": {
            "21496-02": {"die_cut_svg": "<svg/>", "placements": []},
        },
        "importer_profile": {},
    }

    with patch(
        "labelforge.agents.validator.ValidatorAgent.execute",
        new=AsyncMock(return_value=_FakeResult()),
    ):
        out = await validate_output_activity(ActivityInput(
            item_id="itm-1",
            order_id="ORD-X",
            tenant_id="t1",
            payload=payload,
        ))

    assert out.success is True
    assert out.needs_hitl is False
    assert out.new_state == "VALIDATED"
    report = out.data["validation_reports"]["21496-02"]
    assert report.get("override_accepted") is True
    assert report.get("override_note") == "duplicate issue, accepted by operator"


@pytest.mark.asyncio
async def test_without_override_still_raises_hitl():
    """Sanity: the default path (no override key set) still funnels the
    item into HiTL exactly as before."""
    payload = {
        "fused_items": [{"item_no": "21496-02"}],
        "composed_artifacts": {
            "21496-02": {"die_cut_svg": "<svg/>", "placements": []},
        },
        "importer_profile": {},
    }

    with patch(
        "labelforge.agents.validator.ValidatorAgent.execute",
        new=AsyncMock(return_value=_FakeResult()),
    ):
        out = await validate_output_activity(ActivityInput(
            item_id="itm-1",
            order_id="ORD-X",
            tenant_id="t1",
            payload=payload,
        ))

    assert out.needs_hitl is True
    assert out.success is False
    assert "21496-02" in (out.hitl_reason or "")
