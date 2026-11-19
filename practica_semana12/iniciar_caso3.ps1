#Requires -Version 5.1
<#
.SYNOPSIS
    Inicia el Caso 3 · Asistencia y permisos en el puerto 8003.
.PARAMETER NoBrowser
    No abre el navegador automáticamente.
#>
[CmdletBinding()]
param([switch]$NoBrowser)

$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$Caso = Join-Path $Raiz "caso3_asistencia"
$Puerto = 8003
$Url = "http://127.0.0.1:$Puerto/"
$env:PYTHONIOENCODING = "utf-8"
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

if (-not (Test-Path $Caso)) {
    Write-Host "No se encontró la carpeta $Caso." -ForegroundColor Red
    exit 1
}

$Python = Join-Path $Caso ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = Join-Path $Raiz ".venv\Scripts\python.exe"
}
if (-not (Test-Path $Python)) {
    $Python = Join-Path (Split-Path -Parent $Raiz) ".venv\Scripts\python.exe"
}
if (-not (Test-Path $Python)) {
    Write-Host "No se encontró un entorno virtual." -ForegroundColor Red
    Write-Host "Ejecute primero: .\instalar.ps1" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path (Join-Path $Caso "db.sqlite3"))) {
    Write-Host "No existe db.sqlite3. Se aplicarán migraciones y datos demo al iniciar." -ForegroundColor Yellow
}

Write-Host "Caso 3 · Asistencia y permisos" -ForegroundColor Yellow
Write-Host "URL: $Url"
Write-Host "Detenga el servidor con Ctrl+C." -ForegroundColor DarkGray

$job = $null
if (-not $NoBrowser) {
    $job = Start-Job -ScriptBlock {
        param($direccion)
        Start-Sleep -Seconds 2
        Start-Process $direccion
    } -ArgumentList $Url
}

Push-Location $Caso
try {
    if (-not (Test-Path (Join-Path $Caso "db.sqlite3"))) {
        Write-Host "Aplicando migraciones..." -ForegroundColor Yellow
        & $Python manage.py migrate --noinput
    }

    $consulta = "from django.contrib.auth import get_user_model; print('HAY' if get_user_model().objects.exists() else 'VACIA')"
    $estado = (& $Python manage.py shell -c $consulta 2>&1 | Out-String)
    if ($estado -notmatch "HAY") {
        Write-Host "No hay usuarios demo. Generando datos de demostración..." -ForegroundColor Yellow
        & $Python manage.py crear_datos_demo
    }

    & $Python manage.py runserver "127.0.0.1:$Puerto"
} finally {
    Pop-Location
    if ($job) {
        Stop-Job $job -ErrorAction SilentlyContinue
        Remove-Job $job -Force -ErrorAction SilentlyContinue
    }
}
