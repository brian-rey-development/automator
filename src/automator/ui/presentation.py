"""Pure presentation helpers for activity, history and CUIT display."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from automator.domain.cuit import CUIT_LENGTH
from automator.domain.models import ProcessOutcome, ProcessResult
from automator.services.ledger import LedgerRecord
from automator.ui.strings import OUTCOME_LABELS, OUTCOME_ROW_TAG

_ARCHIVED = (ProcessOutcome.MOVED, ProcessOutcome.DRY_RUN)
_REVIEW = (
    ProcessOutcome.UNCLASSIFIED,
    ProcessOutcome.DUPLICATE,
    ProcessOutcome.NEEDS_REVIEW,
    ProcessOutcome.QUARANTINED,
)


def count_key(result: ProcessResult) -> str:
    outcome = result.counted_outcome
    if outcome in _ARCHIVED:
        return "archived"
    if outcome in _REVIEW:
        return "review"
    return "error"


def status_label(result: ProcessResult) -> str:
    if result.outcome is ProcessOutcome.DRY_RUN and result.intended is not None:
        return f"Simulado · {OUTCOME_LABELS[result.intended]}"
    return OUTCOME_LABELS[result.outcome]


def count_pdfs(folder: Path) -> int:
    try:
        return sum(1 for path in folder.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")
    except OSError:
        return 0


def history_row(record: LedgerRecord) -> tuple[str, str, str, str, str]:
    when = record.ts.replace("T", "  ")
    estado = OUTCOME_LABELS.get(record.outcome, record.outcome.value)
    if record.reverted:
        estado = f"{estado} (deshecho)"
    destino = record.destination or record.message
    return (when, record.source_name, record.voucher or "", estado, destino)


def history_tag(record: LedgerRecord) -> str:
    return "warn" if record.reverted else OUTCOME_ROW_TAG.get(record.outcome, "warn")


def format_cuit(cuit: str) -> str:
    if len(cuit) != CUIT_LENGTH:
        return cuit
    return f"{cuit[:2]}-{cuit[2:10]}-{cuit[10:]}"


def format_validation_error(exc: ValidationError) -> str:
    return "\n".join(str(error["msg"]).removeprefix("Value error, ") for error in exc.errors())
