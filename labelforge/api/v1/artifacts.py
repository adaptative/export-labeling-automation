"""Artifact / provenance endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.contracts import Provenance, FrozenInputs, LLMSnapshot
from labelforge.core.auth import TokenPayload
from labelforge.db.models import Artifact as ArtifactModel, OrderItemModel
from labelforge.db.session import get_db

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


# ── Response models ──────────────────────────────────────────────────────────


class ArtifactListResponse(BaseModel):
    artifacts: List[Provenance]
    total: int


class ArtifactDetail(BaseModel):
    artifact_id: str
    artifact_type: str
    content_hash: str
    llm_snapshot: Optional[LLMSnapshot] = None
    frozen_inputs: FrozenInputs
    created_at: datetime
    size_bytes: int
    mime_type: str
    storage_key: str
    order_id: Optional[str] = None
    created_by: Optional[str] = None


class ProvenanceStep(BaseModel):
    step_number: int
    agent_id: str
    model_id: Optional[str] = None
    prompt_hash: Optional[str] = None
    input_hash: str
    output_hash: str
    action: str
    timestamp: str
    duration_ms: int


class ProvenanceChainResponse(BaseModel):
    artifact_id: str
    steps: List[ProvenanceStep]


class DownloadResponse(BaseModel):
    download_url: str
    filename: str
    mime_type: str
    size_bytes: int


# ── Helpers ─────────────────────────────────────────────────────────────────


def _to_provenance(a: ArtifactModel) -> Provenance:
    prov = a.provenance or {}
    llm = None
    if prov.get("model_id"):
        llm = LLMSnapshot(
            model_id=prov["model_id"],
            prompt_hash=prov.get("prompt_hash", ""),
            temperature=prov.get("temperature", 0.0),
            max_tokens=prov.get("max_tokens", 4096),
        )
    frozen = FrozenInputs(
        profile_version=prov.get("profile_version"),
        rules_snapshot_id=prov.get("rules_snapshot_id"),
        asset_hashes=prov.get("asset_hashes", {}),
        code_sha=prov.get("code_sha"),
    )
    return Provenance(
        artifact_id=a.id,
        artifact_type=a.artifact_type,
        content_hash=a.content_hash,
        llm_snapshot=llm,
        frozen_inputs=frozen,
        created_at=a.created_at,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    artifact_type: Optional[str] = Query(None, description="Filter by artifact type"),
    search: Optional[str] = Query(None, description="Search by hash or ID"),
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ArtifactListResponse:
    """List provenance artifacts with optional filtering."""
    query = select(ArtifactModel)
    count_query = select(func.count()).select_from(ArtifactModel)

    if artifact_type:
        query = query.where(ArtifactModel.artifact_type == artifact_type)
        count_query = count_query.where(ArtifactModel.artifact_type == artifact_type)

    if search:
        pattern = f"%{search}%"
        search_filter = or_(
            ArtifactModel.id.ilike(pattern),
            ArtifactModel.content_hash.ilike(pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if order_id:
        query = query.join(
            OrderItemModel, ArtifactModel.order_item_id == OrderItemModel.id
        ).where(OrderItemModel.order_id == order_id)
        count_query = count_query.join(
            OrderItemModel, ArtifactModel.order_item_id == OrderItemModel.id
        ).where(OrderItemModel.order_id == order_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(ArtifactModel.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    artifacts = result.scalars().all()

    return ArtifactListResponse(
        artifacts=[_to_provenance(a) for a in artifacts],
        total=total,
    )


@router.get("/{artifact_id}", response_model=ArtifactDetail)
async def get_artifact(
    artifact_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ArtifactDetail:
    """Get detailed artifact information."""
    query = (
        select(ArtifactModel, OrderItemModel.order_id)
        .outerjoin(OrderItemModel, ArtifactModel.order_item_id == OrderItemModel.id)
        .where(ArtifactModel.id == artifact_id)
    )
    result = await db.execute(query)
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    a, linked_order_id = row
    prov = a.provenance or {}
    provenance_obj = _to_provenance(a)
    created_by = prov.get("created_by", "system")

    return ArtifactDetail(
        artifact_id=a.id,
        artifact_type=a.artifact_type,
        content_hash=a.content_hash,
        llm_snapshot=provenance_obj.llm_snapshot,
        frozen_inputs=provenance_obj.frozen_inputs,
        created_at=a.created_at,
        size_bytes=a.size_bytes or 0,
        mime_type=a.mime_type or "application/octet-stream",
        storage_key=a.s3_key,
        order_id=linked_order_id,
        created_by=created_by,
    )


@router.get("/{artifact_id}/provenance", response_model=ProvenanceChainResponse)
async def get_artifact_provenance(
    artifact_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProvenanceChainResponse:
    """Get provenance chain for an artifact."""
    result = await db.execute(
        select(ArtifactModel).where(ArtifactModel.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    prov = artifact.provenance or {}
    raw_steps = prov.get("steps")

    if raw_steps and isinstance(raw_steps, list):
        steps = [ProvenanceStep(**s) for s in raw_steps]
    else:
        # Build a single step from the artifact's provenance data
        steps = [
            ProvenanceStep(
                step_number=1,
                agent_id=prov.get("created_by", "system"),
                model_id=prov.get("model_id"),
                prompt_hash=prov.get("prompt_hash"),
                input_hash=prov.get("input_hash", artifact.content_hash),
                output_hash=artifact.content_hash,
                action=prov.get("action", "generate"),
                timestamp=artifact.created_at.isoformat(),
                duration_ms=prov.get("duration_ms", 0),
            )
        ]

    return ProvenanceChainResponse(artifact_id=artifact_id, steps=steps)


@router.get("/{artifact_id}/download", response_model=DownloadResponse)
async def download_artifact(
    artifact_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DownloadResponse:
    """Get download URL for an artifact."""
    result = await db.execute(
        select(ArtifactModel).where(ArtifactModel.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    filename = artifact.s3_key.split("/")[-1]
    mime = artifact.mime_type or "application/octet-stream"

    return DownloadResponse(
        download_url=f"https://labelforge-artifacts.s3.amazonaws.com/{artifact.s3_key}?X-Amz-Expires=3600",
        filename=filename,
        mime_type=mime,
        size_bytes=artifact.size_bytes or 0,
    )
