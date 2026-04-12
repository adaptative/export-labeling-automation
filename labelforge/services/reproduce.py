"""Reproduce service for byte-reproducibility verification."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ReproduceResult:
    artifact_id: str
    matched: bool
    original_hash: str
    reproduced_hash: Optional[str] = None
    incident_id: Optional[str] = None


class ReproduceService:
    def __init__(self, provenance_emitter, blob_store, db_session):
        self.provenance = provenance_emitter
        self.blob_store = blob_store
        self.db = db_session

    async def reproduce(self, artifact_id: str) -> ReproduceResult:
        record = await self.db.get_artifact(artifact_id)
        if not record:
            return ReproduceResult(
                artifact_id=artifact_id, matched=False,
                original_hash="", incident_id="NOT_FOUND"
            )
        content = await self.blob_store.download(record.s3_path)
        reproduced_hash = self.provenance.compute_hash(content)
        matched = reproduced_hash == record.content_hash
        incident_id = None
        if not matched:
            incident_id = await self._create_incident(artifact_id, record.content_hash, reproduced_hash)
        return ReproduceResult(
            artifact_id=artifact_id,
            matched=matched,
            original_hash=record.content_hash,
            reproduced_hash=reproduced_hash,
            incident_id=incident_id,
        )

    async def _create_incident(self, artifact_id: str, expected: str, actual: str) -> str:
        incident_id = f"INC-{artifact_id[:8]}"
        await self.db.create_incident(incident_id, artifact_id, expected, actual)
        return incident_id
