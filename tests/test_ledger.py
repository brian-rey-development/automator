"""Tests for the SQLite audit history."""

from __future__ import annotations

from pathlib import Path

from automator.domain.models import ParsedInvoice, ProcessOutcome, ProcessResult, Voucher, VoucherKind
from automator.services.ledger import Ledger


def _invoice(supplier: str = "ACME S.A.", number: str = "00000123") -> ParsedInvoice:
    return ParsedInvoice(
        voucher=Voucher(VoucherKind.INVOICE, "A"),
        sales_point="0001",
        number=number,
        supplier=supplier,
        buyer_cuit="30111111118",
    )


def _result(outcome: ProcessOutcome, destination: Path | None, invoice: ParsedInvoice | None) -> ProcessResult:
    return ProcessResult(
        source=Path("descarga.pdf"), outcome=outcome, destination=destination, invoice=invoice, message="ok"
    )


def test_source_seen_tracks_processed_files(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "h.db")
    signature = "/descargas/f.pdf|1024|1700000000"
    assert not ledger.source_seen(signature)
    ledger.mark_source_seen(signature)
    assert ledger.source_seen(signature)
    ledger.mark_source_seen(signature)  # idempotent, must not fail
    assert ledger.source_seen(signature)
    ledger.close()


def test_record_and_recent(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "h.db")
    ledger.record(_result(ProcessOutcome.MOVED, tmp_path / "a.pdf", _invoice()))
    recent = ledger.recent()
    assert len(recent) == 1
    assert recent[0].outcome is ProcessOutcome.MOVED
    assert recent[0].supplier == "ACME S.A."
    ledger.close()


def test_identity_exists_only_for_archived(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "h.db")
    invoice = _invoice()
    assert invoice.identity is not None
    ledger.record(_result(ProcessOutcome.MOVED, tmp_path / "a.pdf", invoice))
    assert ledger.identity_exists(invoice.identity)
    # A review does not count as archived, it must not flag a duplicate.
    other = _invoice(number="00000999")
    assert other.identity is not None
    ledger.record(_result(ProcessOutcome.NEEDS_REVIEW, tmp_path / "r.pdf", other))
    assert not ledger.identity_exists(other.identity)
    ledger.close()


def test_last_undoable_and_mark_reverted(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "h.db")
    ledger.record(_result(ProcessOutcome.NEEDS_REVIEW, tmp_path / "r.pdf", None))
    ledger.record(_result(ProcessOutcome.MOVED, tmp_path / "a.pdf", _invoice()))
    record = ledger.last_undoable()
    assert record is not None
    assert record.outcome is ProcessOutcome.MOVED
    ledger.mark_reverted(record.id)
    assert ledger.last_undoable() is None  # There is nothing left to undo.
    ledger.close()


def test_clear_wipes_records_and_source_signatures(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "h.db")
    invoice = _invoice()
    assert invoice.identity is not None
    ledger.record(_result(ProcessOutcome.MOVED, tmp_path / "a.pdf", invoice))
    signature = "/descargas/f.pdf|1024|1700000000"
    ledger.mark_source_seen(signature)
    ledger.clear()
    assert ledger.recent() == []
    assert not ledger.identity_exists(invoice.identity)
    assert not ledger.source_seen(signature)
    assert ledger.last_undoable() is None
    ledger.close()


def test_ledger_persists_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "h.db"
    first = Ledger(path)
    first.record(_result(ProcessOutcome.MOVED, tmp_path / "a.pdf", _invoice()))
    first.close()
    second = Ledger(path)
    assert len(second.recent()) == 1  # The history survives the close.
    second.close()
