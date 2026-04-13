"""Provenance emitter for byte-reproducible artifacts.

Provides content-addressed storage with sha256 hashing, idempotent
artifact emission, and bit-exact reproducibility verification.

S3 paths use content-addressed layout: artifacts/{hash[:2]}/{hash}
This ensures even distribution across S3 prefixes for performance.
"""
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ArtifactRecord:
    artifact_id: str
    artifact_type: str
    content_hash: str
    s3_path: str
    provenance: dict


@dataclass
class EmitResult:
    """Result of an emit() call with metadata about what happened."""
    record: ArtifactRecord
    was_deduplicated: bool
    emit_time_ms: float = 0.0


class ProvenanceEmitter:
    """Emits artifacts with full provenance tracking.

    Usage:
        emitter = ProvenanceEmitter(blob_store, db_session)
        record = await emitter.emit("die_cut_svg", svg_bytes,
            llm_snapshot={"model": "gpt-5.4", ...},
            frozen_inputs={"profile_version": 2, ...},
        )
        is_reproducible = await emitter.reproduce(record.artifact_id)
    """

    def __init__(self, blob_store, db_session):
        self.blob_store = blob_store
        self.db = db_session

    def compute_hash(self, content: bytes) -> str:
        """Compute sha256 hex digest of content."""
        return hashlib.sha256(content).hexdigest()

    def content_addressed_path(self, content_hash: str) -> str:
        """Generate S3 content-addressed path from hash."""
        return f"artifacts/{content_hash[:2]}/{content_hash}"

    async def emit(
        self,
        artifact_type: str,
        content: bytes,
        llm_snapshot: Optional[dict] = None,
        frozen_inputs: Optional[dict] = None,
        tenant_id: Optional[str] = None,
        order_item_id: Optional[str] = None,
    ) -> ArtifactRecord:
        """Emit an artifact with provenance. Idempotent — returns existing on hash match."""
        content_hash = self.compute_hash(content)
        s3_path = self.content_addressed_path(content_hash)

        # Idempotent: check if already exists
        existing = await self.db.get_artifact_by_hash(content_hash)
        if existing:
            return existing

        await self.blob_store.upload(s3_path, content)

        provenance = {
            "content_hash": content_hash,
            "llm_snapshot": llm_snapshot,
            "frozen_inputs": frozen_inputs or {},
        }

        record = ArtifactRecord(
            artifact_id=content_hash[:16],
            artifact_type=artifact_type,
            content_hash=content_hash,
            s3_path=s3_path,
            provenance=provenance,
        )
        await self.db.save_artifact(record)
        return record

    async def emit_with_metadata(
        self,
        artifact_type: str,
        content: bytes,
        llm_snapshot: Optional[dict] = None,
        frozen_inputs: Optional[dict] = None,
        tenant_id: Optional[str] = None,
        order_item_id: Optional[str] = None,
    ) -> EmitResult:
        """Like emit() but returns metadata about whether dedup occurred."""
        start = time.monotonic()
        content_hash = self.compute_hash(content)

        existing = await self.db.get_artifact_by_hash(content_hash)
        if existing:
            elapsed = (time.monotonic() - start) * 1000
            return EmitResult(record=existing, was_deduplicated=True, emit_time_ms=elapsed)

        record = await self.emit(
            artifact_type, content, llm_snapshot, frozen_inputs,
            tenant_id, order_item_id,
        )
        elapsed = (time.monotonic() - start) * 1000
        return EmitResult(record=record, was_deduplicated=False, emit_time_ms=elapsed)

    async def reproduce(self, artifact_id: str) -> bool:
        """Verify an artifact is bit-exact reproducible from stored content."""
        record = await self.db.get_artifact(artifact_id)
        if not record:
            return False
        content = await self.blob_store.download(record.s3_path)
        actual_hash = self.compute_hash(content)
        return actual_hash == record.content_hash

    async def get_provenance(self, artifact_id: str) -> Optional[dict]:
        """Retrieve provenance metadata for an artifact."""
        record = await self.db.get_artifact(artifact_id)
        if not record:
            return None
        return record.provenance
