"""Artifact / provenance endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from labelforge.contracts import Provenance, FrozenInputs, LLMSnapshot

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


# ── Response models ──────────────────────────────────────────────────────────


class ArtifactListResponse(BaseModel):
    artifacts: list[Provenance]
    total: int


# ── Mock data ────────────────────────────────────────────────────────────────

_MOCK_ARTIFACTS: list[Provenance] = [
    Provenance(
        artifact_id="art-001",
        artifact_type="fused_item",
        content_hash="sha256:abcdef1234567890",
        llm_snapshot=LLMSnapshot(
            model_id="claude-sonnet-4-20250514",
            prompt_hash="sha256:prompt001",
            temperature=0.0,
            max_tokens=4096,
        ),
        frozen_inputs=FrozenInputs(
            profile_version=3,
            rules_snapshot_id="snap-r1",
            asset_hashes={"po": "sha256:po001", "pi": "sha256:pi001"},
            code_sha="abc123def",
        ),
        created_at=datetime(2026, 4, 8, 10, 0, 0, tzinfo=timezone.utc),
    ),
    Provenance(
        artifact_id="art-002",
        artifact_type="compliance_report",
        content_hash="sha256:fedcba0987654321",
        llm_snapshot=LLMSnapshot(
            model_id="claude-sonnet-4-20250514",
            prompt_hash="sha256:prompt002",
            temperature=0.0,
            max_tokens=4096,
        ),
        frozen_inputs=FrozenInputs(
            profile_version=3,
            rules_snapshot_id="snap-r1",
            asset_hashes={"fused_item": "sha256:abcdef1234567890"},
            code_sha="abc123def",
        ),
        created_at=datetime(2026, 4, 8, 10, 30, 0, tzinfo=timezone.utc),
    ),
    Provenance(
        artifact_id="art-003",
        artifact_type="die_cut_svg",
        content_hash="sha256:1122334455667788",
        llm_snapshot=None,
        frozen_inputs=FrozenInputs(
            profile_version=2,
            rules_snapshot_id="snap-r2",
            asset_hashes={"template": "sha256:tmpl001"},
            code_sha="abc123def",
        ),
        created_at=datetime(2026, 4, 9, 8, 0, 0, tzinfo=timezone.utc),
    ),
]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    artifact_type: Optional[str] = Query(None, description="Filter by artifact type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ArtifactListResponse:
    """List provenance artifacts with optional filtering."""
    results = _MOCK_ARTIFACTS
    if artifact_type:
        results = [a for a in results if a.artifact_type == artifact_type]
    total = len(results)
    return ArtifactListResponse(artifacts=results[offset : offset + limit], total=total)
