"""Local filesystem storage backend."""

from __future__ import annotations

import shutil
from pathlib import Path


class LocalStorage:
    def __init__(self, base_path: Path) -> None:
        self._base = base_path.resolve()

    def get_file(self, key: str, local_dest: Path) -> Path:
        src = self._base / key
        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {src}")
        if src.resolve() == local_dest.resolve():
            return local_dest
        local_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, local_dest)
        return local_dest

    def put_file(self, local_path: Path, dest_key: str) -> str:
        dest = self._base / dest_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
        return str(dest)

    def base_url(self, key: str) -> str:
        return str(self._base / key)
