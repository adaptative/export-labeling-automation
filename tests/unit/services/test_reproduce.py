"""Tests for ReproduceService."""
import asyncio
import hashlib

import pytest

from labelforge.services.reproduce import (
    ReproduceResult, ReproduceService, BatchReproduceResult,
)
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
# ReproduceResult
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
        assert r.duration_ms == 0.0
        assert r.cost_usd == 0.0


# ---------------------------------------------------------------------------
# Single reproduce
# ---------------------------------------------------------------------------


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
        assert result.cost_usd > 0

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

    def test_reproduce_tracks_duration(self):
        data = b"timing test"
        content_hash = hashlib.sha256(data).hexdigest()
        record = ArtifactRecord(
            artifact_id="art-time",
            s3_path="t",
            content_hash=content_hash,
        )
        service, _ = _make_service(
            artifacts=[record],
            blob_contents={"t": data},
        )
        result = self._run(service.reproduce("art-time"))
        assert result.duration_ms >= 0

    def test_reproduce_tracks_cost(self):
        data = b"cost test"
        content_hash = hashlib.sha256(data).hexdigest()
        record = ArtifactRecord(
            artifact_id="art-cost",
            s3_path="c",
            content_hash=content_hash,
        )
        service, _ = _make_service(
            artifacts=[record],
            blob_contents={"c": data},
        )
        result = self._run(service.reproduce("art-cost"))
        assert result.cost_usd == ReproduceService.COST_PER_REPRODUCE_USD


# ---------------------------------------------------------------------------
# Batch reproduce
# ---------------------------------------------------------------------------


class TestBatchReproduce:
    def _run(self, coro):
        return asyncio.run(coro)

    def _make_artifacts(self, count):
        artifacts = []
        blobs = {}
        for i in range(count):
            data = f"artifact-{i}".encode()
            h = hashlib.sha256(data).hexdigest()
            aid = f"art-{i:03d}"
            path = f"blobs/{aid}.bin"
            artifacts.append(ArtifactRecord(artifact_id=aid, s3_path=path, content_hash=h))
            blobs[path] = data
        return artifacts, blobs

    def test_batch_reproduce_all_match(self):
        artifacts, blobs = self._make_artifacts(20)
        service, _ = _make_service(artifacts=artifacts, blob_contents=blobs)
        ids = [a.artifact_id for a in artifacts]

        result = self._run(service.batch_reproduce(ids, sample_pct=0.5, seed=42))
        assert result.total_sampled == 10
        assert result.matched == 10
        assert result.mismatched == 0
        assert result.not_found == 0
        assert result.match_rate == 1.0
        assert result.total_cost_usd > 0
        assert len(result.results) == 10

    def test_batch_reproduce_with_mismatch(self):
        artifacts, blobs = self._make_artifacts(10)
        # Tamper with artifact 5
        blobs[artifacts[5].s3_path] = b"tampered"
        service, db = _make_service(artifacts=artifacts, blob_contents=blobs)
        ids = [a.artifact_id for a in artifacts]

        # Use 100% sample to ensure we hit the tampered one
        result = self._run(service.batch_reproduce(ids, sample_pct=1.0, seed=42))
        assert result.total_sampled == 10
        assert result.mismatched == 1
        assert result.matched == 9
        assert len(db._incidents) == 1

    def test_batch_minimum_sample_size_is_1(self):
        artifacts, blobs = self._make_artifacts(3)
        service, _ = _make_service(artifacts=artifacts, blob_contents=blobs)
        ids = [a.artifact_id for a in artifacts]

        # 5% of 3 = 0.15, should round up to 1
        result = self._run(service.batch_reproduce(ids, sample_pct=0.05, seed=1))
        assert result.total_sampled == 1

    def test_batch_reproduce_deterministic_with_seed(self):
        artifacts, blobs = self._make_artifacts(20)
        service, _ = _make_service(artifacts=artifacts, blob_contents=blobs)
        ids = [a.artifact_id for a in artifacts]

        r1 = self._run(service.batch_reproduce(ids, sample_pct=0.25, seed=99))
        # Rebuild service for fresh run
        service, _ = _make_service(artifacts=artifacts, blob_contents=blobs)
        r2 = self._run(service.batch_reproduce(ids, sample_pct=0.25, seed=99))

        sampled_1 = [r.artifact_id for r in r1.results]
        sampled_2 = [r.artifact_id for r in r2.results]
        assert sampled_1 == sampled_2

    def test_batch_reproduce_empty_list(self):
        service, _ = _make_service()
        result = self._run(service.batch_reproduce([], sample_pct=0.05))
        assert result.total_sampled == 0
        assert result.match_rate == 0.0


# ---------------------------------------------------------------------------
# Nightly sample
# ---------------------------------------------------------------------------


class TestNightlySample:
    def _run(self, coro):
        return asyncio.run(coro)

    def test_nightly_sample_empty_db(self):
        service, _ = _make_service()
        result = self._run(service.nightly_sample())
        assert result.total_sampled == 0

    def test_nightly_sample_runs_5_pct(self):
        from labelforge.services.blob_store import MemoryBlobStore
        from tests.stubs import DB as StubDB, Provenance as StubProvenance

        db = StubDB()
        blob_store = MemoryBlobStore()
        provenance = StubProvenance()

        # Create 100 artifacts
        for i in range(100):
            data = f"nightly-{i}".encode()
            h = hashlib.sha256(data).hexdigest()
            aid = f"nightly-{i:03d}"
            path = f"blobs/{aid}.bin"
            db.add_artifact(ArtifactRecord(artifact_id=aid, s3_path=path, content_hash=h))
            asyncio.run(blob_store.upload(path, data))

        service = ReproduceService(provenance, blob_store, db)
        result = self._run(service.nightly_sample(seed=42))

        assert result.total_sampled == 5  # 5% of 100
        assert result.matched == 5
        assert result.mismatched == 0
        assert result.match_rate == 1.0


# ---------------------------------------------------------------------------
# BatchReproduceResult
# ---------------------------------------------------------------------------


class TestBatchReproduceResult:
    def test_match_rate_calculation(self):
        r = BatchReproduceResult(
            total_sampled=10, matched=8, mismatched=2, not_found=0,
        )
        assert r.match_rate == 0.8

    def test_match_rate_zero_sampled(self):
        r = BatchReproduceResult(
            total_sampled=0, matched=0, mismatched=0, not_found=0,
        )
        assert r.match_rate == 0.0
