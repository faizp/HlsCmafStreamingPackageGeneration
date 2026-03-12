"""Probe input and build an encoding plan from config."""

from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path

from hlspkg.config.schema import AppConfig
from hlspkg.exceptions import PreflightError
from hlspkg.ffutil import run_ffprobe
from hlspkg.models import EncodingPlan, ProbeResult

log = logging.getLogger(__name__)


def probe_input(path: Path) -> ProbeResult:
    """Run ffprobe on input and return a structured ProbeResult."""
    data = run_ffprobe(path)
    streams = data.get("streams", [])

    video_stream = next((s for s in streams if s["codec_type"] == "video"), None)
    if video_stream is None:
        raise PreflightError("No video stream found in input")

    audio_stream = next((s for s in streams if s["codec_type"] == "audio"), None)

    # Parse FPS from r_frame_rate (e.g., "30000/1001")
    fps_str = video_stream.get("r_frame_rate", "30/1")
    try:
        fps = float(Fraction(fps_str))
    except (ValueError, ZeroDivisionError):
        fps = 30.0

    duration_str = data.get("format", {}).get("duration", "0")
    duration = float(duration_str) if duration_str else 0.0

    return ProbeResult(
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=fps,
        duration=duration,
        codec_name=video_stream.get("codec_name", "unknown"),
        pix_fmt=video_stream.get("pix_fmt", "unknown"),
        has_audio=audio_stream is not None,
        audio_codec=audio_stream.get("codec_name") if audio_stream else None,
        audio_channels=int(audio_stream["channels"]) if audio_stream else None,
        audio_sample_rate=(
            int(audio_stream["sample_rate"]) if audio_stream else None
        ),
    )


def _lookup_profile(height: int, config: AppConfig) -> tuple[str, str]:
    """Find the maxrate/bufsize for a given output height."""
    profiles = config.video.profiles
    # Try exact match first, then fallback to closest lower tier, then default
    for tier in sorted(profiles.keys(), reverse=True):
        if tier == 0:
            continue
        if height >= tier:
            p = profiles[tier]
            return p.maxrate, p.bufsize
    # Use default (key 0)
    if 0 in profiles:
        p = profiles[0]
        return p.maxrate, p.bufsize
    return "1500k", "3000k"


def build_encoding_plan(probe: ProbeResult, config: AppConfig) -> EncodingPlan:
    """Determine target encoding parameters from probe + config."""
    # Resolve target height: never upscale
    target_height = min(probe.height, config.video.max_height)
    # Keep even numbers for codec compatibility
    target_height = target_height - (target_height % 2)

    # Scale width proportionally, keep even
    scale_factor = target_height / probe.height
    target_width = round(probe.width * scale_factor)
    target_width = target_width + (target_width % 2)  # round up to even

    needs_scale = target_height != probe.height

    # Cap FPS
    target_fps = min(probe.fps, config.video.max_fps)
    needs_fps_cap = target_fps < probe.fps

    # Lookup bitrate profile
    maxrate, bufsize = _lookup_profile(target_height, config)

    # GOP = fps * segment_duration
    keyint = round(target_fps * config.packaging.segment_duration)

    log.info(
        "Encoding plan: %dx%d @ %.2f fps, crf=%d, maxrate=%s, gop=%d%s%s",
        target_width,
        target_height,
        target_fps,
        config.video.crf,
        maxrate,
        keyint,
        " (scaled)" if needs_scale else "",
        " (fps capped)" if needs_fps_cap else "",
    )

    return EncodingPlan(
        target_width=target_width,
        target_height=target_height,
        target_fps=target_fps,
        crf=config.video.crf,
        maxrate=maxrate,
        bufsize=bufsize,
        keyint=keyint,
        needs_scale=needs_scale,
        needs_fps_cap=needs_fps_cap,
    )


def _build_plan_for_height(
    height: int, probe: ProbeResult, config: AppConfig,
) -> EncodingPlan:
    """Build an EncodingPlan for a specific target height."""
    target_height = height - (height % 2)

    scale_factor = target_height / probe.height
    target_width = round(probe.width * scale_factor)
    target_width = target_width + (target_width % 2)

    needs_scale = target_height != probe.height

    target_fps = min(probe.fps, config.video.max_fps)
    needs_fps_cap = target_fps < probe.fps

    maxrate, bufsize = _lookup_profile(target_height, config)
    keyint = round(target_fps * config.packaging.segment_duration)

    log.info(
        "Encoding plan [%dp]: %dx%d @ %.2f fps, crf=%d, maxrate=%s, gop=%d%s%s",
        target_height,
        target_width,
        target_height,
        target_fps,
        config.video.crf,
        maxrate,
        keyint,
        " (scaled)" if needs_scale else "",
        " (fps capped)" if needs_fps_cap else "",
    )

    return EncodingPlan(
        target_width=target_width,
        target_height=target_height,
        target_fps=target_fps,
        crf=config.video.crf,
        maxrate=maxrate,
        bufsize=bufsize,
        keyint=keyint,
        needs_scale=needs_scale,
        needs_fps_cap=needs_fps_cap,
    )


def build_encoding_plans(
    probe: ProbeResult, config: AppConfig,
) -> list[EncodingPlan]:
    """Build encoding plans for ABR renditions.

    If no renditions configured, falls back to single-rendition via
    build_encoding_plan().
    """
    renditions = config.video.renditions
    if not renditions:
        return [build_encoding_plan(probe, config)]

    source_height = probe.height
    max_height = config.video.max_height

    # Cap at max_height (no upscaling past source either)
    top_height = min(source_height, max_height)

    # Filter ladder entries: no upscaling past source, respect max_height
    valid = sorted([h for h in renditions if h <= top_height], reverse=True)

    # Include top_height as the highest rendition, but skip if the
    # highest ladder entry is within 5% (e.g. 1090p source ≈ 1080p)
    _MIN_GAP_RATIO = 0.05
    if valid and abs(valid[0] - top_height) / top_height <= _MIN_GAP_RATIO:
        # Close enough — use the ladder entry as the top rendition
        pass
    elif not valid or valid[0] != top_height:
        valid.insert(0, top_height)

    log.info(
        "ABR rendition ladder: %s (source=%dp)",
        [f"{h}p" for h in valid],
        source_height,
    )

    return [_build_plan_for_height(h, probe, config) for h in valid]
