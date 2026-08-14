"""Clasificador y archivador automatico de facturas AFIP."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("automator")
except PackageNotFoundError:  # pragma: no cover - solo si el paquete no esta instalado
    __version__ = "1.0.0"
