"""BlobStore abstraction — S3, local filesystem, and in-memory backends.

All backends implement the same async interface with SHA256 on upload.
"""
from __future__ import annotations

import hashlib
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BlobMeta:
    """Metadata returned after a blob operation."""
    key: str
    sha256: str
    size_bytes: int
    content_type: Optional[str] = None


class BlobStore(ABC):
    """Abstract base class for blob storage backends."""

    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: Optional[str] = None) -> BlobMeta:
        """Upload data and return metadata with SHA256 hash."""

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Download blob data by key. Raises KeyError if not found."""

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a blob. Returns True if deleted, False if not found."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a blob exists."""

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> List[str]:
        """List blob keys matching the given prefix."""

    @staticmethod
    def _compute_sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


# ── In-memory backend ──────────────────────────────────────────────────────


class MemoryBlobStore(BlobStore):
    """In-memory blob store for testing."""

    def __init__(self) -> None:
        self._blobs: Dict[str, bytes] = {}
        self._meta: Dict[str, BlobMeta] = {}

    async def upload(self, key: str, data: bytes, content_type: Optional[str] = None) -> BlobMeta:
        sha256 = self._compute_sha256(data)
        self._blobs[key] = data
        meta = BlobMeta(key=key, sha256=sha256, size_bytes=len(data), content_type=content_type)
        self._meta[key] = meta
        logger.debug("MemoryBlobStore: uploaded %s (%d bytes, sha256=%s)", key, len(data), sha256[:16])
        return meta

    async def download(self, key: str) -> bytes:
        if key not in self._blobs:
            raise KeyError(f"Blob not found: {key}")
        return self._blobs[key]

    async def delete(self, key: str) -> bool:
        if key in self._blobs:
            del self._blobs[key]
            del self._meta[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        return key in self._blobs

    async def list_keys(self, prefix: str = "") -> List[str]:
        return sorted(k for k in self._blobs if k.startswith(prefix))


# ── Local filesystem backend ──────────────────────────────────────────────


class LocalFilesystemBlobStore(BlobStore):
    """Stores blobs on the local filesystem. Auto-creates directories."""

    def __init__(self, root_dir: str) -> None:
        self._root = Path(root_dir)

    def _path(self, key: str) -> Path:
        return self._root / key

    async def upload(self, key: str, data: bytes, content_type: Optional[str] = None) -> BlobMeta:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        sha256 = self._compute_sha256(data)
        logger.debug("LocalBlobStore: wrote %s (%d bytes)", path, len(data))
        return BlobMeta(key=key, sha256=sha256, size_bytes=len(data), content_type=content_type)

    async def download(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise KeyError(f"Blob not found: {key}")
        return path.read_bytes()

    async def delete(self, key: str) -> bool:
        path = self._path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    async def list_keys(self, prefix: str = "") -> List[str]:
        if not self._root.exists():
            return []
        results = []
        for path in self._root.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(self._root))
                if rel.startswith(prefix):
                    results.append(rel)
        return sorted(results)


# ── S3 backend (stub) ────────────────────────────────────────────────────


class S3BlobStore(BlobStore):
    """S3-compatible blob store.

    Stub implementation for development. In production, uses aioboto3.
    Implements exponential backoff on retries.
    """

    def __init__(
        self,
        bucket: str = "labelforge-artifacts",
        endpoint_url: str = "",
        access_key: str = "",
        secret_key: str = "",
        region: str = "us-east-1",
        max_retries: int = 3,
    ) -> None:
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._max_retries = max_retries
        # Stub: use in-memory store as backing
        self._backing = MemoryBlobStore()

    async def upload(self, key: str, data: bytes, content_type: Optional[str] = None) -> BlobMeta:
        logger.info("S3BlobStore: uploading s3://%s/%s (%d bytes)", self._bucket, key, len(data))
        return await self._retry(self._backing.upload, key, data, content_type)

    async def download(self, key: str) -> bytes:
        logger.info("S3BlobStore: downloading s3://%s/%s", self._bucket, key)
        return await self._retry(self._backing.download, key)

    async def delete(self, key: str) -> bool:
        logger.info("S3BlobStore: deleting s3://%s/%s", self._bucket, key)
        return await self._retry(self._backing.delete, key)

    async def exists(self, key: str) -> bool:
        return await self._retry(self._backing.exists, key)

    async def list_keys(self, prefix: str = "") -> List[str]:
        return await self._retry(self._backing.list_keys, prefix)

    async def _retry(self, fn, *args, **kwargs):
        """Execute with exponential backoff retries."""
        last_error: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                return await fn(*args, **kwargs)
            except KeyError:
                raise  # Don't retry not-found errors
            except Exception as e:
                last_error = e
                delay = 0.1 * (2 ** attempt)
                logger.warning(
                    "S3 retry %d/%d: %s (backoff %.1fs)",
                    attempt + 1, self._max_retries, e, delay,
                )
                # In production: await asyncio.sleep(delay)
        raise RuntimeError(f"S3 operation failed after {self._max_retries} retries") from last_error
