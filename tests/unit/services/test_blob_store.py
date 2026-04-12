"""Tests for BlobStore backends (MemoryBlobStore and LocalFilesystemBlobStore)."""
import asyncio
import hashlib
import os
import tempfile

import pytest

from labelforge.services.blob_store import (
    LocalFilesystemBlobStore,
    MemoryBlobStore,
)


# ---------------------------------------------------------------------------
# MemoryBlobStore
# ---------------------------------------------------------------------------

class TestMemoryBlobStore:
    def _run(self, coro):
        return asyncio.run(coro)

    def test_upload_returns_sha256_hash(self):
        store = MemoryBlobStore()
        data = b"hello world"
        result = self._run(store.upload("file.txt", data))
        expected = hashlib.sha256(data).hexdigest()
        assert result == expected

    def test_download_roundtrip(self):
        store = MemoryBlobStore()
        data = b"round-trip data \xff\x00"
        self._run(store.upload("binary.bin", data))
        downloaded = self._run(store.download("binary.bin"))
        assert downloaded == data

    def test_download_missing_raises(self):
        store = MemoryBlobStore()
        with pytest.raises(FileNotFoundError, match="Blob not found"):
            self._run(store.download("no-such-file"))

    def test_delete_existing_returns_true(self):
        store = MemoryBlobStore()
        self._run(store.upload("f.txt", b"x"))
        assert self._run(store.delete("f.txt")) is True

    def test_delete_missing_returns_false(self):
        store = MemoryBlobStore()
        assert self._run(store.delete("nope")) is False

    def test_list_filters_by_prefix(self):
        store = MemoryBlobStore()
        self._run(store.upload("images/a.png", b"a"))
        self._run(store.upload("images/b.png", b"b"))
        self._run(store.upload("docs/c.txt", b"c"))

        result = self._run(store.list("images/"))
        assert sorted(result) == ["images/a.png", "images/b.png"]

    def test_list_empty_prefix_returns_all(self):
        store = MemoryBlobStore()
        self._run(store.upload("x", b"1"))
        self._run(store.upload("y", b"2"))
        assert len(self._run(store.list(""))) == 2

    def test_exists_true(self):
        store = MemoryBlobStore()
        self._run(store.upload("present.txt", b"data"))
        assert self._run(store.exists("present.txt")) is True

    def test_exists_false(self):
        store = MemoryBlobStore()
        assert self._run(store.exists("absent.txt")) is False

    def test_compute_hash_method(self):
        store = MemoryBlobStore()
        data = b"test data"
        assert store.compute_hash(data) == hashlib.sha256(data).hexdigest()

    def test_delete_then_download_raises(self):
        store = MemoryBlobStore()
        self._run(store.upload("tmp.txt", b"gone"))
        self._run(store.delete("tmp.txt"))
        with pytest.raises(FileNotFoundError):
            self._run(store.download("tmp.txt"))


# ---------------------------------------------------------------------------
# LocalFilesystemBlobStore
# ---------------------------------------------------------------------------

class TestLocalFilesystemBlobStore:
    def _run(self, coro):
        return asyncio.run(coro)

    def test_upload_returns_sha256_hash(self, tmp_path):
        store = LocalFilesystemBlobStore(str(tmp_path))
        data = b"local data"
        result = self._run(store.upload("file.txt", data))
        assert result == hashlib.sha256(data).hexdigest()

    def test_download_roundtrip(self, tmp_path):
        store = LocalFilesystemBlobStore(str(tmp_path))
        data = b"\x00\x01\x02binary"
        self._run(store.upload("bin.dat", data))
        assert self._run(store.download("bin.dat")) == data

    def test_download_missing_raises(self, tmp_path):
        store = LocalFilesystemBlobStore(str(tmp_path))
        with pytest.raises(FileNotFoundError, match="Blob not found"):
            self._run(store.download("missing.txt"))

    def test_delete_existing_returns_true(self, tmp_path):
        store = LocalFilesystemBlobStore(str(tmp_path))
        self._run(store.upload("d.txt", b"data"))
        assert self._run(store.delete("d.txt")) is True
        assert not os.path.exists(tmp_path / "d.txt")

    def test_delete_missing_returns_false(self, tmp_path):
        store = LocalFilesystemBlobStore(str(tmp_path))
        assert self._run(store.delete("nope.txt")) is False

    def test_auto_creates_directories(self, tmp_path):
        store = LocalFilesystemBlobStore(str(tmp_path))
        self._run(store.upload("deep/nested/dir/file.txt", b"nested"))
        full = tmp_path / "deep" / "nested" / "dir" / "file.txt"
        assert full.exists()
        assert full.read_bytes() == b"nested"

    def test_list_filters_by_prefix(self, tmp_path):
        store = LocalFilesystemBlobStore(str(tmp_path))
        self._run(store.upload("imgs/a.png", b"a"))
        self._run(store.upload("imgs/b.png", b"b"))
        self._run(store.upload("text/c.txt", b"c"))

        result = self._run(store.list("imgs/"))
        assert sorted(result) == ["imgs/a.png", "imgs/b.png"]

    def test_list_empty_returns_empty(self, tmp_path):
        store = LocalFilesystemBlobStore(str(tmp_path))
        assert self._run(store.list("nonexistent/")) == []

    def test_exists_true(self, tmp_path):
        store = LocalFilesystemBlobStore(str(tmp_path))
        self._run(store.upload("here.txt", b"yes"))
        assert self._run(store.exists("here.txt")) is True

    def test_exists_false(self, tmp_path):
        store = LocalFilesystemBlobStore(str(tmp_path))
        assert self._run(store.exists("not_here.txt")) is False

    def test_sha256_on_upload_matches_file_content(self, tmp_path):
        store = LocalFilesystemBlobStore(str(tmp_path))
        data = b"verify hash"
        returned_hash = self._run(store.upload("h.txt", data))
        file_bytes = (tmp_path / "h.txt").read_bytes()
        assert returned_hash == hashlib.sha256(file_bytes).hexdigest()
