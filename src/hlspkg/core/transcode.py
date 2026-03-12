"""Config-driven ffmpeg transcoding with GPU encoder support."""

from __future__ import annotations

import logging
import time
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
    args.extend(["-g", str(plan.keyint), "-keyint_min", str(plan.keyint)])

    if encoder.type == EncoderType.NVENC:
        # NVENC: -strict_gop enforces fixed GOP
        args.extend(["-strict_gop", "1"])
    else:
        # libx264 / VideoToolbox: sc_threshold=0 disables scene-change keyframes
        args.extend(["-sc_threshold", str(config.video.sc_threshold)])

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

    return TranscodeOutput(video_paths=[video_out], audio_path=audio_out)


def _build_split_filter(
    plans: list[EncodingPlan], config: AppConfig, encoder: ResolvedEncoder,
) -> str:
    """Build a -filter_complex string that splits the input into N renditions.

    Example for 3 renditions:
      [0:v]split=3[s0][s1][s2];
      [s0]scale=1920:1080,fps=30,format=yuv420p[out0];
      [s1]scale=1280:720,fps=30,format=yuv420p[out1];
      [s2]scale=854:480,fps=30,format=yuv420p[out2]
    """
    n = len(plans)
    split_outputs = "".join(f"[s{i}]" for i in range(n))
    parts = [f"[0:v]split={n}{split_outputs}"]

    if encoder.type == EncoderType.VIDEOTOOLBOX:
        scale_filter = config.video.encoders.videotoolbox.scale_filter
    else:
        scale_filter = "scale"

    for i, plan in enumerate(plans):
        filters: list[str] = []
        # Always scale — even for the "native" rendition the split output
        # needs an explicit size so each branch has a defined resolution.
        filters.append(f"{scale_filter}={plan.target_width}:{plan.target_height}")
        if plan.needs_fps_cap:
            filters.append(f"fps={plan.target_fps}")
        filters.append(f"format={config.video.pix_fmt}")
        chain = ",".join(filters)
        parts.append(f"[s{i}]{chain}[out{i}]")

    return ";".join(parts)


def _build_split_args(
    input_path: Path,
    plans: list[EncodingPlan],
    config: AppConfig,
    output_paths: list[Path],
    encoder: ResolvedEncoder,
) -> list[str]:
    """Build ffmpeg args for single-decode, multi-output ABR transcoding."""
    fc = _build_split_filter(plans, config, encoder)

    args: list[str] = ["-i", str(input_path), "-an", "-filter_complex", fc]

    for i, (plan, out_path) in enumerate(zip(plans, output_paths)):
        args.extend(["-map", f"[out{i}]"])

        # Codec-specific encoder args
        if encoder.type == EncoderType.CPU:
            cpu = config.video.encoders.cpu
            args.extend([
                f"-c:v:{i}", cpu.codec,
                f"-preset:v:{i}", cpu.preset,
                f"-crf:v:{i}", str(plan.crf),
            ])
        elif encoder.type == EncoderType.NVENC:
            nvenc = config.video.encoders.nvenc
            args.extend([
                f"-c:v:{i}", nvenc.codec,
                f"-preset:v:{i}", nvenc.preset,
                f"-rc:v:{i}", nvenc.rc,
                f"-cq:v:{i}", str(nvenc.cq),
            ])
            if nvenc.extra_args:
                args.extend(nvenc.extra_args)
        elif encoder.type == EncoderType.VIDEOTOOLBOX:
            vt = config.video.encoders.videotoolbox
            args.extend([
                f"-c:v:{i}", vt.codec,
                f"-q:v:{i}", str(vt.quality),
            ])
            if not vt.realtime:
                args.extend(["-realtime", "false"])
            if vt.extra_args:
                args.extend(vt.extra_args)

        # Rate control
        args.extend([
            f"-maxrate:v:{i}", plan.maxrate,
            f"-bufsize:v:{i}", plan.bufsize,
        ])

        # GOP settings
        args.extend([
            f"-g:v:{i}", str(plan.keyint),
            f"-keyint_min:v:{i}", str(plan.keyint),
        ])

        if encoder.type == EncoderType.NVENC:
            args.extend([f"-strict_gop:v:{i}", "1"])
        else:
            args.extend([f"-sc_threshold:v:{i}", str(config.video.sc_threshold)])

        if config.video.closed_gop:
            args.extend([f"-flags:v:{i}", "+cgop"])

        args.extend(["-movflags", "+faststart", str(out_path)])

    return args


def transcode_abr(
    input_path: Path,
    probe: ProbeResult,
    plans: list[EncodingPlan],
    config: AppConfig,
    work_dir: Path,
    encoder: ResolvedEncoder,
) -> TranscodeOutput:
    """Transcode multiple renditions for ABR streaming.

    Uses a single-decode split approach: one ffmpeg call decodes the source
    once and fans out to all renditions via -filter_complex split.  If the
    split approach fails with a GPU encoder, falls back to sequential CPU.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    total = len(plans)
    abr_start = time.monotonic()

    # Build output paths
    video_paths = [work_dir / f"video_{p.target_height}p.mp4" for p in plans]
    rendition_labels = ", ".join(f"{p.target_height}p" for p in plans)

    log.info(
        "Transcoding %d renditions (%s) via split (encoder=%s)",
        total, rendition_labels, encoder.name,
    )

    split_args = _build_split_args(input_path, plans, config, video_paths, encoder)
    t0 = time.monotonic()

    try:
        run_ffmpeg(
            split_args, error_cls=TranscodeError,
            duration=probe.duration, label=f"video {rendition_labels}",
        )
    except TranscodeError:
        if encoder.is_gpu:
            log.warning(
                "GPU split encode failed (%s), falling back to sequential CPU",
                encoder.name,
            )
            cpu_encoder = ResolvedEncoder(
                type=EncoderType.CPU, is_gpu=False, name="CPU",
            )
            split_args = _build_split_args(
                input_path, plans, config, video_paths, cpu_encoder,
            )
            run_ffmpeg(
                split_args, error_cls=TranscodeError,
                duration=probe.duration, label=f"video {rendition_labels} (CPU)",
            )
        else:
            raise

    video_elapsed = time.monotonic() - t0
    log.info("All %d video renditions done in %.1fs", total, video_elapsed)

    # Audio — transcoded once, shared across renditions
    audio_out: Path | None = None
    if probe.has_audio:
        audio_out = work_dir / "audio.m4a"
        log.info("Transcoding audio...")
        t0 = time.monotonic()
        audio_args = build_audio_args(input_path, config, audio_out)
        run_ffmpeg(
            audio_args, error_cls=TranscodeError,
            duration=probe.duration, label="audio",
        )
        log.info("Audio done in %.1fs", time.monotonic() - t0)

    total_elapsed = time.monotonic() - abr_start
    log.info(
        "All %d rendition(s) + audio transcoded in %.1fs",
        total, total_elapsed,
    )
    return TranscodeOutput(video_paths=video_paths, audio_path=audio_out)
