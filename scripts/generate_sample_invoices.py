"""Genera facturas PDF de ejemplo para probar Automator de punta a punta.

Crea comprobantes con texto real (que el parser puede leer) en la carpeta de
entrada configurada, cubriendo los distintos caminos: archivado normal, sin
clasificar, para revisar y cuarentena.

Uso:
    python scripts/generate_sample_invoices.py            # usa la carpeta configurada
    python scripts/generate_sample_invoices.py /ruta/dir  # usa una carpeta puntual
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from automator.config import load_config

# CUIT de las sociedades por defecto (ANDREOLI y CUENCA DEL SALADO).
_CUIT_ANDREOLI = "33-55438074-9"
_CUIT_CUENCA = "33-62708849-9"
_CUIT_DESCONOCIDO = "30-99999999-7"


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
        "CUIT: 30-11111111-2",
        "Fecha de Emision: 14/08/2026",
        f"Punto de Venta: {pv}    Comp. Nro: {number}",
        "CUIT del Cliente:",
        f"CUIT: {buyer_cuit}",
    ]


def generate(target: Path) -> list[Path]:
    """Genera los PDF de ejemplo y devuelve las rutas creadas."""
    target.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    samples = {
        "factura_andreoli.pdf": _invoice_lines(
            "FACTURA", "A", "01", "0001", "00000123", "ACME INSUMOS S.R.L.", _CUIT_ANDREOLI
        ),
        "nota_credito_cuenca.pdf": _invoice_lines(
            "NOTA DE CREDITO", "B", "08", "0003", "00000045", "PROVEEDOR SUR S.A.", _CUIT_CUENCA
        ),
        "factura_sin_clasificar.pdf": _invoice_lines(
            "FACTURA", "A", "01", "0007", "00000777", "DISTRIBUIDORA NORTE S.A.", _CUIT_DESCONOCIDO
        ),
        # Sin numero de comprobante: deberia ir a la carpeta "para revisar".
        "factura_para_revisar.pdf": [
            "FACTURA",
            "Cod. 01",
            "Razon Social: PROVEEDOR SIN NUMERO S.A.",
            f"CUIT: {_CUIT_ANDREOLI}",
        ],
    }
    for name, lines in samples.items():
        path = target / name
        _write_pdf(path, lines)
        created.append(path)

    # PDF sin texto legible: deberia ir a cuarentena.
    empty = target / "escaneo_ilegible.pdf"
    _write_pdf(empty, [])
    created.append(empty)
    return created


def main() -> None:
    target = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else load_config().input_folder
    created = generate(target)
    print(f"Se generaron {len(created)} facturas de ejemplo en:\n  {target}\n")
    for path in created:
        print(f"  - {path.name}")
    print('\nAbri Automator, revisa la carpeta de entrada en Configuracion y apreta "Iniciar".')


if __name__ == "__main__":
    main()
