"""Storage backend protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class StorageBackend(Protocol):
    def get_file(self, key: str, local_dest: Path) -> Path:
        """Download/copy a remote file to a local path. Returns local_dest."""
        ...

    def put_file(self, local_path: Path, dest_key: str) -> str:
        """Upload/copy a local file to storage. Returns the final path/URL."""
        ...

    def base_url(self, key: str) -> str:
        """Return the accessible URL/path for a key."""
        ...
