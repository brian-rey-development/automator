"""Tests for the SQLite audit history."""

from __future__ import annotations

from dataclasses import replace
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


def test_archived_destination_returns_latest_existing_path(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "h.db")
    invoice = _invoice()
    assert invoice.identity is not None
    first = tmp_path / "a.pdf"
    first.write_text("one")
    ledger.record(_result(ProcessOutcome.MOVED, first, invoice))
    assert ledger.archived_destination(invoice.identity) == str(first)
    ledger.close()


def test_archived_destination_ignores_review_and_null_destination(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "h.db")
    invoice = _invoice()
    assert invoice.identity is not None
    ledger.record(_result(ProcessOutcome.NEEDS_REVIEW, tmp_path / "r.pdf", invoice))
    ledger.record(_result(ProcessOutcome.MOVED, None, invoice))
    assert ledger.archived_destination(invoice.identity) is None
    ledger.close()


def test_archived_destination_only_for_filed_outcomes(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "h.db")
    invoice = _invoice()
    assert invoice.identity is not None
    dest = tmp_path / "a.pdf"
    dest.write_text("one")
    ledger.record(_result(ProcessOutcome.MOVED, dest, invoice))
    assert ledger.archived_destination(invoice.identity) == str(dest)
    other = _invoice(number="00000999")
    assert other.identity is not None
    ledger.record(_result(ProcessOutcome.NEEDS_REVIEW, tmp_path / "r.pdf", other))
    assert ledger.archived_destination(other.identity) is None
    ledger.close()


def test_last_undoable_and_mark_reverted(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "h.db")
    ledger.record(_result(ProcessOutcome.NEEDS_REVIEW, tmp_path / "r.pdf", None))
    ledger.record(_result(ProcessOutcome.MOVED, tmp_path / "a.pdf", _invoice()))
    record = ledger.last_undoable()
    assert record is not None
    assert record.outcome is ProcessOutcome.MOVED
    ledger.mark_reverted(record.id)
    leftover = ledger.last_undoable()
    assert leftover is not None
    assert leftover.outcome is ProcessOutcome.NEEDS_REVIEW
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
    assert ledger.archived_destination(invoice.identity) is None
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


def test_archived_destination_matches_renamed_supplier_via_issuer_cuit(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "h.db")
    original = replace(_invoice(supplier="ACME S.A."), issuer_cuit="30712345673")
    dest = tmp_path / "a.pdf"
    dest.write_text("one")
    ledger.record(_result(ProcessOutcome.MOVED, dest, original))
    renamed = _invoice(supplier="ACME NUEVO")
    assert renamed.identity is not None
    assert renamed.identity != original.identity
    assert ledger.archived_destination(renamed.identity, "30712345673") == str(dest)
    ledger.close()


def test_old_history_db_gains_issuer_cuit_column(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            source_name TEXT NOT NULL,
            identity TEXT,
            supplier TEXT,
            voucher TEXT,
            outcome TEXT NOT NULL,
            destination TEXT,
            message TEXT,
            reverted INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.commit()
    conn.close()
    ledger = Ledger(path)
    row = ledger._conn.execute("PRAGMA table_info(records)").fetchall()
    columns = {item[1] for item in row}
    assert "issuer_cuit" in columns
    version = ledger._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert version == 3
    assert "issuer_identity" in columns
    assert "source_signature" in columns
    ledger.close()
