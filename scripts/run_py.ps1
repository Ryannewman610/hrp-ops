param(
    [Parameter(Mandatory = $true)]
    [string]$Args
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    Set-Location $repoRoot

    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        throw "Missing .venv. Run .\scripts\bootstrap.ps1 first."
    }

    # Basic argument splitting for usage like: -Args "-m pytest -q"
    $pythonArgs = $Args -split "\s+"
    if (-not $pythonArgs -or $pythonArgs.Count -eq 0) {
        throw "No python arguments were provided."
    }

    & $venvPython @pythonArgs
}
catch {
    Write-Error "run_py.ps1 failed: $($_.Exception.Message)"
    Write-Error "Example: .\scripts\run_py.ps1 -Args ""-m pytest -q"""
    exit 1
}
