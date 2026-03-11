"""Config-driven ffmpeg transcoding with GPU encoder support."""

from __future__ import annotations

import logging
from pathlib import Path

from hlspkg.config.schema import AppConfig
from hlspkg.core.encoder import EncoderType, ResolvedEncoder
from hlspkg.exceptions import TranscodeError
from hlspkg.ffutil import run_ffmpeg
from hlspkg.models import EncodingPlan, ProbeResult, TranscodeOutput

log = logging.getLogger(__name__)


def _build_encoder_args(
    plan: EncodingPlan, config: AppConfig, encoder: ResolvedEncoder,
) -> list[str]:
    """Build codec-specific encoding flags."""
    args: list[str] = []

    if encoder.type == EncoderType.CPU:
        cpu = config.video.encoders.cpu
        args.extend([
            "-c:v", cpu.codec,
            "-preset", cpu.preset,
            "-crf", str(plan.crf),
        ])

    elif encoder.type == EncoderType.NVENC:
        nvenc = config.video.encoders.nvenc
        args.extend([
            "-c:v", nvenc.codec,
            "-preset", nvenc.preset,
            "-rc", nvenc.rc,
            "-cq", str(nvenc.cq),
        ])
        if nvenc.extra_args:
            args.extend(nvenc.extra_args)

    elif encoder.type == EncoderType.VIDEOTOOLBOX:
        vt = config.video.encoders.videotoolbox
        args.extend([
            "-c:v", vt.codec,
            "-q:v", str(vt.quality),
        ])
        if not vt.realtime:
            args.extend(["-realtime", "false"])
        if vt.extra_args:
            args.extend(vt.extra_args)

    return args


def _build_video_filter(
    plan: EncodingPlan, config: AppConfig, encoder: ResolvedEncoder,
) -> str:
    """Build the -vf filter chain.

    All encoders (including NVENC) use CPU-side filters. NVENC accepts
    CPU-memory frames and handles the upload to GPU internally, which
    avoids fragile hwaccel/cuvid dependencies.
    """
    filters: list[str] = []

    if encoder.type == EncoderType.VIDEOTOOLBOX:
        scale_filter = config.video.encoders.videotoolbox.scale_filter
    else:
        scale_filter = "scale"

    if plan.needs_scale:
        filters.append(f"{scale_filter}={plan.target_width}:{plan.target_height}")
    if plan.needs_fps_cap:
        filters.append(f"fps={plan.target_fps}")
    filters.append(f"format={config.video.pix_fmt}")

    return ",".join(filters)


def build_video_args(
    input_path: Path,
    plan: EncodingPlan,
    config: AppConfig,
    output_path: Path,
    encoder: ResolvedEncoder,
) -> list[str]:
    """Build ffmpeg args for video-only transcoding."""
    vf = _build_video_filter(plan, config, encoder)

    args: list[str] = []
    args.extend(["-i", str(input_path)])
    args.append("-an")
    args.extend(["-vf", vf])

    # Codec-specific encoder args
    args.extend(_build_encoder_args(plan, config, encoder))

    # Rate control (maxrate/bufsize apply to all encoders)
    args.extend(["-maxrate", plan.maxrate, "-bufsize", plan.bufsize])

    # GOP settings
    args.extend([
        "-g", str(plan.keyint),
        "-keyint_min", str(plan.keyint),
        "-sc_threshold", str(config.video.sc_threshold),
    ])

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
    input_path: Path,
    probe: ProbeResult,
    plan: EncodingPlan,
    config: AppConfig,
    work_dir: Path,
    encoder: ResolvedEncoder,
) -> TranscodeOutput:
    """Transcode video (and optionally audio) to intermediate files.

    If a GPU encoder fails at runtime, automatically retries with CPU.
    """
    work_dir.mkdir(parents=True, exist_ok=True)

    video_out = work_dir / "video.mp4"
    log.info("Transcoding video → %s (encoder=%s)", video_out, encoder.name)
    video_args = build_video_args(input_path, plan, config, video_out, encoder)

    try:
        run_ffmpeg(video_args, error_cls=TranscodeError)
    except TranscodeError:
        if encoder.is_gpu:
            log.warning(
                "GPU encoder %s failed at runtime, falling back to CPU", encoder.name
            )
            cpu_encoder = ResolvedEncoder(
                type=EncoderType.CPU, is_gpu=False, name="CPU"
            )
            video_args = build_video_args(
                input_path, plan, config, video_out, cpu_encoder,
            )
            run_ffmpeg(video_args, error_cls=TranscodeError)
        else:
            raise

    audio_out: Path | None = None
    if probe.has_audio:
        audio_out = work_dir / "audio.m4a"
        log.info("Transcoding audio → %s", audio_out)
        audio_args = build_audio_args(input_path, config, audio_out)
        run_ffmpeg(audio_args, error_cls=TranscodeError)

    return TranscodeOutput(video_path=video_out, audio_path=audio_out)
