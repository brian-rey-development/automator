"""Automatic classifier and archiver of AFIP invoices."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("automator")
except PackageNotFoundError:  # pragma: no cover - only if the package is not installed
    __version__ = "1.2.0"
