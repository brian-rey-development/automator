"""Pure presentation helpers for activity and history rows."""

from __future__ import annotations

from pathlib import Path

from automator.domain.models import ProcessOutcome, ProcessResult
from automator.services.ledger import LedgerRecord
from automator.ui.main_window import _count_key, _count_pdfs, _history_row, _status_label


def test_dry_run_review_counts_as_review_not_archived() -> None:
    result = ProcessResult(
        source=Path("x.pdf"),
        outcome=ProcessOutcome.DRY_RUN,
        destination=Path("/out/_PARA_REVISAR/x.pdf"),
        invoice=None,
        message="sim",
        intended=ProcessOutcome.NEEDS_REVIEW,
    )
    assert _count_key(result) == "review"
    assert _status_label(result) == "Simulado · Revisar"


def test_history_row_formats_record() -> None:
    record = LedgerRecord(
        id=1,
        ts="2026-08-14T10:00:00",
        source_name="factura.pdf",
        identity=None,
        supplier="PROVEEDOR X",
        voucher="FC A",
        outcome=ProcessOutcome.MOVED,
        destination="/salida/x/factura.pdf",
        message="ok",
        reverted=False,
    )
    row = _history_row(record)
    assert row[1] == "factura.pdf"
    assert row[3] == "Archivado"


def test_count_pdfs_is_case_insensitive_and_recursive(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.pdf").write_bytes(b"%PDF")
    (tmp_path / "sub" / "b.PDF").write_bytes(b"%PDF")
    (tmp_path / "sub" / "c.txt").write_bytes(b"x")
    assert _count_pdfs(tmp_path) == 2
    assert _count_pdfs(tmp_path / "no-existe") == 0
