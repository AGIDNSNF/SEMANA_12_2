#Requires -Version 5.1
<#
.SYNOPSIS
    Instala los tres casos de la Práctica Semana 12.
.DESCRIPTION
    Crea un entorno virtual por caso, instala Django, aplica migraciones y genera
    los datos de demostración. Es idempotente: reutiliza entornos existentes.
.PARAMETER SinDemo
    Omite la generación de datos de demostración.
.PARAMETER PythonExe
    Ejecutable de Python a usar (por ejemplo "python" o una ruta absoluta).
#>
[CmdletBinding()]
param(
    [switch]$SinDemo,
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONIOENCODING = "utf-8"
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

function Resolver-Python {
    param([string]$Preferido)
    if ($Preferido) {
        return @($Preferido)
    }

    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        foreach ($version in @("3.13", "3.12")) {
            & py "-$version" --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return @("py", "-$version")
            }
        }
    }

    if (Get-Command "python" -ErrorAction SilentlyContinue) {
        $salida = & python --version 2>&1
        if ("$salida" -match "3\.(12|13)\.") {
            return @("python")
        }
    }

    throw "No se encontró Python 3.12 o 3.13. Use -PythonExe para indicar la ruta."
}

$script:PythonCmd = Resolver-Python -Preferido $PythonExe

function Invoke-Python {
    param([string[]]$Argumentos)
    if ($script:PythonCmd.Count -gt 1) {
        $extra = $script:PythonCmd[1..($script:PythonCmd.Count - 1)]
        & $script:PythonCmd[0] @extra @Argumentos
    } else {
        & $script:PythonCmd[0] @Argumentos
    }
    if ($LASTEXITCODE -ne 0) {
        throw "El comando de Python falló con código $LASTEXITCODE."
    }
}

function Write-Paso {
    param([string]$Texto)
    Write-Host ""
    Write-Host "==> $Texto" -ForegroundColor Cyan
}

$Casos = @(
    @{ Nombre = "Caso 1 · Préstamos"; Carpeta = "caso1_prestamos"; App = "prestamos" },
    @{ Nombre = "Caso 2 · Consultas médicas"; Carpeta = "caso2_consultas_medicas"; App = "consultas" },
    @{ Nombre = "Caso 3 · Asistencia"; Carpeta = "caso3_asistencia"; App = "asistencia" }
)

Write-Host "Práctica Grupal Semana 12 · IS093A" -ForegroundColor Yellow
Write-Host "Raíz: $Raiz"

foreach ($caso in $Casos) {
    $directorio = Join-Path $Raiz $caso.Carpeta
    if (-not (Test-Path $directorio)) {
        throw "No se encontró la carpeta $directorio."
    }

    Write-Paso "$($caso.Nombre): preparando entorno"
    Push-Location $directorio
    try {
        $venvPython = Join-Path $directorio ".venv\Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            Write-Host "Creando entorno virtual..."
            Invoke-Python -Argumentos @("-m", "venv", ".venv")
        } else {
            Write-Host "Entorno virtual existente."
        }

        Write-Host "Instalando dependencias..."
        & $venvPython -m pip install --disable-pip-version-check --quiet -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw "Falló pip install en $($caso.Carpeta)." }

        Write-Host "Aplicando migraciones..."
        & $venvPython manage.py migrate --noinput
        if ($LASTEXITCODE -ne 0) { throw "Falló migrate en $($caso.Carpeta)." }

        if (-not $SinDemo) {
            Write-Host "Generando datos demo..."
            & $venvPython manage.py crear_datos_demo
            if ($LASTEXITCODE -ne 0) { throw "Falló crear_datos_demo en $($caso.Carpeta)." }
        }
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Instalación completada." -ForegroundColor Green
Write-Host "Ejecute:" -ForegroundColor Yellow
Write-Host "  .\iniciar_caso1.ps1   -> http://127.0.0.1:8001"
Write-Host "  .\iniciar_caso2.ps1   -> http://127.0.0.1:8002"
Write-Host "  .\iniciar_caso3.ps1   -> http://127.0.0.1:8003"
Write-Host "  .\probar_todo.ps1     -> verificación completa"
