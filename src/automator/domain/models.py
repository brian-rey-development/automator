"""Modelos inmutables del dominio de facturas AFIP."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# Centinela cuando no se pudo detectar la razon social del proveedor.
UNKNOWN_SUPPLIER = "PROVEEDOR_DESCONOCIDO"


class VoucherKind(StrEnum):
    """Tipo de comprobante. El valor es la etiqueta usada en el nombre del archivo."""

    INVOICE = "FC"  # Factura
    CREDIT_NOTE = "NC"  # Nota de credito
    DEBIT_NOTE = "ND"  # Nota de debito


@dataclass(frozen=True, slots=True)
class Voucher:
    """Comprobante identificado por tipo y letra (por ejemplo FC A)."""

    kind: VoucherKind
    letter: str

    @property
    def label(self) -> str:
        return f"{self.kind.value} {self.letter}"


@dataclass(frozen=True, slots=True)
class ParsedInvoice:
    """Datos extraidos de una factura, listos para archivar."""

    voucher: Voucher
    sales_point: str  # Punto de venta (4 digitos)
    number: str  # Numero de comprobante (8 digitos)
    supplier: str  # Razon social del proveedor
    buyer_cuit: str | None  # CUIT de la sociedad compradora detectada
    ambiguous_buyer: bool = False  # Aparecen varias sociedades propias: no se puede decidir

    @property
    def full_number(self) -> str:
        return f"{self.sales_point}-{self.number}"

    @property
    def has_number(self) -> bool:
        """True si se pudo extraer un numero de comprobante real (no el de relleno)."""
        return self.number != "00000000" or self.sales_point != "0000"

    @property
    def has_supplier(self) -> bool:
        """True si se detecto la razon social del proveedor (no el centinela)."""
        return self.supplier != UNKNOWN_SUPPLIER


class ProcessOutcome(StrEnum):
    """Resultado posible del procesamiento de un archivo."""

    MOVED = "moved"
    DRY_RUN = "dry_run"
    UNCLASSIFIED = "unclassified"  # Archivado, pero sin poder identificar la sociedad compradora.
    NEEDS_REVIEW = "needs_review"
    QUARANTINED = "quarantined"
    SKIPPED_MISSING = "skipped_missing"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Resultado del procesamiento de un unico PDF."""

    source: Path
    outcome: ProcessOutcome
    destination: Path | None
    invoice: ParsedInvoice | None
    message: str

    @property
    def is_success(self) -> bool:
        return self.outcome in (ProcessOutcome.MOVED, ProcessOutcome.DRY_RUN)
