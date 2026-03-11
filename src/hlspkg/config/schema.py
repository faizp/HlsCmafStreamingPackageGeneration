"""Typed configuration dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VideoProfile:
    maxrate: str
    bufsize: str


@dataclass
class VideoConfig:
    codec: str
    preset: str
    crf: int
    pix_fmt: str
    max_height: int
    max_fps: float
    sc_threshold: int
    closed_gop: bool
    profiles: dict[int, VideoProfile] = field(default_factory=dict)


@dataclass
class AudioConfig:
    codec: str
    bitrate: str
    channels: int
    sample_rate: int


@dataclass
class PackagingConfig:
    segment_duration: int
    segment_type: str
    hls_version: int


@dataclass
class OutputConfig:
    layout: str


@dataclass
class AppConfig:
    video: VideoConfig
    audio: AudioConfig
    packaging: PackagingConfig
    output: OutputConfig
