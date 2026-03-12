"""Core data models for the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProbeResult:
    """Raw ffprobe output, parsed into usable fields."""

    width: int
    height: int
    fps: float
    duration: float
    codec_name: str
    pix_fmt: str
    has_audio: bool
    audio_codec: str | None = None
    audio_channels: int | None = None
    audio_sample_rate: int | None = None


@dataclass
class EncodingPlan:
    """Resolved encoding parameters for a single rendition."""

    target_width: int
    target_height: int
    target_fps: float
    crf: int
    maxrate: str
    bufsize: str
    keyint: int
    needs_scale: bool
    needs_fps_cap: bool


@dataclass
class TranscodeOutput:
    """Paths to transcoded elementary streams."""

    video_paths: list[Path] = field(default_factory=list)
    audio_path: Path | None = None


@dataclass
class PackageOutput:
    """Paths to the CMAF HLS package on disk."""

    base_dir: Path
    master_playlist: Path
    variant_playlists: list[Path] = field(default_factory=list)
    segments: list[Path] = field(default_factory=list)
    init_segments: list[Path] = field(default_factory=list)
