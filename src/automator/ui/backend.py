"""Open and close the SQLite stores used by the main window."""

from __future__ import annotations

import logging
import sqlite3

from automator.paths import ledger_path
from automator.services.ledger import Ledger
from automator.services.supplier_store import SupplierStore

logger = logging.getLogger(__name__)


def open_ledger() -> Ledger | None:
    try:
        return Ledger(ledger_path())
    except (OSError, sqlite3.Error):
        logger.exception("No se pudo abrir el historial; se continua sin el")
        return None


def open_supplier_store() -> SupplierStore | None:
    try:
        return SupplierStore(ledger_path())
    except (OSError, sqlite3.Error):
        logger.exception("No se pudo abrir el registro de proveedores; se continua sin el")
        return None


def close_stores(ledger: Ledger | None, suppliers: SupplierStore | None) -> None:
    if ledger is not None:
        ledger.close()
    if suppliers is not None:
        suppliers.close()
