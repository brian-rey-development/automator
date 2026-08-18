"""Spanish copy used by the interface."""

from __future__ import annotations

from automator.domain.models import ProcessOutcome

CLEAR_HISTORY_CONFIRM = (
    "Se borra el historial de procesamiento: duplicados, revisiones y archivos ya vistos.\n\n"
    "Los PDF no se mueven ni se eliminan.\n\n"
    "Despues vas a poder reprocesar y revisar de nuevo. Continuar?"
)

OUTCOME_LABELS: dict[ProcessOutcome, str] = {
    ProcessOutcome.MOVED: "Archivado",
    ProcessOutcome.DRY_RUN: "Simulado",
    ProcessOutcome.UNCLASSIFIED: "Sin clasificar",
    ProcessOutcome.DUPLICATE: "Duplicado",
    ProcessOutcome.NEEDS_REVIEW: "Revisar",
    ProcessOutcome.QUARANTINED: "Cuarentena",
    ProcessOutcome.ERROR: "Error",
    ProcessOutcome.SKIPPED_MISSING: "Omitido",
}

OUTCOME_ROW_TAG: dict[ProcessOutcome, str] = {
    ProcessOutcome.MOVED: "ok",
    ProcessOutcome.DRY_RUN: "ok",
    ProcessOutcome.UNCLASSIFIED: "warn",
    ProcessOutcome.DUPLICATE: "warn",
    ProcessOutcome.NEEDS_REVIEW: "warn",
    ProcessOutcome.QUARANTINED: "warn",
    ProcessOutcome.ERROR: "error",
    ProcessOutcome.SKIPPED_MISSING: "warn",
}
