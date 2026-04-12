"""Tests for BlobStore abstraction — Memory, LocalFilesystem, and S3."""
from __future__ import annotations

import pytest

from labelforge.core.blobstore import (
    BlobMeta,
    BlobStore,
    LocalFilesystemBlobStore,
    MemoryBlobStore,
    S3BlobStore,
)


# ── Shared tests for all backends ──────────────────────────────────────────


class BlobStoreContractTests:
    """Contract tests that all BlobStore implementations must pass."""

    @pytest.fixture
    def store(self) -> BlobStore:
        raise NotImplementedError

    @pytest.mark.asyncio
    async def test_upload_returns_meta(self, store):
        meta = await store.upload("test.txt", b"hello world", content_type="text/plain")
        assert isinstance(meta, BlobMeta)
        assert meta.key == "test.txt"
        assert meta.size_bytes == 11
        assert meta.content_type == "text/plain"
        assert len(meta.sha256) == 64

    @pytest.mark.asyncio
    async def test_sha256_computed_on_upload(self, store):
        import hashlib
        data = b"sha256 test data"
        meta = await store.upload("hash.bin", data)
        expected = hashlib.sha256(data).hexdigest()
        assert meta.sha256 == expected

    @pytest.mark.asyncio
    async def test_round_trip_integrity(self, store):
        data = b"round trip data \x00\xff"
        await store.upload("rt.bin", data)
        downloaded = await store.download("rt.bin")
        assert downloaded == data

    @pytest.mark.asyncio
    async def test_download_not_found(self, store):
        with pytest.raises(KeyError):
            await store.download("nonexistent")

    @pytest.mark.asyncio
    async def test_exists_true(self, store):
        await store.upload("exists.txt", b"yes")
        assert await store.exists("exists.txt") is True

    @pytest.mark.asyncio
    async def test_exists_false(self, store):
        assert await store.exists("nope.txt") is False

    @pytest.mark.asyncio
    async def test_delete_existing(self, store):
        await store.upload("del.txt", b"delete me")
        assert await store.delete("del.txt") is True
        assert await store.exists("del.txt") is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store):
        assert await store.delete("ghost.txt") is False

    @pytest.mark.asyncio
    async def test_list_with_prefix(self, store):
        await store.upload("dir/a.txt", b"a")
        await store.upload("dir/b.txt", b"b")
        await store.upload("other/c.txt", b"c")
        keys = await store.list_keys("dir/")
        assert "dir/a.txt" in keys
        assert "dir/b.txt" in keys
        assert "other/c.txt" not in keys

    @pytest.mark.asyncio
    async def test_list_empty_prefix(self, store):
        await store.upload("x.txt", b"x")
        keys = await store.list_keys()
        assert "x.txt" in keys

    @pytest.mark.asyncio
    async def test_overwrite_existing(self, store):
        await store.upload("ow.txt", b"v1")
        await store.upload("ow.txt", b"v2")
        data = await store.download("ow.txt")
        assert data == b"v2"


# ── Memory backend ─────────────────────────────────────────────────────────


class TestMemoryBlobStore(BlobStoreContractTests):
    @pytest.fixture
    def store(self):
        return MemoryBlobStore()


# ── Local filesystem backend ──────────────────────────────────────────────


class TestLocalFilesystemBlobStore(BlobStoreContractTests):
    @pytest.fixture
    def store(self, tmp_path):
        return LocalFilesystemBlobStore(str(tmp_path / "blobs"))

    @pytest.mark.asyncio
    async def test_auto_creates_directories(self, store):
        await store.upload("deep/nested/dir/file.txt", b"content")
        data = await store.download("deep/nested/dir/file.txt")
        assert data == b"content"


# ── S3 backend (stub) ────────────────────────────────────────────────────


class TestS3BlobStore(BlobStoreContractTests):
    @pytest.fixture
    def store(self):
        return S3BlobStore(bucket="test-bucket")

    def test_s3_has_retry_config(self):
        s3 = S3BlobStore(max_retries=5)
        assert s3._max_retries == 5


# ── BlobMeta ──────────────────────────────────────────────────────────────


class TestBlobMeta:
    def test_fields(self):
        meta = BlobMeta(key="k", sha256="abc", size_bytes=10, content_type="text/plain")
        assert meta.key == "k"
        assert meta.sha256 == "abc"
        assert meta.size_bytes == 10
        assert meta.content_type == "text/plain"

    def test_content_type_optional(self):
        meta = BlobMeta(key="k", sha256="abc", size_bytes=0)
        assert meta.content_type is None
