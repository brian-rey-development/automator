"""Background worker that drains the processing queue."""

from __future__ import annotations

import logging
import queue
from pathlib import Path

from automator.domain.models import ParsedInvoice, ProcessOutcome, ProcessResult
from automator.services.engine.events import EngineEvent, EngineEventType, EventSink
from automator.services.engine.inbox import Inbox
from automator.services.engine.source_memory import SourceMemory
from automator.services.file_ops import path_exists
from automator.services.ledger import Ledger
from automator.services.processing import InvoiceProcessor

logger = logging.getLogger(__name__)

SENTINEL = object()
WORKER_JOIN_TIMEOUT_S = 10.0
RESCAN_INTERVAL_S = 60.0


def record_result(ledger: Ledger | None, result: ProcessResult) -> None:
    if ledger is None or result.outcome is ProcessOutcome.SKIPPED_MISSING:
        return
    try:
        ledger.record(result)
    except Exception:
        logger.exception("No se pudo registrar en el historial")


def is_archived_duplicate(ledger: Ledger | None, invoice: ParsedInvoice) -> bool:
    if ledger is None or invoice.identity is None:
        return False
    destination = ledger.archived_destination(invoice.identity, invoice.issuer_cuit)
    # A real duplicate only if the previously archived file is still there. If the
    # original was removed, this copy must be filed, never lost as a phantom duplicate.
    return destination is not None and path_exists(Path(destination))


class Worker:
    def __init__(
        self,
        processor: InvoiceProcessor,
        inbox: Inbox,
        memory: SourceMemory,
        emit: EventSink,
        ledger: Ledger | None,
    ) -> None:
        self._processor = processor
        self._inbox = inbox
        self._memory = memory
        self._emit = emit
        self._ledger = ledger

    def run(self, work_queue: queue.Queue[object]) -> None:
        while True:
            item = work_queue.get()
            if item is SENTINEL:
                return
            if isinstance(item, Path):
                self.safe_process(item)

    def safe_process(self, path: Path) -> None:
        try:
            result = self._processor.process(path)
            record_result(self._ledger, result)
            self._memory.remember(path, result.outcome)
            self._emit(EngineEvent(EngineEventType.RESULT, result.message, path, result))
        except Exception as exc:
            logger.exception("Error inesperado procesando %s", path)
            self._emit(EngineEvent(EngineEventType.ERROR, str(exc), path))
        finally:
            self._inbox.release(path)
