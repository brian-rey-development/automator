# Prepara el entorno de desarrollo y ejecuta la app desde el codigo fuente.
# Uso:  .\scripts\dev.ps1
$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    Write-Host "==> Creando entorno virtual" -ForegroundColor Cyan
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1

Write-Host "==> Instalando dependencias (modo editable)" -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

Write-Host "==> Iniciando la aplicacion" -ForegroundColor Cyan
python -m automator
