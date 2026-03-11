"""Pluggable storage layer — local filesystem or S3."""

from __future__ import annotations

from pathlib import Path

from hlspkg.storage.base import StorageBackend
from hlspkg.storage.local import LocalStorage


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse 's3://bucket/prefix' into (bucket, prefix)."""
    without_scheme = uri[len("s3://"):]
    parts = without_scheme.split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    return bucket, prefix


def resolve_storage(uri: str) -> StorageBackend:
    """Create the appropriate storage backend from a URI string."""
    if uri.startswith("s3://"):
        from hlspkg.storage.s3 import S3Storage

        bucket, prefix = _parse_s3_uri(uri)
        return S3Storage(bucket, prefix)
    return LocalStorage(Path(uri))


__all__ = ["StorageBackend", "resolve_storage"]
