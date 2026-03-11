"""Pipeline orchestration: preflight → transcode → package → publish."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

from hlspkg.config.schema import AppConfig
from hlspkg.core.encoder import detect_encoder
from hlspkg.core.package import package
from hlspkg.core.preflight import build_encoding_plan, probe_input
from hlspkg.core.transcode import transcode
from hlspkg.publish.publisher import publish
from hlspkg.storage.base import StorageBackend

log = logging.getLogger(__name__)


def run_pipeline(
    input_key: str,
    input_storage: StorageBackend,
    output_storage: StorageBackend,
    config: AppConfig,
    asset_id: str | None = None,
    version: str = "v1",
    force_cpu: bool = False,
) -> str:
    """Run the full VOD pipeline. Returns the published asset URL/path."""
    asset_id = asset_id or uuid.uuid4().hex[:12]
    log.info("Starting pipeline for %s (asset_id=%s, version=%s)", input_key, asset_id, version)

    # Detect best available encoder
    encoder = detect_encoder(config, force_cpu=force_cpu)

    with tempfile.TemporaryDirectory(prefix="hlspkg_") as tmp:
        work_dir = Path(tmp)

        # 1. Download source
        source_path = work_dir / "source"
        log.info("Fetching input: %s", input_key)
        input_storage.get_file(input_key, source_path)

        # 2. Preflight
        log.info("Probing input...")
        probe = probe_input(source_path)
        plan = build_encoding_plan(probe, config)

        # 3. Transcode
        log.info("Transcoding...")
        tc_output = transcode(
            source_path, probe, plan, config, work_dir / "transcode", encoder
        )

        # 4. Package
        log.info("Packaging CMAF HLS...")
        pkg_output = package(tc_output, config, work_dir / "package")

        # 5. Publish
        log.info("Publishing...")
        result_url = publish(pkg_output, asset_id, version, config, output_storage)

    log.info("Pipeline complete: %s", result_url)
    return result_url
