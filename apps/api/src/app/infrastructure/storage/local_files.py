"""Local file storage adapter."""

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

from app.domain.ports.storage import FileStorage, StoredFile


class LocalFileStorage(FileStorage):
    """Local filesystem-based file storage."""

    def __init__(self, upload_dir: Path):
        self.upload_dir = upload_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, key: str, chunks: AsyncIterator[bytes], max_bytes: int) -> StoredFile:
        """Save file chunks with size limit."""
        file_path = self.upload_dir / key
        file_path.parent.mkdir(parents=True, exist_ok=True)

        sha256_hash = hashlib.sha256()
        total_size = 0

        with open(file_path, "wb") as f:
            async for chunk in chunks:
                total_size += len(chunk)
                if total_size > max_bytes:
                    file_path.unlink()
                    raise ValueError(f"file exceeds {max_bytes} bytes")
                sha256_hash.update(chunk)
                f.write(chunk)

        return StoredFile(
            path=str(file_path),
            sha256=sha256_hash.hexdigest(),
            size=total_size,
        )

    async def delete(self, key: str) -> None:
        """Delete a stored file."""
        file_path = self.upload_dir / key
        if file_path.exists():
            file_path.unlink()

    async def exists(self, key: str) -> bool:
        """Check if a file exists."""
        return (self.upload_dir / key).exists()
