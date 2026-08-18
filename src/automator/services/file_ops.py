"""Safe file operations: stability wait, uniqueness and moving."""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

_STABILITY_POLL_INTERVAL_S = 0.4
_LONG_PATH_PREFIX = "\\\\?\\"
_UNC_PREFIX = "\\\\"
_LONG_PATH_UNC_PREFIX = "\\\\?\\UNC\\"


def is_pdf(path: Path) -> bool:
    """True if the file has a .pdf extension (case-insensitive)."""
    return path.suffix.lower() == ".pdf"


def wait_until_stable(
    path: Path,
    timeout_s: float,
    poll_interval_s: float = _STABILITY_POLL_INTERVAL_S,
) -> bool:
    """Waits for the file size to stabilize (download finished).

    Returns True only if the file stopped growing within the time limit.
    Returns False if the time expired while it kept changing or it never appeared.
    """
    deadline = time.monotonic() + timeout_s
    last_size = -1
    while True:
        current_size = _safe_size(path)
        if current_size >= 0 and current_size == last_size:
            return True
        last_size = current_size
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval_s)


def path_exists(path: Path) -> bool:
    return os.path.exists(_os_path(path))


def unique_destination(path: Path) -> Path:
    """Returns a path that does not exist, appending ' (n)' on collision."""
    if not path_exists(path):
        return path
    parent, stem, suffix = path.parent, path.stem, path.suffix
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not path_exists(candidate):
            return candidate
        counter += 1


def move_file(source: Path, target_dir: Path, filename: str) -> Path:
    """Moves the file to the target folder avoiding overwrites.

    Uses shutil.move to support moves across different disks (C: to network).
    The worker is single and sequential, so there is no real race between the
    destination calculation and the move.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    desired = target_dir / filename
    if _already_at(source, desired):
        return source
    target = unique_destination(desired)
    shutil.move(_os_path(source), _os_path(target))
    return target


def copy_file(source: Path, target_dir: Path, filename: str) -> Path:
    """Copies the file to the target folder avoiding overwrites.

    Leaves the original intact. copy2 preserves the file dates, so the signature
    the engine uses to avoid reprocessing stays stable.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    desired = target_dir / filename
    if _already_at(source, desired):
        return source
    target = unique_destination(desired)
    shutil.copy2(_os_path(source), _os_path(target))
    return target


def _already_at(source: Path, desired: Path) -> bool:
    try:
        return path_exists(desired) and os.path.samefile(_os_path(source), _os_path(desired))
    except OSError:
        return False


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return -1


def _os_path(path: Path) -> str:
    """System-ready path, with the long-path prefix on Windows.

    Windows limits paths to 260 characters unless the extended prefix is used,
    which is needed for deeply nested supplier folders.
    """
    text = str(path)
    if not sys.platform.startswith("win") or not os.path.isabs(text) or text.startswith(_LONG_PATH_PREFIX):
        return text
    # UNC paths (\\server\share) require the \\?\UNC\server\share form,
    # not a simple prepended prefix (which would produce an invalid path).
    if text.startswith(_UNC_PREFIX):
        return _LONG_PATH_UNC_PREFIX + text[len(_UNC_PREFIX) :]
    return _LONG_PATH_PREFIX + text
