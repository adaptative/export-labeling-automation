"""BlobStore abstraction with S3, local filesystem, and in-memory backends."""
import hashlib
import os
from abc import ABC, abstractmethod
from typing import Optional


class BlobStore(ABC):
    @abstractmethod
    async def upload(self, path: str, data: bytes) -> str:
        """Upload data, return sha256 hash."""
        ...

    @abstractmethod
    async def download(self, path: str) -> bytes:
        ...

    @abstractmethod
    async def delete(self, path: str) -> bool:
        ...

    @abstractmethod
    async def list(self, prefix: str) -> list[str]:
        ...

    @abstractmethod
    async def exists(self, path: str) -> bool:
        ...

    def compute_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


class MemoryBlobStore(BlobStore):
    def __init__(self):
        self._store: dict[str, bytes] = {}

    async def upload(self, path: str, data: bytes) -> str:
        self._store[path] = data
        return self.compute_hash(data)

    async def download(self, path: str) -> bytes:
        if path not in self._store:
            raise FileNotFoundError(f"Blob not found: {path}")
        return self._store[path]

    async def delete(self, path: str) -> bool:
        if path in self._store:
            del self._store[path]
            return True
        return False

    async def list(self, prefix: str) -> list[str]:
        return [k for k in self._store if k.startswith(prefix)]

    async def exists(self, path: str) -> bool:
        return path in self._store


class LocalFilesystemBlobStore(BlobStore):
    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def _full_path(self, path: str) -> str:
        return os.path.join(self.base_dir, path)

    async def upload(self, path: str, data: bytes) -> str:
        full = self._full_path(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as f:
            f.write(data)
        return self.compute_hash(data)

    async def download(self, path: str) -> bytes:
        full = self._full_path(path)
        if not os.path.exists(full):
            raise FileNotFoundError(f"Blob not found: {path}")
        with open(full, 'rb') as f:
            return f.read()

    async def delete(self, path: str) -> bool:
        full = self._full_path(path)
        if os.path.exists(full):
            os.remove(full)
            return True
        return False

    async def list(self, prefix: str) -> list[str]:
        results = []
        base = self._full_path(prefix)
        search_dir = os.path.dirname(base) if not os.path.isdir(base) else base
        if not os.path.exists(search_dir):
            return []
        for root, _, files in os.walk(search_dir):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, self.base_dir)
                if rel.startswith(prefix):
                    results.append(rel)
        return results

    async def exists(self, path: str) -> bool:
        return os.path.exists(self._full_path(path))
