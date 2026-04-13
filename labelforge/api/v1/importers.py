"""Importer profile endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.contracts import ImporterProfile
from labelforge.core.auth import TokenPayload
from labelforge.db.models import Importer, ImporterProfileModel
from labelforge.db.session import get_db

router = APIRouter(prefix="/importers", tags=["importers"])


# ── Response models ──────────────────────────────────────────────────────────


class ImporterListResponse(BaseModel):
    importers: list[ImporterProfile]
    total: int


# ── Helpers ──────────────────────────────────────────────────────────────────


def _profile_to_contract(importer: Importer, profile: Optional[ImporterProfileModel]) -> ImporterProfile:
    return ImporterProfile(
        importer_id=importer.id,
        brand_treatment=profile.brand_treatment if profile else None,
        panel_layouts=profile.panel_layouts if profile else None,
        handling_symbol_rules=profile.handling_symbol_rules if profile else None,
        pi_template_mapping=profile.pi_template_mapping if profile else None,
        logo_asset_hash=profile.logo_asset_hash if profile else None,
        version=profile.version if profile else 0,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=ImporterListResponse)
async def list_importers(
    search: Optional[str] = Query(None, description="Search by importer ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterListResponse:
    """List importer profiles with optional search."""
    query = select(Importer).where(Importer.tenant_id == _user.tenant_id)
    count_query = select(func.count()).select_from(Importer).where(Importer.tenant_id == _user.tenant_id)

    if search:
        pattern = f"%{search}%"
        query = query.where(Importer.name.ilike(pattern) | Importer.code.ilike(pattern))
        count_query = count_query.where(Importer.name.ilike(pattern) | Importer.code.ilike(pattern))

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(Importer.name).offset(offset).limit(limit)
    result = await db.execute(query)
    importers = result.scalars().all()

    profiles: list[ImporterProfile] = []
    for importer in importers:
        # Get latest profile (highest version) for each importer
        subq = (
            select(func.max(ImporterProfileModel.version))
            .where(ImporterProfileModel.importer_id == importer.id)
            .scalar_subquery()
        )
        prof_result = await db.execute(
            select(ImporterProfileModel).where(
                ImporterProfileModel.importer_id == importer.id,
                ImporterProfileModel.version == subq,
            )
        )
        profile = prof_result.scalar_one_or_none()
        profiles.append(_profile_to_contract(importer, profile))

    return ImporterListResponse(importers=profiles, total=total)


@router.get("/{importer_id}", response_model=ImporterProfile)
async def get_importer(
    importer_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterProfile:
    """Get a single importer profile by ID."""
    result = await db.execute(
        select(Importer).where(
            Importer.id == importer_id,
            Importer.tenant_id == _user.tenant_id,
        )
    )
    importer = result.scalar_one_or_none()
    if importer is None:
        raise HTTPException(status_code=404, detail="Importer not found")

    # Get latest profile
    subq = (
        select(func.max(ImporterProfileModel.version))
        .where(ImporterProfileModel.importer_id == importer.id)
        .scalar_subquery()
    )
    prof_result = await db.execute(
        select(ImporterProfileModel).where(
            ImporterProfileModel.importer_id == importer.id,
            ImporterProfileModel.version == subq,
        )
    )
    profile = prof_result.scalar_one_or_none()

    return _profile_to_contract(importer, profile)
