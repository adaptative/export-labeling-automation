"""Tests for ReproduceService."""
import asyncio
import hashlib

import pytest

from labelforge.services.reproduce import ReproduceResult, ReproduceService
from tests.stubs import DB, ArtifactRecord, Provenance


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _make_service(artifacts=None, blob_contents=None):
    """Build a ReproduceService with in-memory fakes.

    When real APIs are available, replace DB/ArtifactRecord/Provenance imports
    above with real implementations — this factory stays the same.
    """
    from labelforge.services.blob_store import MemoryBlobStore

    db = DB()
    blob_store = MemoryBlobStore()
    provenance = Provenance()

    if artifacts:
        for rec in artifacts:
            db.add_artifact(rec)

    if blob_contents:
        for path, data in blob_contents.items():
            asyncio.run(blob_store.upload(path, data))

    return ReproduceService(provenance, blob_store, db), db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReproduceResult:
    def test_fields(self):
        r = ReproduceResult(
            artifact_id="abc",
            matched=True,
            original_hash="hash1",
            reproduced_hash="hash1",
        )
        assert r.artifact_id == "abc"
        assert r.matched is True
        assert r.incident_id is None

    def test_defaults(self):
        r = ReproduceResult(artifact_id="x", matched=False, original_hash="h")
        assert r.reproduced_hash is None
        assert r.incident_id is None


class TestReproduceService:
    def _run(self, coro):
        return asyncio.run(coro)

    def test_reproduce_match(self):
        data = b"stable content"
        content_hash = hashlib.sha256(data).hexdigest()
        record = ArtifactRecord(
            artifact_id="art-001",
            s3_path="artifacts/art-001.bin",
            content_hash=content_hash,
        )
        service, _ = _make_service(
            artifacts=[record],
            blob_contents={"artifacts/art-001.bin": data},
        )

        result = self._run(service.reproduce("art-001"))
        assert result.matched is True
        assert result.original_hash == content_hash
        assert result.reproduced_hash == content_hash
        assert result.incident_id is None

    def test_reproduce_mismatch_creates_incident(self):
        original_data = b"original content"
        tampered_data = b"tampered content"
        original_hash = hashlib.sha256(original_data).hexdigest()

        record = ArtifactRecord(
            artifact_id="art-002",
            s3_path="artifacts/art-002.bin",
            content_hash=original_hash,
        )
        service, db = _make_service(
            artifacts=[record],
            blob_contents={"artifacts/art-002.bin": tampered_data},
        )

        result = self._run(service.reproduce("art-002"))
        assert result.matched is False
        assert result.original_hash == original_hash
        assert result.reproduced_hash == hashlib.sha256(tampered_data).hexdigest()
        assert result.reproduced_hash != result.original_hash

        # Incident was created
        assert result.incident_id == "INC-art-002"
        assert len(db._incidents) == 1
        assert db._incidents[0]["artifact_id"] == "art-002"
        assert db._incidents[0]["expected"] == original_hash

    def test_reproduce_not_found(self):
        service, _ = _make_service()
        result = self._run(service.reproduce("nonexistent"))
        assert result.matched is False
        assert result.original_hash == ""
        assert result.incident_id == "NOT_FOUND"

    def test_reproduce_frozen_inputs(self):
        """Verify that the same frozen input always produces the same result."""
        data = b"deterministic payload"
        content_hash = hashlib.sha256(data).hexdigest()
        record = ArtifactRecord(
            artifact_id="art-frozen",
            s3_path="blobs/frozen.bin",
            content_hash=content_hash,
        )

        for _ in range(3):
            service, _ = _make_service(
                artifacts=[record],
                blob_contents={"blobs/frozen.bin": data},
            )
            result = self._run(service.reproduce("art-frozen"))
            assert result.matched is True
            assert result.reproduced_hash == content_hash

    def test_incident_id_format(self):
        original_data = b"data"
        record = ArtifactRecord(
            artifact_id="abcdef1234567890",
            s3_path="p",
            content_hash="wrong-hash",
        )
        service, _ = _make_service(
            artifacts=[record],
            blob_contents={"p": original_data},
        )
        result = self._run(service.reproduce("abcdef1234567890"))
        assert result.incident_id == "INC-abcdef12"
