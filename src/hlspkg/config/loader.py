"""Load YAML config, merge with CLI overrides, return validated AppConfig."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from hlspkg.config.schema import (
    AppConfig,
    AudioConfig,
    OutputConfig,
    PackagingConfig,
    VideoConfig,
    VideoProfile,
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


def _build_config(data: dict[str, Any]) -> AppConfig:
    v = data["video"]
    a = data["audio"]
    p = data["packaging"]
    o = data["output"]

    return AppConfig(
        video=VideoConfig(
            codec=v["codec"],
            preset=v["preset"],
            crf=int(v["crf"]),
            pix_fmt=v["pix_fmt"],
            max_height=int(v["max_height"]),
            max_fps=float(v["max_fps"]),
            sc_threshold=int(v["sc_threshold"]),
            closed_gop=bool(v["closed_gop"]),
            profiles=_parse_profiles(v.get("profiles", {})),
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
            data["video"]["crf"] = cli_overrides["crf"]
        if "segment_duration" in cli_overrides:
            data["packaging"]["segment_duration"] = cli_overrides["segment_duration"]

    return _build_config(data)
