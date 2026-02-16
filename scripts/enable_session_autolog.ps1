param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$notesPath = Join-Path $RepoRoot "SESSION_NOTES.md"

if (-not (Test-Path $notesPath)) {
    @(
        "# Session Notes",
        "",
        "Last updated: $(Get-Date -Format 'yyyy-MM-dd')",
        "",
        "## Input Log"
    ) | Set-Content -Path $notesPath -Encoding UTF8
}

$content = Get-Content -Path $notesPath -Raw
if ($content -notmatch "(?im)^## Input Log\s*$") {
    Add-Content -Path $notesPath -Encoding UTF8 -Value "`r`n## Input Log`r`n"
}

$global:SessionNotesAutoLogPath = $notesPath
$global:SessionNotesAutoLogEnabled = $true

Set-PSReadLineOption -AddToHistoryHandler {
    param([string]$line)
    if (-not $global:SessionNotesAutoLogEnabled) {
        return $true
    }
    if ([string]::IsNullOrWhiteSpace($line)) {
        return $true
    }

    $singleLine = ($line -replace "\r?\n", " ").Trim()
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $global:SessionNotesAutoLogPath -Encoding UTF8 -Value "- [$stamp] $singleLine"
    return $true
}

Write-Output "Session auto-log enabled: $notesPath"
