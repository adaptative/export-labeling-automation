"""Artifact / provenance endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from labelforge.contracts import Provenance, FrozenInputs, LLMSnapshot

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


# ── Mock data ────────────────────────────────────────────────────────────────

_MOCK_ARTIFACTS: List[Provenance] = [
    Provenance(
        artifact_id="art-001",
        artifact_type="fused_item",
        content_hash="sha256:abcdef1234567890",
        llm_snapshot=LLMSnapshot(
            model_id="gpt-5.4",
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
            model_id="gpt-5.4",
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

_MOCK_DETAILS: Dict[str, ArtifactDetail] = {
    "art-001": ArtifactDetail(
        artifact_id="art-001", artifact_type="fused_item",
        content_hash="sha256:abcdef1234567890",
        llm_snapshot=_MOCK_ARTIFACTS[0].llm_snapshot,
        frozen_inputs=_MOCK_ARTIFACTS[0].frozen_inputs,
        created_at=_MOCK_ARTIFACTS[0].created_at,
        size_bytes=245_760, mime_type="application/json",
        storage_key="artifacts/art-001/fused_item.json",
        order_id="PO-2065", created_by="composer-agent-v3",
    ),
    "art-002": ArtifactDetail(
        artifact_id="art-002", artifact_type="compliance_report",
        content_hash="sha256:fedcba0987654321",
        llm_snapshot=_MOCK_ARTIFACTS[1].llm_snapshot,
        frozen_inputs=_MOCK_ARTIFACTS[1].frozen_inputs,
        created_at=_MOCK_ARTIFACTS[1].created_at,
        size_bytes=1_048_576, mime_type="application/pdf",
        storage_key="artifacts/art-002/compliance_report.pdf",
        order_id="PO-2065", created_by="validator-agent-v2",
    ),
    "art-003": ArtifactDetail(
        artifact_id="art-003", artifact_type="die_cut_svg",
        content_hash="sha256:1122334455667788",
        llm_snapshot=None,
        frozen_inputs=_MOCK_ARTIFACTS[2].frozen_inputs,
        created_at=_MOCK_ARTIFACTS[2].created_at,
        size_bytes=82_944, mime_type="image/svg+xml",
        storage_key="artifacts/art-003/diecut.svg",
        order_id="PO-2066", created_by="composer-agent-v3",
    ),
}

_MOCK_PROVENANCE: Dict[str, List[ProvenanceStep]] = {
    "art-001": [
        ProvenanceStep(step_number=1, agent_id="extractor-agent-v2", model_id="gpt-5.4",
                       prompt_hash="sha256:ext001", input_hash="sha256:po001",
                       output_hash="sha256:extracted001", action="extract",
                       timestamp="2026-04-08T09:30:00Z", duration_ms=4200),
        ProvenanceStep(step_number=2, agent_id="composer-agent-v3", model_id="gpt-5.4",
                       prompt_hash="sha256:prompt001", input_hash="sha256:extracted001",
                       output_hash="sha256:abcdef1234567890", action="compose",
                       timestamp="2026-04-08T09:45:00Z", duration_ms=8500),
        ProvenanceStep(step_number=3, agent_id="validator-agent-v2", model_id="gpt-5.4",
                       prompt_hash="sha256:val001", input_hash="sha256:abcdef1234567890",
                       output_hash="sha256:abcdef1234567890", action="validate",
                       timestamp="2026-04-08T10:00:00Z", duration_ms=3100),
    ],
    "art-002": [
        ProvenanceStep(step_number=1, agent_id="validator-agent-v2", model_id="gpt-5.4",
                       prompt_hash="sha256:prompt002", input_hash="sha256:abcdef1234567890",
                       output_hash="sha256:fedcba0987654321", action="validate",
                       timestamp="2026-04-08T10:15:00Z", duration_ms=6200),
        ProvenanceStep(step_number=2, agent_id="system", model_id=None,
                       prompt_hash=None, input_hash="sha256:fedcba0987654321",
                       output_hash="sha256:fedcba0987654321", action="approve",
                       timestamp="2026-04-08T10:30:00Z", duration_ms=120),
    ],
    "art-003": [
        ProvenanceStep(step_number=1, agent_id="composer-agent-v3", model_id=None,
                       prompt_hash=None, input_hash="sha256:tmpl001",
                       output_hash="sha256:1122334455667788", action="compose",
                       timestamp="2026-04-09T08:00:00Z", duration_ms=2400),
    ],
}


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    artifact_type: Optional[str] = Query(None, description="Filter by artifact type"),
    search: Optional[str] = Query(None, description="Search by hash or ID"),
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ArtifactListResponse:
    """List provenance artifacts with optional filtering."""
    results = list(_MOCK_ARTIFACTS)
    if artifact_type:
        results = [a for a in results if a.artifact_type == artifact_type]
    if search:
        q = search.lower()
        results = [
            a for a in results
            if q in a.artifact_id.lower() or q in a.content_hash.lower()
        ]
    if order_id:
        # Filter by order_id using the detail lookup
        results = [
            a for a in results
            if a.artifact_id in _MOCK_DETAILS
            and _MOCK_DETAILS[a.artifact_id].order_id == order_id
        ]
    total = len(results)
    return ArtifactListResponse(artifacts=results[offset:offset + limit], total=total)


@router.get("/{artifact_id}", response_model=ArtifactDetail)
async def get_artifact(artifact_id: str) -> ArtifactDetail:
    """Get detailed artifact information."""
    detail = _MOCK_DETAILS.get(artifact_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return detail


@router.get("/{artifact_id}/provenance", response_model=ProvenanceChainResponse)
async def get_artifact_provenance(artifact_id: str) -> ProvenanceChainResponse:
    """Get provenance chain for an artifact."""
    steps = _MOCK_PROVENANCE.get(artifact_id)
    if steps is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return ProvenanceChainResponse(artifact_id=artifact_id, steps=steps)


@router.get("/{artifact_id}/download", response_model=DownloadResponse)
async def download_artifact(artifact_id: str) -> DownloadResponse:
    """Get download URL for an artifact."""
    detail = _MOCK_DETAILS.get(artifact_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Artifact not found")

    filename = detail.storage_key.split("/")[-1]
    return DownloadResponse(
        download_url=f"https://labelforge-artifacts.s3.amazonaws.com/{detail.storage_key}?X-Amz-Expires=3600",
        filename=filename,
        mime_type=detail.mime_type,
        size_bytes=detail.size_bytes,
    )
