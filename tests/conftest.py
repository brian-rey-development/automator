"""Shared fixtures. Sample invoice texts live in fixtures/invoices.py."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from automator.config import AppConfig, SocietyMapping
from fixtures.invoices import CUIT_ONE


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[..., AppConfig]:
    """Return an AppConfig factory pointing at temporary directories.

    wait_for_stability defaults to False so dummy files do not pay the poll interval.
    Tests that need the production default pass wait_for_stability=True.
    """

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
    def factory(name: str = "factura.pdf") -> Path:
        folder = tmp_path / "entrada"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_bytes(b"%PDF-1.4 contenido de prueba")
        return path

    return factory
