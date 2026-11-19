#Requires -Version 5.1
<#
.SYNOPSIS
    Ejecuta la verificación completa de los tres casos.
.DESCRIPTION
    Para cada caso ejecuta: check, makemigrations --check --dry-run, migrate y test.
    Muestra un resumen y devuelve código 1 si alguna prueba falla.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$Raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONIOENCODING = "utf-8"
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

function Resolver-PythonCaso {
    param([string]$Directorio)
    $candidatos = @(
        (Join-Path $Directorio ".venv\Scripts\python.exe"),
        (Join-Path $Raiz ".venv\Scripts\python.exe"),
        (Join-Path (Split-Path -Parent $Raiz) ".venv\Scripts\python.exe")
    )
    foreach ($candidato in $candidatos) {
        if (Test-Path $candidato) { return $candidato }
    }
    $cmdPython = Get-Command "python" -ErrorAction SilentlyContinue
    if ($cmdPython) { return $cmdPython.Source }
    throw "No se encontró Python para $Directorio. Ejecute .\instalar.ps1."
}

function Executar-Paso {
    param(
        [string]$Etiqueta,
        [string]$Directorio,
        [string]$Python,
        [string[]]$Argumentos
    )
    Write-Host ""
    Write-Host ">>> $Etiqueta" -ForegroundColor Cyan
    Write-Host "    $Python $($Argumentos -join ' ')" -ForegroundColor DarkGray
    Push-Location $Directorio
    try {
        & $Python @Argumentos 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                $texto = $_.Exception.Message
                if ($texto) { Write-Host $texto }
            } else {
                Write-Host $_
            }
        }
        $codigo = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($codigo -eq 0) {
        Write-Host "    OK" -ForegroundColor Green
    } else {
        Write-Host "    FALLO (codigo $codigo)" -ForegroundColor Red
    }
    return $codigo
}

$Casos = @(
    @{ Nombre = "Caso 1 - Prestamos"; Carpeta = "caso1_prestamos"; App = "prestamos" },
    @{ Nombre = "Caso 2 - Consultas medicas"; Carpeta = "caso2_consultas_medicas"; App = "consultas" },
    @{ Nombre = "Caso 3 - Asistencia"; Carpeta = "caso3_asistencia"; App = "asistencia" }
)

Write-Host "Verificacion completa - Practica Semana 12" -ForegroundColor Yellow
Write-Host "Fecha: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"

$resultados = @()
$fallos = 0

foreach ($caso in $Casos) {
    $directorio = Join-Path $Raiz $caso.Carpeta
    if (-not (Test-Path $directorio)) {
        Write-Host "No se encontro $directorio" -ForegroundColor Red
        $fallos++
        continue
    }

    $python = Resolver-PythonCaso -Directorio $directorio
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkGray
    Write-Host $caso.Nombre -ForegroundColor Yellow
    Write-Host ("=" * 70) -ForegroundColor DarkGray

    $check = Executar-Paso -Etiqueta "check" -Directorio $directorio -Python $python -Argumentos @("manage.py", "check")
    $migraciones = Executar-Paso -Etiqueta "makemigrations --check --dry-run" -Directorio $directorio -Python $python -Argumentos @("manage.py", "makemigrations", "--check", "--dry-run")
    $migrate = Executar-Paso -Etiqueta "migrate" -Directorio $directorio -Python $python -Argumentos @("manage.py", "migrate", "--noinput")
    $test = Executar-Paso -Etiqueta "test $($caso.App)" -Directorio $directorio -Python $python -Argumentos @("manage.py", "test", $caso.App, "-v", "1")

    $estado = "REVISAR"
    if (($check + $migraciones + $migrate + $test) -eq 0) { $estado = "OK" }
    if ($estado -ne "OK") { $fallos++ }

    $checkTexto = "FALLA"
    if ($check -eq 0) { $checkTexto = "OK" }
    $migracionesTexto = "FALLA"
    if ($migraciones -eq 0) { $migracionesTexto = "OK" }
    $migrateTexto = "FALLA"
    if ($migrate -eq 0) { $migrateTexto = "OK" }
    $testTexto = "FALLA"
    if ($test -eq 0) { $testTexto = "OK" }

    $resultados += [PSCustomObject]@{
        Caso        = $caso.Nombre
        Check       = $checkTexto
        Migraciones = $migracionesTexto
        Migrate     = $migrateTexto
        Test        = $testTexto
        Estado      = $estado
    }
}

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor DarkGray
Write-Host "Resumen" -ForegroundColor Yellow
Write-Host ("=" * 70) -ForegroundColor DarkGray
$resultados | Format-Table -AutoSize | Out-String | Write-Host

if ($fallos -eq 0) {
    Write-Host "Todas las verificaciones finalizaron correctamente." -ForegroundColor Green
    exit 0
} else {
    Write-Host ("Hay {0} caso(s) con fallos. Revise la salida anterior." -f $fallos) -ForegroundColor Red
    exit 1
}
