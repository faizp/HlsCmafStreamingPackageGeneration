"""Config-driven CMAF HLS packaging via Shaka Packager."""

from __future__ import annotations

import logging
from pathlib import Path

from hlspkg.config.schema import AppConfig
from hlspkg.models import PackageOutput, TranscodeOutput
from hlspkg.shakautil import run_shaka

log = logging.getLogger(__name__)


def _collect_outputs(hls_dir: Path) -> PackageOutput:
    """Walk the HLS output directory and categorize files."""
    master = hls_dir / "master.m3u8"
    variants: list[Path] = []
    segments: list[Path] = []
    inits: list[Path] = []

    for p in sorted(hls_dir.rglob("*")):
        if not p.is_file():
            continue
        if p.name == "master.m3u8":
            continue
        if p.suffix == ".m3u8":
            variants.append(p)
        elif p.name.startswith("init") and p.suffix == ".mp4":
            inits.append(p)
        elif p.suffix == ".m4s":
            segments.append(p)

    return PackageOutput(
        base_dir=hls_dir,
        master_playlist=master,
        variant_playlists=variants,
        segments=segments,
        init_segments=inits,
    )


def package(
    tc_output: TranscodeOutput, config: AppConfig, work_dir: Path
) -> PackageOutput:
    """Package transcoded streams into CMAF HLS using Shaka Packager."""
    hls_dir = work_dir / "hls"
    hls_dir.mkdir(parents=True, exist_ok=True)

    seg_dur = config.packaging.segment_duration

    stream_descriptors: list[str] = []

    # Video stream descriptors (one per rendition)
    for video_path in tc_output.video_paths:
        # Derive rendition label from filename: video_720p.mp4 → 720p, video.mp4 → video
        stem = video_path.stem
        if stem.startswith("video_"):
            label = stem.replace("video_", "")
            dir_name = f"stream_video_{label}"
        else:
            dir_name = "stream_video"
            label = "video"

        video_dir = hls_dir / dir_name
        video_dir.mkdir(parents=True, exist_ok=True)

        video_desc = (
            f"in={video_path},"
            f"stream=video,"
            f"init_segment={video_dir / 'init.mp4'},"
            f"segment_template={video_dir / 'seg_$Number$.m4s'},"
            f"playlist_name={video_dir / 'stream.m3u8'}"
        )
        stream_descriptors.append(video_desc)

    # Audio stream descriptor (if present)
    if tc_output.audio_path is not None:
        audio_dir = hls_dir / "stream_audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        audio_desc = (
            f"in={tc_output.audio_path},"
            f"stream=audio,"
            f"init_segment={audio_dir / 'init.mp4'},"
            f"segment_template={audio_dir / 'seg_$Number$.m4s'},"
            f"playlist_name={audio_dir / 'stream.m3u8'},"
            f"hls_group_id=audio,"
            f"hls_name=default"
        )
        stream_descriptors.append(audio_desc)

    flags = [
        "--hls_master_playlist_output",
        str(hls_dir / "master.m3u8"),
        "--segment_duration",
        str(seg_dur),
    ]

    log.info("Packaging CMAF HLS → %s", hls_dir)
    run_shaka(stream_descriptors, flags)

    return _collect_outputs(hls_dir)
