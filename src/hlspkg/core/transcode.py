"""Config-driven ffmpeg transcoding."""

from __future__ import annotations

import logging
from pathlib import Path

from hlspkg.config.schema import AppConfig
from hlspkg.exceptions import TranscodeError
from hlspkg.ffutil import run_ffmpeg
from hlspkg.models import EncodingPlan, ProbeResult, TranscodeOutput

log = logging.getLogger(__name__)


def _build_video_filter(plan: EncodingPlan, config: AppConfig) -> str:
    """Build the -vf filter chain."""
    filters: list[str] = []
    if plan.needs_scale:
        filters.append(f"scale={plan.target_width}:{plan.target_height}")
    if plan.needs_fps_cap:
        filters.append(f"fps={plan.target_fps}")
    filters.append(f"format={config.video.pix_fmt}")
    return ",".join(filters)


def build_video_args(
    input_path: Path, plan: EncodingPlan, config: AppConfig, output_path: Path
) -> list[str]:
    """Build ffmpeg args for video-only transcoding."""
    vf = _build_video_filter(plan, config)
    args = [
        "-i", str(input_path),
        "-an",
        "-vf", vf,
        "-c:v", config.video.codec,
        "-preset", config.video.preset,
        "-crf", str(plan.crf),
        "-maxrate", plan.maxrate,
        "-bufsize", plan.bufsize,
        "-g", str(plan.keyint),
        "-keyint_min", str(plan.keyint),
        "-sc_threshold", str(config.video.sc_threshold),
    ]
    if config.video.closed_gop:
        args.extend(["-flags", "+cgop"])
    args.extend(["-movflags", "+faststart", str(output_path)])
    return args


def build_audio_args(
    input_path: Path, config: AppConfig, output_path: Path
) -> list[str]:
    """Build ffmpeg args for audio-only transcoding."""
    return [
        "-i", str(input_path),
        "-vn",
        "-c:a", config.audio.codec,
        "-b:a", config.audio.bitrate,
        "-ac", str(config.audio.channels),
        "-ar", str(config.audio.sample_rate),
        str(output_path),
    ]


def transcode(
    input_path: Path, probe: ProbeResult, plan: EncodingPlan,
    config: AppConfig, work_dir: Path,
) -> TranscodeOutput:
    """Transcode video (and optionally audio) to intermediate files."""
    work_dir.mkdir(parents=True, exist_ok=True)

    video_out = work_dir / "video.mp4"
    log.info("Transcoding video → %s", video_out)
    video_args = build_video_args(input_path, plan, config, video_out)
    run_ffmpeg(video_args, error_cls=TranscodeError)

    audio_out: Path | None = None
    if probe.has_audio:
        audio_out = work_dir / "audio.m4a"
        log.info("Transcoding audio → %s", audio_out)
        audio_args = build_audio_args(input_path, config, audio_out)
        run_ffmpeg(audio_args, error_cls=TranscodeError)

    return TranscodeOutput(video_path=video_out, audio_path=audio_out)
