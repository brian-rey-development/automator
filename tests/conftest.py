"""Shared fixtures and sample invoice texts for the tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from automator.config import AppConfig, SocietyMapping

# Fictitious CUITs for the test societies (they match the sample texts).
CUIT_ONE = "30111111118"
CUIT_TWO = "30222222229"

FACTURA_A_TEXT = """ORIGINAL
FACTURA
A
Cod. 01
Razon Social: PROVEEDOR EJEMPLO SRL
CUIT: 30-99999999-5
Fecha de Emision: 01/08/2026
Punto de Venta: 0001    Comp. Nro: 00000123
Periodo Facturado
CUIT: 30-11111111-8
Razon Social: COMPRADORA UNO SA
"""

NOTA_CREDITO_B_TEXT = """ORIGINAL
NOTA DE CREDITO
B
Cod. 08
Razon Social: PROVEEDOR DOS SA
Punto de Venta: 0003    Comp. Nro: 00000045
CUIT: 30-22222222-9
"""

NOTA_DEBITO_B_TEXT = """ORIGINAL
NOTA DE DEBITO
B
Cod. 07
Razon Social: PROVEEDOR TRES SA
Punto de Venta: 0005    Comp. Nro: 00000009
CUIT: 30-22222222-9
"""

COMBINED_NUMBER_TEXT = """FACTURA
Cod. 01
Comp. Nro: 0002-00000777
Razon Social: DISTRIBUIDORA NORTE
"""

NO_RAZON_SOCIAL_TEXT = """MI PROVEEDOR SIN ETIQUETA
Cod. 01
Punto de Venta: 0009   Comp. Nro: 00000001
"""

# Full word "Comprobante Nro" (not the "Comp." abbreviation) with point of sale and
# number on separate lines. The IIBB below (trailing check digit) must NOT be taken
# as the number: the anchored label wins.
COMPROBANTE_WORD_TEXT = """FACTURA
A
Razon Social: PROVEEDOR LOMBARDI SA
Punto de Venta:
1238
Comprobante Nro:
00002972
CUIT: 30-69746598-3
Ingresos Brutos: 90230-69746598-3
"""

# Inline label "Nro/Numero/FACTURA A Nro" followed by point-of-sale-dash-number, the
# way many suppliers print it (no "Comp." token at all).
INLINE_NUMERO_TEXT = """PROVEEDOR VERCELLI
IVA Responsable Inscripto
FACTURA Nº 0007 - 00001522
Fecha: 05/08/2026
Razon Social: PROVEEDOR VERCELLI SA
CUIT: 20238054428
"""

# Number sitting alone in a table cell, no label, next to the issuer CUIT and the date
# (the "Cuenca del Salado" template family). The nearby CUIT must not be grabbed.
STANDALONE_TABLE_TEXT = """FACTURA
A
Razon Social: PROVEEDOR BASILICO
33-55438074-9
0004 - 00004899
06/08/2026
20-17427308-2
"""

# Two distinct standalone numbers and no label: the number cannot be decided, so it is
# left as the default and the invoice goes to review (never guessed).
AMBIGUOUS_STANDALONE_TEXT = """FACTURA
A
Razon Social: PROVEEDOR DUDOSO
0003-00010452
0007-00099999
"""

# Only an IIBB registration (point-of-sale-like prefix, dash, digits, trailing check
# digit) and a CUIT are present, no real voucher number: must stay the default.
ONLY_IIBB_TEXT = """FACTURA
A
Razon Social: PROVEEDOR SIN NUMERO
Ingresos Brutos: 90230-69746598-3
CUIT: 30-69746598-3
"""

# Point of sale and sequence live in different cells: the point of sale after its label
# and the sequence after the "Cod. NN" line.
SPLIT_NUMBER_TEXT = """FACTURA
A
Cod. 01 00082809
Punto de venta: 0022 Numero:
Razon Social: PROVEEDOR JUNIN SA
"""

# Layout extraction can place a second column on the same line as the label. The label
# capture must stop at the column gap and not swallow the neighbouring "Domicilio:" cell.
COLUMN_BLEED_SUPPLIER_TEXT = """FACTURA
A
Razon Social: PROVEEDOR COLUMNA SRL          Domicilio: CALLE FALSA 123
Punto de Venta: 0001 Comp. Nro: 00000123
"""

COLUMN_BLEED_ORDER_TEXT = """GRUPO X
ORD COMPRA  NRO: 2026-00004050
Unidad Ejecutora: CHACO                 Proveedor: JIMENEZ LORENZO HECTOR
Sociedad: ANDREOLI AGRO S.A.            Domicilio: CHACRA 15 0
Responsable Inscripto CUIT: 30711637253
"""

# Purchase order (Orden de Compra): different labels and numbering than a factura.
# Buyer CUIT matches CUIT_ONE (COMPRADORA UNO SA); supplier via "Proveedor:".
ORDEN_COMPRA_TEXT = """GRUPO EJEMPLO
RUTA 30 - KM 88.5
ORD COMPRA  NRO: 2026-00004046
Fecha: 15/08/2026
Unidad Ejecutora: AUTOMOTRIZ
Sociedad: COMPRADORA UNO SA
Responsable Inscripto CUIT: 30111111118
Proveedor: FERRETERIA EJEMPLO SRL
Cond. Iva: Responsable No Inscripto CUIT: 30-99999999-4
Total: 774,534.00
"""

# Same OC but the buyer CUIT is absent; only the near-matching society name is
# present, to exercise the fuzzy fallback.
ORDEN_COMPRA_NO_CUIT_TEXT = """GRUPO EJEMPLO
ORD COMPRA  NRO: 2026-00004050
Sociedad: COMPRADORA UNO S.A.
Proveedor: FERRETERIA EJEMPLO SRL
Total: 100,000.00
"""


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[..., AppConfig]:
    """Return an AppConfig factory pointing at temporary directories."""

    def factory(**overrides: object) -> AppConfig:
        base = tmp_path / "salida"
        config = AppConfig(
            input_folder=tmp_path / "entrada",
            base_output_folder=base,
            unknown_folder=base / "_SIN_CLASIFICAR",
            quarantine_folder=base / "_ERRORES",
            orders_folder=tmp_path / "ordenes",
            societies=[
                SocietyMapping(cuit=CUIT_ONE, name="COMPRADORA UNO SA"),
            ],
            dry_run=False,
            wait_for_stability=False,
            stability_timeout_s=0.1,
        )
        return config.model_copy(update=overrides)

    return factory


@pytest.fixture
def dummy_pdf(tmp_path: Path) -> Callable[[str], Path]:
    """Create a file with a .pdf extension in the temporary input folder."""

    def factory(name: str = "factura.pdf") -> Path:
        folder = tmp_path / "entrada"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_bytes(b"%PDF-1.4 contenido de prueba")
        return path

    return factory
