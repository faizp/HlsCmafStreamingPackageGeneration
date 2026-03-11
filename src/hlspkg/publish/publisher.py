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

    try:
        # 1. Init segments first
        for init_seg in pkg.init_segments:
            key = _dest_key(init_seg)
            log.debug("Publishing init segment: %s", key)
            storage.put_file(init_seg, key)

        # 2. Media segments
        for seg in pkg.segments:
            key = _dest_key(seg)
            log.debug("Publishing segment: %s", key)
            storage.put_file(seg, key)

        # 3. Variant playlists
        for playlist in pkg.variant_playlists:
            key = _dest_key(playlist)
            log.debug("Publishing variant playlist: %s", key)
            storage.put_file(playlist, key)

        # 4. Master playlist last (makes the asset "live")
        master_key = _dest_key(pkg.master_playlist)
        log.info("Publishing master playlist: %s", master_key)
        storage.put_file(pkg.master_playlist, master_key)

    except Exception as exc:
        raise PublishError(f"Failed to publish: {exc}") from exc

    return storage.base_url(layout)
