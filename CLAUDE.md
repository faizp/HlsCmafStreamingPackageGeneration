# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Single-rendition VOD pipeline: takes any video file, transcodes it to a single rendition (1080p max, no upscaling), and packages it as CMAF HLS for VOD streaming. Runs in Docker with ffmpeg. All encoding parameters are externalized to `config/default.yaml`.

## Repository

- Remote: https://github.com/faizp/HlsCmafStreamingPackageGeneration.git
- Branch: main

## Tech Stack

- Python 3.12, hatchling build system
- Docker (ffmpeg + Python bundled)
- click (CLI), PyYAML (config), boto3 (optional S3)

## Project Structure

- `config/default.yaml` — All encoding/packaging tunables (single source of truth)
- `src/hlspkg/cli.py` — Click CLI entry point
- `src/hlspkg/config/` — Config schema (dataclasses) and YAML loader
- `src/hlspkg/core/` — Pipeline: preflight → transcode → package
- `src/hlspkg/storage/` — Pluggable I/O (local filesystem or S3)
- `src/hlspkg/publish/` — Atomic publish ordering
- `src/hlspkg/models.py` — Data models (ProbeResult, EncodingPlan, etc.)
- `src/hlspkg/ffutil.py` — ffmpeg/ffprobe subprocess wrappers
- `src/hlspkg/exceptions.py` — Error hierarchy

## Build & Run

```bash
# Build Docker image
docker compose build

# Local in, local out
docker compose run hlspkg /data/input/video.mp4 --output /data/output -v

# S3 in, S3 out
docker compose run hlspkg video.mp4 --input-storage s3://raw-bucket --output s3://cdn-bucket/content

# With config overrides
docker compose run hlspkg /data/input/video.mp4 --output /data/output --crf 20 --segment-duration 6

# Local dev install (requires ffmpeg on host)
pip install -e .
hlspkg /path/to/video.mp4 --output /tmp/output -v
```

## Configuration

Edit `config/default.yaml` to change encoding parameters. No Python changes needed for tuning. CLI flags `--crf` and `--segment-duration` override specific values. A full override YAML can be passed with `--config`.
