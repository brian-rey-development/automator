"""Utilidades del sistema operativo independientes de la plataforma."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def open_folder(path: Path) -> None:
    """Abre una carpeta en el explorador de archivos del sistema."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]  # Solo existe en Windows.
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except OSError:
        logger.exception("No se pudo abrir la carpeta %s", path)


def notify(title: str, message: str) -> None:
    """Muestra un aviso del sistema, en best-effort: si no se puede, no hace nada.

    Nunca lanza ni bloquea: un aviso que falla no debe afectar el procesamiento.
    """
    try:
        if sys.platform == "darwin":
            script = f"display notification {_applescript_quote(message)} with title {_applescript_quote(title)}"
            subprocess.run(["osascript", "-e", script], check=False, timeout=5)
        elif sys.platform.startswith("win"):
            _notify_windows(title, message)
        # En Linux no hay una via universal sin dependencias: se omite en silencio.
    except (OSError, subprocess.SubprocessError):
        logger.debug("No se pudo mostrar el aviso del sistema", exc_info=True)


def _applescript_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _notify_windows(title: str, message: str) -> None:
    # Aviso nativo via PowerShell (globo de la bandeja); best-effort, sin dependencias.
    safe_title = title.replace("'", "''")
    safe_message = message.replace("'", "''")
    script = (
        "[reflection.assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null;"
        "$n = New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon = [System.Drawing.SystemIcons]::Information;"
        "$n.BalloonTipTitle = '" + safe_title + "';"
        "$n.BalloonTipText = '" + safe_message + "';"
        "$n.Visible = $true; $n.ShowBalloonTip(5000); Start-Sleep -Seconds 6; $n.Dispose()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        check=False,
        timeout=10,
    )
