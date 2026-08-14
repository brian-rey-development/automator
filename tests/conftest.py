"""Fixtures compartidos y textos de factura de ejemplo para los tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from automator.config import AppConfig, SocietyMapping

# CUIT de sociedades de prueba (coinciden con los textos de ejemplo).
CUIT_ANDREOLI = "33554380749"
CUIT_CUENCA = "33627088499"

FACTURA_A_TEXT = """ORIGINAL
FACTURA
A
Cod. 01
Razon Social: ACME INSUMOS S.R.L.
CUIT: 30-11111111-2
Fecha de Emision: 01/08/2026
Punto de Venta: 0001    Comp. Nro: 00000123
Periodo Facturado
CUIT: 33-55438074-9
Razon Social: ANDREOLI S.A.
"""

NOTA_CREDITO_B_TEXT = """ORIGINAL
NOTA DE CREDITO
B
Cod. 08
Razon Social: PROVEEDOR SUR S.A.
Punto de Venta: 0003    Comp. Nro: 00000045
CUIT: 33-62708849-9
"""

NOTA_DEBITO_B_TEXT = """ORIGINAL
NOTA DE DEBITO
B
Cod. 07
Razon Social: LOGISTICA DEL PLATA
Punto de Venta: 0005    Comp. Nro: 00000009
CUIT: 33-62708849-9
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


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[..., AppConfig]:
    """Devuelve una fabrica de AppConfig apuntando a directorios temporales."""

    def factory(**overrides: object) -> AppConfig:
        base = tmp_path / "salida"
        config = AppConfig(
            input_folder=tmp_path / "entrada",
            base_output_folder=base,
            unknown_folder=base / "_SIN_CLASIFICAR",
            quarantine_folder=base / "_ERRORES",
            societies=[
                SocietyMapping(cuit=CUIT_ANDREOLI, name="ANDREOLI S.A.", folder=base / "ANDREOLI" / "PROV"),
            ],
            dry_run=False,
            wait_for_stability=False,
            stability_timeout_s=0.1,
        )
        return config.model_copy(update=overrides)

    return factory


@pytest.fixture
def dummy_pdf(tmp_path: Path) -> Callable[[str], Path]:
    """Crea un archivo con extension .pdf en la carpeta de entrada temporal."""

    def factory(name: str = "factura.pdf") -> Path:
        folder = tmp_path / "entrada"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_bytes(b"%PDF-1.4 contenido de prueba")
        return path

    return factory
