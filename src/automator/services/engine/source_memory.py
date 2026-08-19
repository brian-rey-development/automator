"""In-memory and ledger tracking of already processed source files."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from automator.domain.models import ProcessOutcome
from automator.services.engine.events import ConfigProvider
from automator.services.ledger import Ledger

logger = logging.getLogger(__name__)

# Outcomes that left a placed copy: in copy mode they are marked as seen so the
# original that stays in the input folder is not reprocessed.
_COPY_PLACED = frozenset(
    {
        ProcessOutcome.MOVED,
        ProcessOutcome.UNCLASSIFIED,
        ProcessOutcome.DUPLICATE,
        ProcessOutcome.NEEDS_REVIEW,
        ProcessOutcome.QUARANTINED,
    }
)


def source_signature(path: Path) -> str | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return f"{os.path.abspath(path)}|{stat.st_size}|{int(stat.st_mtime)}"


class SourceMemory:
    def __init__(
        self,
        lock: threading.Lock,
        config_provider: ConfigProvider,
        ledger: Ledger | None,
    ) -> None:
        self._lock = lock
        self._config_provider = config_provider
        self._ledger = ledger
        self._seen_signatures: set[str] = set()

    def clear(self) -> None:
        self._seen_signatures = set()

    def already_processed(self, path: Path) -> bool:
        signature = source_signature(path)
        if signature is not None:
            with self._lock:
                if signature in self._seen_signatures:
                    return True
        if self._ledger is None or not self._config_provider().copy_files:
            return False
        return signature is not None and self._ledger.source_seen(signature)

    def remember(self, path: Path, outcome: ProcessOutcome) -> None:
        if outcome is ProcessOutcome.SKIPPED_MISSING:
            return
        config = self._config_provider()
        signature = source_signature(path)
        if signature is not None and (config.dry_run or config.copy_files):
            with self._lock:
                self._seen_signatures.add(signature)
        self._mark_copied(path, outcome, config.copy_files)

    def _mark_copied(self, path: Path, outcome: ProcessOutcome, copy_files: bool) -> None:
        if self._ledger is None or not copy_files or outcome not in _COPY_PLACED:
            return
        signature = source_signature(path)
        if signature is None:
            return
        try:
            self._ledger.mark_source_seen(signature)
        except Exception:
            logger.exception("No se pudo marcar %s como procesado", path)
