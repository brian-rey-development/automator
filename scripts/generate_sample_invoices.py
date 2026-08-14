"""Generate sample PDF invoices to test Automator end to end.

Creates vouchers with real text (that the parser can read) in the configured
input folder, covering the different paths: archived by society,
unclassified, for review and quarantine.

The data is fictitious. If there are configured societies, some invoices use
their CUITs so the routing is visible; if there are none, all fall into the
automatic folders (which still demonstrates the flow).

Usage:
    python scripts/generate_sample_invoices.py            # uses the configured folder
    python scripts/generate_sample_invoices.py /ruta/dir  # uses a specific folder
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from automator.config import AppConfig, load_config

# Fallback fictitious CUITs when there are no configured societies.
_FICTIONAL_BUYER_A = "30111111118"
_FICTIONAL_BUYER_B = "30222222229"
_FICTIONAL_UNKNOWN = "30999999995"


def _fmt_cuit(cuit: str) -> str:
    return f"{cuit[:2]}-{cuit[2:10]}-{cuit[10:]}" if len(cuit) == 11 else cuit


def _write_pdf(path: Path, lines: list[str]) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setFont("Helvetica", 12)
    y = 780
    for line in lines:
        pdf.drawString(60, y, line)
        y -= 22
    pdf.save()


def _invoice_lines(
    kind: str, letter: str, code: str, pv: str, number: str, supplier: str, buyer_cuit: str
) -> list[str]:
    return [
        "ORIGINAL",
        f"{kind}",
        f"{letter}",
        f"Cod. {code}",
        f"Razon Social: {supplier}",
        "CUIT: 30-99999999-5",
        "Fecha de Emision: 14/08/2026",
        f"Punto de Venta: {pv}    Comp. Nro: {number}",
        "CUIT del Cliente:",
        f"CUIT: {_fmt_cuit(buyer_cuit)}",
    ]


def generate(target: Path, config: AppConfig) -> list[Path]:
    """Generate the sample PDFs and return the created paths."""
    target.mkdir(parents=True, exist_ok=True)
    cuits = [society.cuit for society in config.societies]
    first = cuits[0] if cuits else _FICTIONAL_BUYER_A
    second = cuits[1] if len(cuits) > 1 else _FICTIONAL_BUYER_B

    samples = {
        "factura_proveedor_uno.pdf": _invoice_lines(
            "FACTURA", "A", "01", "0001", "00000123", "PROVEEDOR EJEMPLO UNO SRL", first
        ),
        "nota_credito_proveedor_dos.pdf": _invoice_lines(
            "NOTA DE CREDITO", "B", "08", "0003", "00000045", "PROVEEDOR EJEMPLO DOS SA", second
        ),
        "factura_sin_clasificar.pdf": _invoice_lines(
            "FACTURA", "A", "01", "0007", "00000777", "PROVEEDOR EJEMPLO TRES SA", _FICTIONAL_UNKNOWN
        ),
        # Without a voucher number: it should go to the "for review" folder.
        "factura_para_revisar.pdf": [
            "FACTURA",
            "Cod. 01",
            "Razon Social: PROVEEDOR SIN NUMERO SA",
            f"CUIT: {_fmt_cuit(first)}",
        ],
    }
    created = [_render(target / name, lines) for name, lines in samples.items()]
    # PDF without readable text: it should go to quarantine.
    created.append(_render(target / "escaneo_ilegible.pdf", []))
    return created


def _render(path: Path, lines: list[str]) -> Path:
    _write_pdf(path, lines)
    return path


def main() -> None:
    config = load_config()
    target = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else config.input_folder
    created = generate(target, config)
    print(f"Se generaron {len(created)} facturas de ejemplo en:\n  {target}\n")
    for path in created:
        print(f"  - {path.name}")
    print('\nAbri Automator, revisa la carpeta de entrada en Configuracion y apreta "Iniciar".')


if __name__ == "__main__":
    main()
