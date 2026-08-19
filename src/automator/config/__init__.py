"""Application configuration: validated model, persistence and a safe store."""

from automator.config.defaults import (
    DUPLICATES_FOLDER_NAME,
    ORDERS_UNKNOWN_FOLDER_NAME,
    QUARANTINE_FOLDER_NAME,
    REVIEW_FOLDER_NAME,
    UNKNOWN_FOLDER_NAME,
    default_config,
)
from automator.config.model import AppConfig, ConfigProvider, SocietyMapping
from automator.config.store import ConfigStore, load_config, load_store, save_config
from automator.paths import config_path, ledger_path, log_dir

__all__ = [
    "DUPLICATES_FOLDER_NAME",
    "ORDERS_UNKNOWN_FOLDER_NAME",
    "QUARANTINE_FOLDER_NAME",
    "REVIEW_FOLDER_NAME",
    "UNKNOWN_FOLDER_NAME",
    "AppConfig",
    "ConfigProvider",
    "ConfigStore",
    "SocietyMapping",
    "config_path",
    "default_config",
    "ledger_path",
    "load_config",
    "load_store",
    "log_dir",
    "save_config",
]
