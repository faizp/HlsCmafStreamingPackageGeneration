"""Thin subprocess wrappers for ffmpeg and ffprobe."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from hlspkg.exceptions import PreflightError, TranscodeError, PackageError

log = logging.getLogger(__name__)


def run_ffprobe(input_path: Path) -> dict:
    """Run ffprobe and return parsed JSON output."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]
    log.debug("ffprobe command: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise PreflightError(f"ffprobe failed: {exc.stderr}") from exc
    except FileNotFoundError:
        raise PreflightError("ffprobe not found — is ffmpeg installed?")
    return json.loads(result.stdout)


def run_ffmpeg(args: list[str], *, error_cls: type[Exception] = TranscodeError) -> None:
    """Run ffmpeg with the given arguments."""
    cmd = ["ffmpeg", "-y", *args]
    log.debug("ffmpeg command: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise error_cls(f"ffmpeg failed: {exc.stderr}") from exc
    except FileNotFoundError:
        raise error_cls("ffmpeg not found — is ffmpeg installed?")
