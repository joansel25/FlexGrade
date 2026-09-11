# ---------------------------------------------------------------------------
# Encuentra el bash de Git y ejecuta con el un script de esta carpeta.
#
# No se ejecuta solo: lo llaman estado.ps1, levantar.ps1 y destruir.ps1.
#
# POR QUE HACE FALTA BUSCARLO EN VEZ DE ESCRIBIR `bash`
#
# En Windows 11, `bash` en el PATH es `C:\Windows\system32\bash.exe`, que es el LANZADOR DE WSL,
# no el de Git. Si no hay ninguna distribucion de Linux instalada —el caso normal— falla con:
#
#     WSL (...) ERROR: CreateProcessCommon:818: execvpe(/bin/bash) failed: No such file or directory
#
# Un mensaje que no menciona ni el script ni Git, y que manda a diagnosticar WSL en lugar de
# mirar donde esta el problema. Por eso aqui se busca el binario de Git directamente.
#
# Y AUNQUE WSL FUNCIONARA, TAMPOCO SERVIRIA: dentro de WSL las rutas de Windows se ven bajo
# /mnt/c/..., y `az` no esta instalado ahi. Serian dos maquinas distintas.
# ---------------------------------------------------------------------------

$ErrorActionPreference = 'Stop'

function Invoke-ScriptBash {
    param(
        [Parameter(Mandatory = $true)] [string] $Script,
        [string[]] $Argumentos = @()
    )

    $candidatos = @(
        "$env:ProgramFiles\Git\bin\bash.exe",
        "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
    )

    $bash = $candidatos | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

    if (-not $bash) {
        Write-Host "No encuentro el bash de Git." -ForegroundColor Red
        Write-Host "Se instala con Git para Windows: https://git-scm.com/download/win" -ForegroundColor Red
        exit 1
    }

    # La ruta se pasa en formato de Windows: el bash de Git la entiende, y asi no hay que
    # traducirla aqui.
    $ruta = Join-Path $PSScriptRoot $Script

    & $bash $ruta @Argumentos
    exit $LASTEXITCODE
}
