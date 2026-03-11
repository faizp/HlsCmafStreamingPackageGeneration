"""GPU encoder detection with CPU fallback."""

from __future__ import annotations

import enum
import logging
import subprocess
from dataclasses import dataclass

from hlspkg.config.schema import AppConfig

log = logging.getLogger(__name__)


class EncoderType(enum.Enum):
    NVENC = "nvenc"
    VIDEOTOOLBOX = "videotoolbox"
    CPU = "cpu"


@dataclass(frozen=True)
class ResolvedEncoder:
    type: EncoderType
    is_gpu: bool
    name: str


_ENCODER_MAP: dict[str, EncoderType] = {
    "nvenc": EncoderType.NVENC,
    "videotoolbox": EncoderType.VIDEOTOOLBOX,
    "cpu": EncoderType.CPU,
}

_CODEC_FOR_TYPE: dict[EncoderType, str] = {
    EncoderType.NVENC: "h264_nvenc",
    EncoderType.VIDEOTOOLBOX: "h264_videotoolbox",
    EncoderType.CPU: "libx264",
}


def _ffmpeg_has_encoder(codec: str) -> bool:
    """Check if ffmpeg reports the encoder as available."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        return codec in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _smoke_test_encoder(codec: str) -> bool:
    """Run a zero-frame encode to confirm the encoder actually works at runtime.

    Uses a software lavfi source without hwaccel so the test works regardless
    of whether the encoder expects GPU or CPU input frames — NVENC can accept
    system-memory frames and will upload internally.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-f", "lavfi", "-i", "color=black:s=256x256:d=0.04:r=25",
        "-frames:v", "1",
        "-c:v", codec,
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, check=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        log.debug("Smoke test for %s failed: %s", codec, exc.stderr.strip())
        return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def detect_encoder(config: AppConfig, force_cpu: bool = False) -> ResolvedEncoder:
    """Auto-detect the best available encoder.

    Walks ``config.video.encoder_preference`` and returns the first encoder
    that is both listed by ffmpeg *and* passes a zero-frame smoke test.
    Falls back to CPU if nothing else works.
    """
    if force_cpu:
        log.info("Encoder: CPU (forced via --cpu)")
        return ResolvedEncoder(type=EncoderType.CPU, is_gpu=False, name="CPU")

    for name in config.video.encoder_preference:
        enc_type = _ENCODER_MAP.get(name)
        if enc_type is None:
            log.warning("Unknown encoder name '%s' in encoder_preference, skipping", name)
            continue

        if enc_type == EncoderType.CPU:
            # CPU is always the final fallback — no smoke test needed
            break

        codec = _CODEC_FOR_TYPE[enc_type]
        log.debug("Probing encoder: %s (codec=%s)", name, codec)

        if not _ffmpeg_has_encoder(codec):
            log.debug("Encoder %s not listed by ffmpeg, skipping", codec)
            continue

        if _smoke_test_encoder(codec):
            display = {
                EncoderType.NVENC: "NVENC",
                EncoderType.VIDEOTOOLBOX: "VideoToolbox",
            }[enc_type]
            log.info("Encoder: %s (auto-detected)", display)
            return ResolvedEncoder(type=enc_type, is_gpu=True, name=display)
        else:
            log.debug("Encoder %s smoke test failed, skipping", codec)

    log.info("Encoder: CPU (fallback)")
    return ResolvedEncoder(type=EncoderType.CPU, is_gpu=False, name="CPU")
