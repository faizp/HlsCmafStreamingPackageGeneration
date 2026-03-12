"""Atomic publish: segments → variant playlists → master playlist."""

from __future__ import annotations

import logging
from pathlib import Path

from hlspkg.config.schema import AppConfig
from hlspkg.exceptions import PublishError
from hlspkg.models import PackageOutput
from hlspkg.storage.base import StorageBackend

log = logging.getLogger(__name__)


def publish(
    pkg: PackageOutput,
    asset_id: str,
    version: str,
    config: AppConfig,
    storage: StorageBackend,
) -> str:
    """Publish HLS package to output storage in atomic order.

    Returns the base URL/path for the published asset.
    """
    layout = config.output.layout.format(asset_id=asset_id, version=version)

    def _dest_key(local_path: Path) -> str:
        rel = local_path.relative_to(pkg.base_dir)
        return f"{layout}/{rel}"

    all_files = (
        list(pkg.init_segments)
        + list(pkg.segments)
        + list(pkg.variant_playlists)
        + [pkg.master_playlist]
    )
    total = len(all_files)

    try:
        # 1. Init segments first
        for init_seg in pkg.init_segments:
            storage.put_file(init_seg, _dest_key(init_seg))

        # 2. Media segments
        for seg in pkg.segments:
            storage.put_file(seg, _dest_key(seg))

        # 3. Variant playlists
        for playlist in pkg.variant_playlists:
            storage.put_file(playlist, _dest_key(playlist))

        # 4. Master playlist last (makes the asset "live")
        storage.put_file(pkg.master_playlist, _dest_key(pkg.master_playlist))

    except Exception as exc:
        raise PublishError(f"Failed to publish: {exc}") from exc

    log.debug("Published %d files to %s", total, storage.base_url(layout))
    return storage.base_url(layout)
