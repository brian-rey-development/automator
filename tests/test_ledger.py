"""Tests del historial de auditoria en SQLite."""

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
        buyer_cuit="33554380749",
    )


def _result(outcome: ProcessOutcome, destination: Path | None, invoice: ParsedInvoice | None) -> ProcessResult:
    return ProcessResult(
        source=Path("descarga.pdf"), outcome=outcome, destination=destination, invoice=invoice, message="ok"
    )


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
    # Una revision no cuenta como archivada, no debe marcar duplicado.
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
    assert ledger.last_undoable() is None  # Ya no hay nada para deshacer.
    ledger.close()


def test_ledger_persists_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "h.db"
    first = Ledger(path)
    first.record(_result(ProcessOutcome.MOVED, tmp_path / "a.pdf", _invoice()))
    first.close()
    second = Ledger(path)
    assert len(second.recent()) == 1  # El historial sobrevive al cierre.
    second.close()
