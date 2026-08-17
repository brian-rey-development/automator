"""Tests for the processing engine (without real threads or watchdog)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from automator.config import AppConfig
from automator.domain.models import ProcessOutcome
from automator.services import engine as engine_module
from automator.services.engine import EngineEvent, EngineEventType, ProcessingEngine
from automator.services.ledger import Ledger
from tests.conftest import FACTURA_A_TEXT


def _engine(config: AppConfig, sink: Callable[[EngineEvent], None], text: str) -> ProcessingEngine:
    return ProcessingEngine(lambda: config, sink, extractor=lambda _path: text)


def test_process_now_returns_result_and_emits_event(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    events: list[EngineEvent] = []
    config = make_config()
    source = dummy_pdf("factura.pdf")

    result = _engine(config, events.append, FACTURA_A_TEXT).process_now(source)

    assert result.outcome is ProcessOutcome.MOVED
    assert [event.type for event in events] == [EngineEventType.RESULT]
    assert events[0].result is result


def test_process_existing_enqueues_all_pdfs(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    events: list[EngineEvent] = []
    config = make_config()
    dummy_pdf("a.pdf")
    dummy_pdf("b.pdf")

    count = _engine(config, events.append, FACTURA_A_TEXT).process_existing()

    assert count == 2
    detected = [event for event in events if event.type is EngineEventType.DETECTED]
    assert len(detected) == 2


def test_start_and_stop_lifecycle_emits_events(make_config: Callable[..., AppConfig]) -> None:
    events: list[EngineEvent] = []
    config = make_config()
    engine = _engine(config, events.append, FACTURA_A_TEXT)

    engine.start()
    assert engine.is_running
    engine.stop()
    assert not engine.is_running

    emitted = [event.type for event in events]
    assert EngineEventType.STARTED in emitted
    assert EngineEventType.STOPPED in emitted


def test_failed_start_emits_error_and_leaves_no_running_engine(
    make_config: Callable[..., AppConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_watcher(*_args: object, **_kwargs: object) -> object:
        raise OSError("no se pudo vigilar la carpeta")

    monkeypatch.setattr(engine_module, "FolderWatcher", broken_watcher)
    events: list[EngineEvent] = []
    engine = _engine(make_config(), events.append, FACTURA_A_TEXT)

    engine.start()

    assert not engine.is_running  # No orphaned worker is left behind.
    assert any(event.type is EngineEventType.ERROR for event in events)
    assert all(event.type is not EngineEventType.STARTED for event in events)


def test_dry_run_does_not_reprocess_seen_source(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path], tmp_path: Path
) -> None:
    ledger = Ledger(tmp_path / "history.db")
    config = make_config(dry_run=True)
    source = dummy_pdf("factura.pdf")
    events: list[EngineEvent] = []
    engine = ProcessingEngine(lambda: config, events.append, extractor=lambda _path: FACTURA_A_TEXT, ledger=ledger)

    result = engine.process_now(source)
    assert result.outcome is ProcessOutcome.DRY_RUN
    assert source.exists()

    events.clear()
    engine.process_existing()
    assert not any(event.type is EngineEventType.DETECTED for event in events)
    ledger.close()


def test_copy_mode_does_not_reprocess_seen_source(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path], tmp_path: Path
) -> None:
    ledger = Ledger(tmp_path / "history.db")
    config = make_config(copy_files=True)
    source = dummy_pdf("factura.pdf")
    events: list[EngineEvent] = []
    engine = ProcessingEngine(lambda: config, events.append, extractor=lambda _path: FACTURA_A_TEXT, ledger=ledger)

    result = engine.process_now(source)
    assert result.outcome is ProcessOutcome.MOVED
    assert source.exists()  # copied: the original stays in the input

    events.clear()
    engine.process_existing()  # the rescan sees it again, but it must not be reprocessed
    assert not any(event.type is EngineEventType.DETECTED for event in events)
    ledger.close()


def test_sink_errors_do_not_crash_engine(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    def broken_sink(_event: EngineEvent) -> None:
        raise RuntimeError("sink roto")

    config = make_config()
    source = dummy_pdf("factura.pdf")
    # It must not propagate the sink exception.
    result = _engine(config, broken_sink, FACTURA_A_TEXT).process_now(source)
    assert result.outcome is ProcessOutcome.MOVED
