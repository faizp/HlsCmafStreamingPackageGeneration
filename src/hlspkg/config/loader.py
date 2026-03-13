"""Load YAML config, merge with CLI overrides, return validated AppConfig."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from hlspkg.config.schema import (
    AppConfig,
    AudioConfig,
    CpuEncoderConfig,
    EncodersConfig,
    NvencEncoderConfig,
    OutputConfig,
    PackagingConfig,
    VideoConfig,
    VideoProfile,
    VideotoolboxEncoderConfig,
)

_DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "config" / "default.yaml"
# In Docker, config is at /app/config/default.yaml
_DOCKER_CONFIG = Path("/app/config/default.yaml")


def _find_default_config() -> Path:
    if _DEFAULT_CONFIG.exists():
        return _DEFAULT_CONFIG
    if _DOCKER_CONFIG.exists():
        return _DOCKER_CONFIG
    raise FileNotFoundError(
        f"Default config not found at {_DEFAULT_CONFIG} or {_DOCKER_CONFIG}"
    )


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _parse_profiles(raw: dict[str, Any]) -> dict[int, VideoProfile]:
    """Convert profile keys to ints (0 for 'default')."""
    profiles: dict[int, VideoProfile] = {}
    for key, val in raw.items():
        int_key = 0 if key == "default" else int(key)
        profiles[int_key] = VideoProfile(maxrate=val["maxrate"], bufsize=val["bufsize"])
    return profiles


def _parse_encoder_configs(raw: dict[str, Any]) -> EncodersConfig:
    """Parse the encoders sub-section into typed dataclasses."""
    cpu_raw = raw["cpu"]
    nvenc_raw = raw["nvenc"]
    vt_raw = raw["videotoolbox"]

    return EncodersConfig(
        cpu=CpuEncoderConfig(
            codec=cpu_raw["codec"],
            preset=cpu_raw["preset"],
            crf=int(cpu_raw["crf"]),
        ),
        nvenc=NvencEncoderConfig(
            codec=nvenc_raw["codec"],
            preset=nvenc_raw["preset"],
            cq=int(nvenc_raw["cq"]),
            rc=nvenc_raw["rc"],
            hwaccel=nvenc_raw["hwaccel"],
            hwaccel_output_format=nvenc_raw["hwaccel_output_format"],
            scale_filter=nvenc_raw["scale_filter"],
            scale_interp=nvenc_raw.get("scale_interp", "super"),
            extra_args=list(nvenc_raw.get("extra_args", [])),
        ),
        videotoolbox=VideotoolboxEncoderConfig(
            codec=vt_raw["codec"],
            quality=int(vt_raw["quality"]),
            realtime=bool(vt_raw.get("realtime", False)),
            scale_filter=vt_raw["scale_filter"],
            extra_args=list(vt_raw.get("extra_args", [])),
        ),
    )


def _build_config(data: dict[str, Any]) -> AppConfig:
    v = data["video"]
    a = data["audio"]
    p = data["packaging"]
    o = data["output"]

    return AppConfig(
        video=VideoConfig(
            pix_fmt=v["pix_fmt"],
            max_height=int(v["max_height"]),
            max_fps=float(v["max_fps"]),
            sc_threshold=int(v["sc_threshold"]),
            closed_gop=bool(v["closed_gop"]),
            encoder_preference=list(v.get("encoder_preference", ["cpu"])),
            encoders=_parse_encoder_configs(v["encoders"]),
            profiles=_parse_profiles(v.get("profiles", {})),
            renditions=[int(h) for h in v.get("renditions", [])],
        ),
        audio=AudioConfig(
            codec=a["codec"],
            bitrate=a["bitrate"],
            channels=int(a["channels"]),
            sample_rate=int(a["sample_rate"]),
        ),
        packaging=PackagingConfig(
            segment_duration=int(p["segment_duration"]),
            segment_type=p["segment_type"],
            hls_version=int(p["hls_version"]),
        ),
        output=OutputConfig(layout=o["layout"]),
    )


def load_config(
    override_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> AppConfig:
    """Load default config, merge optional override file and CLI flags."""
    default_path = _find_default_config()
    with open(default_path) as f:
        data = yaml.safe_load(f)

    if override_path:
        with open(override_path) as f:
            override_data = yaml.safe_load(f) or {}
        data = _deep_merge(data, override_data)

    # Apply CLI overrides
    if cli_overrides:
        if "crf" in cli_overrides:
            data["video"]["encoders"]["cpu"]["crf"] = cli_overrides["crf"]
        if "segment_duration" in cli_overrides:
            data["packaging"]["segment_duration"] = cli_overrides["segment_duration"]
        if "renditions" in cli_overrides:
            data["video"]["renditions"] = cli_overrides["renditions"]

    return _build_config(data)
