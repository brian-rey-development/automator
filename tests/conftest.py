"""Fixtures compartidos y textos de factura de ejemplo para los tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from automator.config import AppConfig, SocietyMapping

# CUIT ficticios de sociedades de prueba (coinciden con los textos de ejemplo).
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
                SocietyMapping(cuit=CUIT_ONE, name="COMPRADORA UNO SA", folder=base / "UNO" / "PROV"),
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
