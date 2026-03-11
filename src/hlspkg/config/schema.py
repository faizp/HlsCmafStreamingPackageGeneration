"""Typed configuration dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VideoProfile:
    maxrate: str
    bufsize: str


@dataclass
class CpuEncoderConfig:
    codec: str
    preset: str
    crf: int


@dataclass
class NvencEncoderConfig:
    codec: str
    preset: str
    cq: int
    rc: str
    hwaccel: str
    hwaccel_output_format: str
    scale_filter: str
    extra_args: list[str] = field(default_factory=list)


@dataclass
class VideotoolboxEncoderConfig:
    codec: str
    quality: int
    realtime: bool
    scale_filter: str
    extra_args: list[str] = field(default_factory=list)


@dataclass
class EncodersConfig:
    cpu: CpuEncoderConfig
    nvenc: NvencEncoderConfig
    videotoolbox: VideotoolboxEncoderConfig


@dataclass
class VideoConfig:
    pix_fmt: str
    max_height: int
    max_fps: float
    sc_threshold: int
    closed_gop: bool
    encoder_preference: list[str]
    encoders: EncodersConfig
    profiles: dict[int, VideoProfile] = field(default_factory=dict)

    @property
    def crf(self) -> int:
        """Backward-compat: delegates to CPU encoder config."""
        return self.encoders.cpu.crf


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
