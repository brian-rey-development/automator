# Genera el ejecutable de Windows (dist/Facturas.exe).
# Uso: abrir PowerShell en la carpeta del proyecto y ejecutar:  .\scripts\build_windows.ps1
$ErrorActionPreference = "Stop"

Write-Host "==> Creando entorno virtual" -ForegroundColor Cyan
python -m venv .venv
.\.venv\Scripts\Activate.ps1

Write-Host "==> Instalando dependencias" -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

Write-Host "==> Ejecutando la bateria de tests" -ForegroundColor Cyan
python -m pytest

Write-Host "==> Empaquetando con PyInstaller" -ForegroundColor Cyan
python -m PyInstaller automator.spec --noconfirm --clean

Write-Host "==> Listo. El ejecutable esta en dist\Automator.exe" -ForegroundColor Green
