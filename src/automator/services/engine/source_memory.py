"""In-memory and ledger tracking of already processed source files."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from automator.config import ConfigProvider
from automator.domain.models import ProcessOutcome
from automator.services.file_ops import file_signature
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
_REMEMBERED = _COPY_PLACED | frozenset({ProcessOutcome.DRY_RUN})


def source_signature(path: Path) -> str | None:
    return file_signature(path)


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
        if signature is None or self._ledger is None or not self._config_provider().copy_files:
            return False
        return self._ledger.source_seen(signature)

    def remember(self, path: Path, outcome: ProcessOutcome) -> None:
        config = self._config_provider()
        if outcome in _REMEMBERED and (config.dry_run or config.copy_files):
            signature = source_signature(path)
            if signature is not None:
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
