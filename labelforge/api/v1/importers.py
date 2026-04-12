"""Importer profile endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from labelforge.contracts import ImporterProfile

router = APIRouter(prefix="/importers", tags=["importers"])


# ── Response models ──────────────────────────────────────────────────────────


class ImporterListResponse(BaseModel):
    importers: list[ImporterProfile]
    total: int


# ── Mock data ────────────────────────────────────────────────────────────────

_MOCK_IMPORTERS: list[ImporterProfile] = [
    ImporterProfile(
        importer_id="IMP-ACME",
        brand_treatment={
            "primary_color": "#003DA5",
            "font_family": "Helvetica Neue",
            "logo_position": "top-right",
        },
        panel_layouts={
            "carton_top": ["logo", "upc", "item_description"],
            "carton_side": ["warnings", "country_of_origin", "net_weight"],
        },
        handling_symbol_rules={
            "fragile": True,
            "this_side_up": True,
            "keep_dry": False,
        },
        pi_template_mapping={
            "item_no_col": "A",
            "box_dims_col": "D",
            "cbm_col": "G",
        },
        logo_asset_hash="sha256:a1b2c3d4e5f6",
        version=3,
    ),
    ImporterProfile(
        importer_id="IMP-GLOBEX",
        brand_treatment={
            "primary_color": "#E31837",
            "font_family": "Arial",
            "logo_position": "top-left",
        },
        panel_layouts={
            "carton_top": ["logo", "item_description", "upc"],
            "carton_side": ["net_weight", "warnings", "country_of_origin"],
        },
        handling_symbol_rules={
            "fragile": False,
            "this_side_up": True,
            "keep_dry": True,
        },
        pi_template_mapping={
            "item_no_col": "B",
            "box_dims_col": "E",
            "cbm_col": "H",
        },
        logo_asset_hash="sha256:f6e5d4c3b2a1",
        version=2,
    ),
    ImporterProfile(
        importer_id="IMP-INITECH",
        brand_treatment={
            "primary_color": "#2E8B57",
            "font_family": "Roboto",
            "logo_position": "center",
        },
        panel_layouts={
            "carton_top": ["logo", "upc"],
            "carton_side": ["item_description", "warnings"],
        },
        handling_symbol_rules={
            "fragile": True,
            "this_side_up": False,
            "keep_dry": False,
        },
        pi_template_mapping=None,
        logo_asset_hash=None,
        version=1,
    ),
]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=ImporterListResponse)
async def list_importers(
    search: Optional[str] = Query(None, description="Search by importer ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ImporterListResponse:
    """List importer profiles with optional search."""
    results = _MOCK_IMPORTERS
    if search:
        q = search.lower()
        results = [p for p in results if q in p.importer_id.lower()]
    total = len(results)
    return ImporterListResponse(importers=results[offset : offset + limit], total=total)


@router.get("/{importer_id}", response_model=ImporterProfile)
async def get_importer(importer_id: str) -> ImporterProfile:
    """Get a single importer profile by ID."""
    profile = next((p for p in _MOCK_IMPORTERS if p.importer_id == importer_id), None)
    if profile is None:
        return _MOCK_IMPORTERS[0]
    return profile
