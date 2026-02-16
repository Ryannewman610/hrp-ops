Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    Set-Location $repoRoot

    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        throw "Missing .venv. Run .\scripts\bootstrap.ps1 first."
    }

    & $venvPython -m pytest -q
}
catch {
    Write-Error "run_tests.ps1 failed: $($_.Exception.Message)"
    Write-Error "Create/setup venv with: .\scripts\bootstrap.ps1"
    exit 1
}
