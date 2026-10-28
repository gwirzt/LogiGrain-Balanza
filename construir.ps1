# Genera dist\BalanzaLogigrain\BalanzaLogigrain.exe
# Uso: .\construir.ps1
# PyInstaller borra dist\BalanzaLogigrain completo: antes se respalda todo lo que no genera la compilacion
# (config.toml, .env, datos\ con la base y los tickets, y cualquier otro archivo agregado a mano)
# y al terminar se restaura, aunque la compilacion falle.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$dist = Join-Path $PSScriptRoot "dist\BalanzaLogigrain"
$generados = @("BalanzaLogigrain.exe", "_internal", "config.example.toml", "manual_de_instrucciones_balanza.md")
$respaldo = Join-Path $env:TEMP ("BalanzaLogigrain-respaldo-" + (Get-Date -Format "yyyyMMdd-HHmmss"))

function Test-Libre([string]$ruta) {
    try { [IO.File]::Open($ruta, "Open", "ReadWrite", "None").Close(); return $true } catch { return $false }
}

& .\.venv\Scripts\python.exe -m pip install -q -r requirements-dev.txt
& .\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Fallaron las pruebas, no se genera el ejecutable." }

$propios = @()
if (Test-Path $dist) {
    if (Get-Process BalanzaLogigrain -ErrorAction SilentlyContinue) {
        throw "BalanzaLogigrain esta abierto. Cerrarlo y volver a ejecutar."
    }
    # Un archivo abierto (por ejemplo un PDF en el visor) corta a PyInstaller a mitad de la limpieza.
    $abiertos = Get-ChildItem $dist -Recurse -File | Where-Object { -not (Test-Libre $_.FullName) }
    if ($abiertos) {
        throw ("Hay archivos abiertos en otro programa; cerrarlos y volver a ejecutar:`n  " +
               (($abiertos | ForEach-Object { $_.FullName }) -join "`n  "))
    }
    $propios = Get-ChildItem $dist -Force | Where-Object { $generados -notcontains $_.Name }
    if ($propios) {
        New-Item -ItemType Directory $respaldo | Out-Null
        $propios | Copy-Item -Destination $respaldo -Recurse -Force
        Write-Host "Respaldo de config y datos: $respaldo"
    }
}

try {
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
    $fallo = $LASTEXITCODE -ne 0
    if (-not $fallo) {
        Copy-Item config.example.toml (Join-Path $dist "config.example.toml") -Force
        Copy-Item manual_de_instrucciones_balanza.md (Join-Path $dist "manual_de_instrucciones_balanza.md") -Force
    }
}
finally {
    if ($propios) {
        New-Item -ItemType Directory $dist -Force | Out-Null
        Get-ChildItem $respaldo -Force | Copy-Item -Destination $dist -Recurse -Force
        Write-Host ("Restaurado en dist: " + (($propios | ForEach-Object { $_.Name }) -join ", "))
    }
}
if ($fallo) { throw "Fallo PyInstaller (config y datos restaurados desde $respaldo)." }
Write-Host "Listo: dist\BalanzaLogigrain\BalanzaLogigrain.exe"
