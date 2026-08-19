"""Default configuration and special folder names."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from platformdirs import user_downloads_dir

if TYPE_CHECKING:
    from automator.config.model import AppConfig

UNKNOWN_FOLDER_NAME = "_SIN_CLASIFICAR"
QUARANTINE_FOLDER_NAME = "_ERRORES"
REVIEW_FOLDER_NAME = "_PARA_REVISAR"
DUPLICATES_FOLDER_NAME = "_DUPLICADOS"


def default_config() -> AppConfig:
    """Neutral initial configuration, with no company preloaded.

    No real data is hardcoded: the user defines their companies and CUITs
    from the interface (or the first-time wizard). It starts with no companies.
    """
    from automator.config.model import AppConfig

    home = Path.home()
    base = home / "Automator" / "Facturas ordenadas"
    return AppConfig(
        input_folder=Path(user_downloads_dir()),
        base_output_folder=base,
        unknown_folder=base / UNKNOWN_FOLDER_NAME,
        quarantine_folder=base / QUARANTINE_FOLDER_NAME,
        orders_folder=home / "Automator" / "Ordenes de compra",
    )
