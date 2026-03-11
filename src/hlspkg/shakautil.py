"""Thin subprocess wrapper for Shaka Packager."""

from __future__ import annotations

import logging
import shutil
import subprocess

from hlspkg.exceptions import PackageError

log = logging.getLogger(__name__)

_BINARY_NAMES = ("packager", "shaka-packager")


def _find_packager() -> str:
    """Locate the Shaka Packager binary on PATH."""
    for name in _BINARY_NAMES:
        path = shutil.which(name)
        if path:
            return path
    raise PackageError(
        "Shaka Packager not found — install 'packager' or 'shaka-packager'"
    )


def run_shaka(
    stream_descriptors: list[str],
    flags: list[str] | None = None,
) -> None:
    """Run Shaka Packager with the given stream descriptors and flags."""
    binary = _find_packager()
    cmd = [binary, *stream_descriptors, *(flags or [])]
    log.debug("shaka command: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise PackageError(f"Shaka Packager failed: {exc.stderr}") from exc
    except FileNotFoundError:
        raise PackageError("Shaka Packager binary not found at runtime")
