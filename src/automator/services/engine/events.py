"""Events the engine emits toward the interface."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from automator.config import AppConfig
from automator.domain.models import ProcessResult

logger = logging.getLogger(__name__)


class EngineEventType(StrEnum):
    STARTED = "started"
    STOPPED = "stopped"
    DETECTED = "detected"
    RESULT = "result"
    ERROR = "error"


@dataclass(frozen=True)
class EngineEvent:
    """Event emitted by the engine toward the interface."""

    type: EngineEventType
    message: str = ""
    path: Path | None = None
    result: ProcessResult | None = None
    generation_id: int = 0


EventSink = Callable[[EngineEvent], None]
ConfigProvider = Callable[[], AppConfig]


def emit(sink: EventSink, event: EngineEvent) -> None:
    try:
        sink(event)
    except Exception:
        logger.exception("Fallo el sink de eventos")
