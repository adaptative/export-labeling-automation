"""Tests for labelforge.core.provenance — TASK-005."""
import hashlib

import pytest
from unittest.mock import AsyncMock, MagicMock

from labelforge.core.provenance import ArtifactRecord, ProvenanceEmitter


@pytest.fixture
def blob_store():
    store = AsyncMock()
    return store


@pytest.fixture
def db_session():
    db = AsyncMock()
    db.get_artifact_by_hash.return_value = None
    db.get_artifact.return_value = None
    return db


@pytest.fixture
def emitter(blob_store, db_session):
    return ProvenanceEmitter(blob_store, db_session)


class TestComputeHash:
    def test_is_sha256(self, emitter):
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()
        assert emitter.compute_hash(content) == expected

    def test_different_content_different_hash(self, emitter):
        assert emitter.compute_hash(b"aaa") != emitter.compute_hash(b"bbb")

    def test_same_content_same_hash(self, emitter):
        assert emitter.compute_hash(b"same") == emitter.compute_hash(b"same")


class TestEmit:
    @pytest.mark.asyncio
    async def test_creates_artifact_record(self, emitter, blob_store, db_session):
        content = b"label pdf content"
        record = await emitter.emit("label_pdf", content)
        assert isinstance(record, ArtifactRecord)
        assert record.artifact_type == "label_pdf"
        assert record.content_hash == hashlib.sha256(content).hexdigest()
        db_session.save_artifact.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_is_idempotent(self, emitter, blob_store, db_session):
        content = b"same content"
        existing = ArtifactRecord(
            artifact_id="existing",
            artifact_type="label_pdf",
            content_hash=hashlib.sha256(content).hexdigest(),
            s3_path="artifacts/ab/abcdef",
            provenance={},
        )
        db_session.get_artifact_by_hash.return_value = existing

        record = await emitter.emit("label_pdf", content)
        assert record is existing
        blob_store.upload.assert_not_awaited()
        db_session.save_artifact.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stores_to_blob_store(self, emitter, blob_store, db_session):
        content = b"artifact bytes"
        content_hash = hashlib.sha256(content).hexdigest()
        expected_path = f"artifacts/{content_hash[:2]}/{content_hash}"

        await emitter.emit("sds", content)
        blob_store.upload.assert_awaited_once_with(expected_path, content)

    @pytest.mark.asyncio
    async def test_without_llm_snapshot(self, emitter, db_session):
        content = b"no snapshot"
        record = await emitter.emit("label_pdf", content)
        assert record.provenance["llm_snapshot"] is None
        assert record.provenance["frozen_inputs"] == {}

    @pytest.mark.asyncio
    async def test_with_llm_snapshot(self, emitter, db_session):
        content = b"with snapshot"
        snapshot = {"model": "gpt-4", "temperature": 0.0}
        record = await emitter.emit("label_pdf", content, llm_snapshot=snapshot)
        assert record.provenance["llm_snapshot"] == snapshot

    @pytest.mark.asyncio
    async def test_s3_path_uses_hash_prefix(self, emitter):
        content = b"test content"
        record = await emitter.emit("label", content)
        content_hash = hashlib.sha256(content).hexdigest()
        assert record.s3_path.startswith(f"artifacts/{content_hash[:2]}/")


class TestReproduce:
    @pytest.mark.asyncio
    async def test_returns_true_on_hash_match(self, emitter, blob_store, db_session):
        content = b"reproducible content"
        content_hash = hashlib.sha256(content).hexdigest()
        record = ArtifactRecord(
            artifact_id="abc123",
            artifact_type="label_pdf",
            content_hash=content_hash,
            s3_path="artifacts/ab/abc",
            provenance={},
        )
        db_session.get_artifact.return_value = record
        blob_store.download.return_value = content

        result = await emitter.reproduce("abc123")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_mismatch(self, emitter, blob_store, db_session):
        record = ArtifactRecord(
            artifact_id="abc123",
            artifact_type="label_pdf",
            content_hash="original_hash",
            s3_path="artifacts/ab/abc",
            provenance={},
        )
        db_session.get_artifact.return_value = record
        blob_store.download.return_value = b"tampered content"

        result = await emitter.reproduce("abc123")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_missing_artifact(self, emitter, db_session):
        db_session.get_artifact.return_value = None
        result = await emitter.reproduce("nonexistent")
        assert result is False
