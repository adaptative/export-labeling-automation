"""Provenance emitter for byte-reproducible artifacts."""
import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class ArtifactRecord:
    artifact_id: str
    artifact_type: str
    content_hash: str
    s3_path: str
    provenance: dict


class ProvenanceEmitter:
    def __init__(self, blob_store, db_session):
        self.blob_store = blob_store
        self.db = db_session

    def compute_hash(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    async def emit(
        self,
        artifact_type: str,
        content: bytes,
        llm_snapshot: Optional[dict] = None,
        frozen_inputs: Optional[dict] = None,
    ) -> ArtifactRecord:
        content_hash = self.compute_hash(content)
        s3_path = f"artifacts/{content_hash[:2]}/{content_hash}"
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

    async def reproduce(self, artifact_id: str) -> bool:
        record = await self.db.get_artifact(artifact_id)
        if not record:
            return False
        content = await self.blob_store.download(record.s3_path)
        actual_hash = self.compute_hash(content)
        return actual_hash == record.content_hash
