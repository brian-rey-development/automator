"""Tests for the processing engine (without real threads or watchdog)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from automator.config import AppConfig
from automator.domain.models import ProcessOutcome
from automator.domain.suppliers import Supplier, SupplierRegistry
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


def test_process_now_canonicalizes_supplier_via_registry(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path]
) -> None:
    config = make_config()
    source = dummy_pdf("factura.pdf")
    registry = SupplierRegistry([Supplier(cuit="30999999995", razon_social="Proveedor Canonico SRL")])
    engine = ProcessingEngine(
        lambda: config, lambda _e: None, extractor=lambda _p: FACTURA_A_TEXT, registry_provider=lambda: registry
    )

    result = engine.process_now(source)

    assert result.invoice is not None
    assert result.invoice.supplier == "Proveedor Canonico SRL"


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


def test_duplicate_only_when_the_original_still_exists(
    make_config: Callable[..., AppConfig], dummy_pdf: Callable[[str], Path], tmp_path: Path
) -> None:
    ledger = Ledger(tmp_path / "history.db")
    config = make_config()
    engine = ProcessingEngine(lambda: config, lambda _e: None, extractor=lambda _path: FACTURA_A_TEXT, ledger=ledger)

    first = engine.process_now(dummy_pdf("f1.pdf"))
    assert first.outcome is ProcessOutcome.MOVED
    assert first.destination is not None

    # Same invoice while the archived original is in place: a real duplicate.
    assert engine.process_now(dummy_pdf("f2.pdf")).outcome is ProcessOutcome.DUPLICATE

    # The archived original disappears (the user emptied the folder): the next copy must
    # be filed, never diverted as a phantom duplicate of something that no longer exists.
    first.destination.unlink()
    assert engine.process_now(dummy_pdf("f3.pdf")).outcome is ProcessOutcome.MOVED
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
