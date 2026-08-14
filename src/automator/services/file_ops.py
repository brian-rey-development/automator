"""Operaciones seguras de archivos: espera de estabilidad, unicidad y movimiento."""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

_STABILITY_POLL_INTERVAL_S = 0.4
_LONG_PATH_PREFIX = "\\\\?\\"
_UNC_PREFIX = "\\\\"
_LONG_PATH_UNC_PREFIX = "\\\\?\\UNC\\"


def is_pdf(path: Path) -> bool:
    """True si el archivo tiene extension .pdf (sin distinguir mayusculas)."""
    return path.suffix.lower() == ".pdf"


def wait_until_stable(
    path: Path,
    timeout_s: float,
    poll_interval_s: float = _STABILITY_POLL_INTERVAL_S,
) -> bool:
    """Espera a que el tamano del archivo se estabilice (descarga terminada).

    Devuelve True solo si el archivo dejo de crecer dentro del tiempo limite.
    Devuelve False si expiro el tiempo mientras seguia cambiando o nunca aparecio.
    """
    deadline = time.monotonic() + timeout_s
    last_size = -1
    while True:
        current_size = _safe_size(path)
        if current_size >= 0 and current_size == last_size:
            return True
        last_size = current_size
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval_s)


def unique_destination(path: Path) -> Path:
    """Devuelve una ruta que no existe, agregando ' (n)' si hay colision."""
    if not path.exists():
        return path
    parent, stem, suffix = path.parent, path.stem, path.suffix
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def move_file(source: Path, target_dir: Path, filename: str) -> Path:
    """Mueve el archivo a la carpeta destino evitando sobrescrituras.

    Usa shutil.move para soportar movimientos entre discos distintos (C: a red).
    El worker es unico y secuencial, por lo que no hay carrera real entre el
    calculo del destino y el movimiento.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    target = unique_destination(target_dir / filename)
    shutil.move(_os_path(source), _os_path(target))
    return target


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return -1


def _os_path(path: Path) -> str:
    """Ruta lista para el sistema, con prefijo de rutas largas en Windows.

    Windows limita las rutas a 260 caracteres salvo que se use el prefijo
    extendido, necesario para carpetas de proveedor muy anidadas.
    """
    text = str(path)
    if not sys.platform.startswith("win") or not os.path.isabs(text) or text.startswith(_LONG_PATH_PREFIX):
        return text
    # Las rutas UNC (\\servidor\recurso) requieren la forma \\?\UNC\servidor\recurso,
    # no un simple prefijo antepuesto (que produciria una ruta invalida).
    if text.startswith(_UNC_PREFIX):
        return _LONG_PATH_UNC_PREFIX + text[len(_UNC_PREFIX) :]
    return _LONG_PATH_PREFIX + text
