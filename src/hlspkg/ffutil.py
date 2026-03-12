"""Thin subprocess wrappers for ffmpeg and ffprobe."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import threading
from pathlib import Path

from hlspkg.exceptions import PreflightError, TranscodeError, PackageError

log = logging.getLogger(__name__)

_TIME_RE = re.compile(r"out_time_us=(\d+)")


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


def _drain_stderr(stream, collected: list[str]) -> None:
    """Read ffmpeg stderr in a background thread, log each line, collect for errors."""
    for line in stream:
        stripped = line.rstrip()
        if not stripped:
            continue
        collected.append(stripped)
        log.debug("ffmpeg: %s", stripped)
    stream.close()


def run_ffmpeg(
    args: list[str],
    *,
    error_cls: type[Exception] = TranscodeError,
    duration: float = 0.0,
    label: str = "",
) -> None:
    """Run ffmpeg with the given arguments.

    If *duration* > 0, prints a live progress percentage to stderr using
    ffmpeg's ``-progress pipe:1`` mechanism.

    ffmpeg's stderr (codec info, hwaccel status, warnings) is always
    streamed to the log at DEBUG level.
    """
    show_progress = duration > 0.0
    cmd = ["ffmpeg", "-y"]
    if show_progress:
        cmd.extend(["-progress", "pipe:1", "-nostats"])
    cmd.extend(args)
    log.debug("ffmpeg command: %s", " ".join(cmd))

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE if show_progress else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Drain stderr in background so it doesn't block and so we can log it
        stderr_lines: list[str] = []
        stderr_thread = threading.Thread(
            target=_drain_stderr, args=(proc.stderr, stderr_lines), daemon=True,
        )
        stderr_thread.start()

        if show_progress:
            last_pct = -1
            prefix = f"  {label}" if label else "  progress"
            for line in proc.stdout:  # type: ignore[union-attr]
                m = _TIME_RE.match(line.strip())
                if m:
                    elapsed_us = int(m.group(1))
                    pct = min(int(elapsed_us / (duration * 1_000_000) * 100), 100)
                    if pct != last_pct:
                        last_pct = pct
                        sys.stderr.write(f"\r{prefix}: {pct:3d}%")
                        sys.stderr.flush()
            sys.stderr.write(f"\r{prefix}: 100%\n")
            sys.stderr.flush()

        proc.wait()
        stderr_thread.join(timeout=5)

        if proc.returncode != 0:
            stderr_text = "\n".join(stderr_lines)
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, stderr=stderr_text,
            )
    except subprocess.CalledProcessError as exc:
        raise error_cls(f"ffmpeg failed: {exc.stderr}") from exc
    except FileNotFoundError:
        raise error_cls("ffmpeg not found — is ffmpeg installed?")
