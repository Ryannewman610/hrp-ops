# HRP-Ops Quickstart

## Daily Run (~12 min) — Interactive
```
scripts\RUN_DAILY.bat
```
Exports roster + 5 global pages + 3 pages/horse → parses → snapshot → reports.
If session expired, auto-opens browser for login.

## Weekly Run (~55 min) — Interactive
```
scripts\RUN_WEEKLY.bat
```
Same as daily but exports all 8 pages/horse (adds pedigree, conformation, accessories, foals).

## Scheduled (Unattended) Runs
```
scripts\RUN_DAILY_SCHEDULED.bat
scripts\RUN_WEEKLY_SCHEDULED.bat
```
Same pipeline but **non-interactive**: if auth is expired, exits with `LOGIN REQUIRED` (exit code 2) instead of opening a browser. Check `outputs/last_run_status.json` for results.

## When Login Expires
For interactive runs, the pipeline auto-detects and opens a browser.
For scheduled runs, you'll see `LOGIN REQUIRED` in the log. Fix it:
1. Run `.venv\Scripts\python.exe scripts\01_login_save_state.py`
2. Log in at HRP in the browser that opens
3. Return to terminal, press Enter
4. Re-run the scheduled bat, or wait for next scheduled time

## Task Scheduler Setup

### Daily Run (every day at 7:00 AM)
```powershell
# Run in PowerShell as Administrator:
$action = New-ScheduledTaskAction `
    -Execute "c:\hrp-ops\scripts\RUN_DAILY_SCHEDULED.bat" `
    -WorkingDirectory "c:\hrp-ops"
$trigger = New-ScheduledTaskTrigger -Daily -At 7:00AM
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask `
    -TaskName "HRP-Ops Daily" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "HRP stable data export + reports (daily mode)"
```

### Weekly Run (Sundays at 6:00 AM)
```powershell
$action = New-ScheduledTaskAction `
    -Execute "c:\hrp-ops\scripts\RUN_WEEKLY_SCHEDULED.bat" `
    -WorkingDirectory "c:\hrp-ops"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 6:00AM
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask `
    -TaskName "HRP-Ops Weekly" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "HRP stable data export + reports (full weekly mode)"
```

### Remove Scheduled Tasks
```powershell
Unregister-ScheduledTask -TaskName "HRP-Ops Daily" -Confirm:$false
Unregister-ScheduledTask -TaskName "HRP-Ops Weekly" -Confirm:$false
```

## Where Outputs Go
| Output | Path |
|--------|------|
| Raw HTML | `inputs/export/raw/{horse}/` |
| Global pages | `inputs/export/raw/_global/` |
| Daily snapshot | `inputs/YYYY-MM-DD/stable_snapshot.json` |
| Tracker | `tracker/HRP_Tracker.xlsx` |
| Dashboard | `reports/Stable_Dashboard.md` |
| Weekly Plan | `reports/Weekly_Plan.md` |
| Decisions Log | `reports/Decisions_Log.md` (append-only) |
| **Run status** | `outputs/last_run_status.json` |
| **Schedule log** | `outputs/scheduled_run.log` |
| Auth cookies | `inputs/export/auth.json` (gitignored) |
