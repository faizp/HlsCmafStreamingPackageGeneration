"""S3 storage backend (requires boto3)."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


class S3Storage:
    def __init__(self, bucket: str, prefix: str = "") -> None:
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for S3 storage. "
                "Install with: pip install hlspkg[s3]"
            )
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._s3 = boto3.client("s3")

    def _full_key(self, key: str) -> str:
        if self._prefix:
            return f"{self._prefix}/{key}"
        return key

    def get_file(self, key: str, local_dest: Path) -> Path:
        full_key = self._full_key(key)
        local_dest.parent.mkdir(parents=True, exist_ok=True)
        log.info("Downloading s3://%s/%s → %s", self._bucket, full_key, local_dest)
        self._s3.download_file(self._bucket, full_key, str(local_dest))
        return local_dest

    def put_file(self, local_path: Path, dest_key: str) -> str:
        full_key = self._full_key(dest_key)
        log.info("Uploading %s → s3://%s/%s", local_path, self._bucket, full_key)
        self._s3.upload_file(str(local_path), self._bucket, full_key)
        return f"s3://{self._bucket}/{full_key}"

    def base_url(self, key: str) -> str:
        full_key = self._full_key(key)
        return f"s3://{self._bucket}/{full_key}"
