# -*- mode: python ; coding: utf-8 -*-
"""Especificacion de PyInstaller para generar el ejecutable de Windows.

Genera un unico .exe sin consola. CustomTkinter incluye archivos de tema que
deben empaquetarse explicitamente con collect_all.
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

_ctk_datas, _ctk_binaries, _ctk_hiddenimports = collect_all("customtkinter")
# watchdog's Windows backend (ReadDirectoryChangesW) lives in submodules that are not
# imported on the macOS dev machine, so PyInstaller would miss them; collect them all.
_watchdog_hiddenimports = collect_submodules("watchdog")

a = Analysis(
    ["src/automator/__main__.py"],
    pathex=["src"],
    binaries=_ctk_binaries,
    datas=_ctk_datas + [("assets/automator.png", "assets")],
    hiddenimports=(
        _ctk_hiddenimports
        + _watchdog_hiddenimports
        + ["pypdf", "pydantic", "pydantic_core", "platformdirs", "openpyxl", "et_xmlfile"]
    ),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Automator",
    icon="assets/automator.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
