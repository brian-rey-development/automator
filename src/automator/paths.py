"""Application data paths resolved per platform and runtime (source vs frozen)."""

from __future__ import annotations

import sys
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir, user_log_dir

APP_NAME = "Automator"
APP_AUTHOR = "Brian Rey"


def config_path() -> Path:
    return Path(user_config_dir(APP_NAME, APP_AUTHOR)) / "config.json"


def data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def ledger_path() -> Path:
    return data_dir() / "history.db"


def log_dir() -> Path:
    return Path(user_log_dir(APP_NAME, APP_AUTHOR))


def assets_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if isinstance(meipass, str):
        return Path(meipass) / "assets"
    return Path(__file__).resolve().parents[2] / "assets"
