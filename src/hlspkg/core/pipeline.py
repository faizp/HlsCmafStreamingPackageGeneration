"""Pipeline orchestration: preflight → transcode → package → publish."""

from __future__ import annotations

import logging
import tempfile
import time
import uuid
from pathlib import Path

from hlspkg.config.schema import AppConfig
from hlspkg.core.encoder import (
    EncoderType,
    ResolvedEncoder,
    check_hwaccel_decode,
    detect_encoder,
)
from hlspkg.core.package import package
from hlspkg.core.preflight import build_encoding_plans, probe_input
from hlspkg.core.transcode import transcode_abr
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
    # Silence noisy AWS SDK loggers
    for name in ("boto3", "botocore", "s3transfer", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)

    asset_id = asset_id or uuid.uuid4().hex[:12]
    log.info("Starting pipeline for %s (asset_id=%s, version=%s)", input_key, asset_id, version)
    pipeline_start = time.monotonic()
    step_times: dict[str, float] = {}

    # Detect best available encoder
    encoder = detect_encoder(config, force_cpu=force_cpu)

    with tempfile.TemporaryDirectory(prefix="hlspkg_") as tmp:
        work_dir = Path(tmp)

        # 1. Download source
        t0 = time.monotonic()
        source_path = work_dir / "source"
        input_storage.get_file(input_key, source_path)
        step_times["download"] = time.monotonic() - t0
        log.info("Source downloaded")

        # 2. Preflight
        log.info("Probing input...")
        probe = probe_input(source_path)
        plans = build_encoding_plans(probe, config)

        # 2b. CUVID hardware decode detection
        if encoder.is_gpu and encoder.type == EncoderType.NVENC:
            if check_hwaccel_decode(
                probe.codec_name, source_path,
                scale_filter=config.video.encoders.nvenc.scale_filter,
            ):
                encoder = ResolvedEncoder(
                    type=encoder.type, is_gpu=True, name=encoder.name,
                    hwaccel_decode=True,
                )
                log.info("CUVID hardware decode enabled for %s", probe.codec_name)

        # 3. Transcode
        t0 = time.monotonic()
        log.info("Transcoding %d rendition(s)...", len(plans))
        tc_output = transcode_abr(
            source_path, probe, plans, config, work_dir / "transcode", encoder
        )
        step_times["transcode"] = time.monotonic() - t0

        # 4. Package
        t0 = time.monotonic()
        log.info("Packaging CMAF HLS...")
        pkg_output = package(tc_output, config, work_dir / "package")
        step_times["package"] = time.monotonic() - t0

        # 5. Publish
        t0 = time.monotonic()
        total_files = (
            len(pkg_output.init_segments)
            + len(pkg_output.segments)
            + len(pkg_output.variant_playlists)
            + 1  # master playlist
        )
        result_url = publish(pkg_output, asset_id, version, config, output_storage)
        step_times["upload"] = time.monotonic() - t0
        log.info("Upload complete")

    total = time.monotonic() - pipeline_start
    step_times["total"] = total

    log.info("--- Pipeline Summary ---")
    log.info("  Download:   %6.1fs", step_times["download"])
    log.info("  Transcode:  %6.1fs", step_times["transcode"])
    log.info("  Package:    %6.1fs", step_times["package"])
    log.info("  Upload:     %6.1fs", step_times["upload"])
    log.info("  Total:      %6.1fs", total)
    log.info("  Renditions: %d | Files uploaded: %d", len(plans), total_files)
    log.info("  Output:     %s", result_url)

    return result_url
