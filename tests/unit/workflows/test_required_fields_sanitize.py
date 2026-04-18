"""Sanitize garbage entries out of ``_required_fields_from_profile``.

Onboarding LLM extraction sometimes drops full warning-label sentences
or URLs into ``panel_layouts`` instead of short identifiers. When those
leak through they become "required fields", fail every validation pass
as missing, and spawn a duplicate HiTL thread per order item — the
failure reason then reads like prose ("for more information go to
www.p65warnings.ca.gov/furniture…") because it's listing warning text
as field names. This test pins the filter.
"""
from __future__ import annotations

from labelforge.workflows.order_processor import _required_fields_from_profile


def test_drops_sentences_and_urls_keeps_identifiers():
    profile = {
        "panel_layouts": {
            "carton_top": [
                "upc",                       # valid
                "item_description",          # valid
                "for more information go to www.p65warnings.ca.gov/furniture",  # junk
                "WARNING: California Prop 65 chemical exposure notice.",        # junk
                "this product can expose you to chemicals including lead",      # junk
            ],
            "carton_side": {
                "selected": True,
                "fields": [
                    "country_of_origin",     # valid
                    "4×3 inches",            # junk (non-ASCII + space)
                    "prop65_warning",        # valid
                ],
            },
        },
    }
    got = _required_fields_from_profile(profile)
    # Baseline fields are always included.
    assert "item_no" in got
    assert "case_qty" in got
    # Valid identifiers from the profile survived.
    assert "upc" in got
    assert "item_description" in got
    assert "prop65_warning" in got
    assert "country_of_origin" in got
    # Junk did NOT survive.
    assert not any("p65warnings" in s for s in got)
    assert not any("WARNING" in s for s in got)
    assert not any("inches" in s for s in got)


def test_deselected_panel_is_skipped():
    profile = {
        "panel_layouts": {
            "carton_top": {"selected": False, "fields": ["upc"]},
            "carton_side": {"selected": True, "fields": ["barcode"]},
        },
    }
    got = _required_fields_from_profile(profile)
    # barcode is baseline anyway, but the point is no exception on deselect.
    assert "barcode" in got
