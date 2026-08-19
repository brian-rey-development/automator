"""Copy or move a file into a destination folder. Never overwrite."""

from __future__ import annotations

from pathlib import Path

from automator.services import file_ops


def place_file(source: Path, target_dir: Path, filename: str, *, copy_files: bool) -> Path:
    if copy_files:
        return file_ops.copy_file(source, target_dir, filename)
    return file_ops.move_file(source, target_dir, filename)
