"""Config-driven CMAF HLS packaging."""

from __future__ import annotations

import logging
from pathlib import Path

from hlspkg.config.schema import AppConfig
from hlspkg.exceptions import PackageError
from hlspkg.ffutil import run_ffmpeg
from hlspkg.models import PackageOutput, TranscodeOutput

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
    """Package transcoded streams into CMAF HLS."""
    hls_dir = work_dir / "hls"
    hls_dir.mkdir(parents=True, exist_ok=True)

    seg_dur = config.packaging.segment_duration

    if tc_output.audio_path is not None:
        # Mux video + audio with separate CMAF tracks
        args = [
            "-i", str(tc_output.video_path),
            "-i", str(tc_output.audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c", "copy",
            "-f", "hls",
            "-hls_time", str(seg_dur),
            "-hls_playlist_type", "vod",
            "-hls_segment_type", config.packaging.segment_type,
            "-hls_fmp4_init_filename", "init.mp4",
            "-hls_flags", "independent_segments",
            "-hls_list_size", "0",
            "-hls_segment_filename", str(hls_dir / "stream_%v" / "seg_%03d.m4s"),
            "-master_pl_name", "master.m3u8",
            "-var_stream_map", "v:0,agroup:audio,name:video a:0,agroup:audio,name:audio",
            str(hls_dir / "stream_%v" / "stream.m3u8"),
        ]
    else:
        # Video-only
        args = [
            "-i", str(tc_output.video_path),
            "-c", "copy",
            "-f", "hls",
            "-hls_time", str(seg_dur),
            "-hls_playlist_type", "vod",
            "-hls_segment_type", config.packaging.segment_type,
            "-hls_fmp4_init_filename", "init.mp4",
            "-hls_flags", "independent_segments",
            "-hls_list_size", "0",
            "-hls_segment_filename", str(hls_dir / "stream_video" / "seg_%03d.m4s"),
            "-master_pl_name", "master.m3u8",
            str(hls_dir / "stream_video" / "stream.m3u8"),
        ]

    # Ensure output sub-directories exist
    (hls_dir / "stream_video").mkdir(parents=True, exist_ok=True)
    if tc_output.audio_path is not None:
        (hls_dir / "stream_audio").mkdir(parents=True, exist_ok=True)

    log.info("Packaging CMAF HLS → %s", hls_dir)
    run_ffmpeg(args, error_cls=PackageError)

    return _collect_outputs(hls_dir)
