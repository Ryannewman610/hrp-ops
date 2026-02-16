Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    Set-Location $repoRoot

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if (-not $pyCmd) {
        throw "Python launcher 'py' was not found. Install Python for Windows and ensure 'py' is on PATH."
    }

    $venvDir = Join-Path $repoRoot ".venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    $requirementsPath = Join-Path $repoRoot "requirements.txt"

    if (-not (Test-Path $venvPython)) {
        Write-Host "Creating virtual environment at .venv ..."
        & py -m venv .venv
    } else {
        Write-Host "Using existing virtual environment at .venv"
    }

    if (-not (Test-Path $venvPython)) {
        throw "Virtual environment python not found at $venvPython after creation."
    }

    Write-Host "Upgrading pip ..."
    & $venvPython -m pip install --upgrade pip

    if (Test-Path $requirementsPath) {
        Write-Host "Installing dependencies from requirements.txt ..."
        & $venvPython -m pip install -r $requirementsPath
    } else {
        Write-Host "requirements.txt not found; installing pytest only ..."
        & $venvPython -m pip install pytest
    }

    Write-Host "Running tests ..."
    & $venvPython -m pytest -q

    Write-Host "Bootstrap complete."
}
catch {
    Write-Error "bootstrap.ps1 failed: $($_.Exception.Message)"
    Write-Error "Fix the issue above, then re-run: .\scripts\bootstrap.ps1"
    exit 1
}
