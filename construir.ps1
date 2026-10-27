# Genera dist\BalanzaLogigrain\BalanzaLogigrain.exe
# Uso: .\construir.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

& .\.venv\Scripts\python.exe -m pip install -q -r requirements-dev.txt
& .\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Fallaron las pruebas, no se genera el ejecutable." }

& .\.venv\Scripts\pyinstaller.exe lanzador.py `
    --name BalanzaLogigrain `
    --windowed `
    --noconfirm `
    --clean `
    --exclude-module tkinter `
    --exclude-module PySide6.QtWebEngineCore `
    --exclude-module PySide6.Qt3DCore `
    --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.QtQml `
    --exclude-module PySide6.QtMultimedia
if ($LASTEXITCODE -ne 0) { throw "Falló PyInstaller." }

Copy-Item config.example.toml dist\BalanzaLogigrain\config.example.toml -Force
Write-Host "Listo: dist\BalanzaLogigrain\BalanzaLogigrain.exe"
