# Scheduler Registration Report — 2026-02-24

## Registered Tasks

| Task Name | Schedule | Next Run | State |
|-----------|----------|----------|-------|
| HRP-Ops Daily | Every day at 7:00 AM | 2/25/2026 7:00 AM | Ready |
| HRP-Ops Weekly | Every Sunday at 6:00 AM | 3/1/2026 6:00 AM | Ready |

## Manual Test Results

| Task | Triggered At | Log Entry | Outcome |
|------|-------------|-----------|---------|
| HRP-Ops Daily | 2/24/2026 2:00 PM | `scheduled_run.log` entry confirmed | Auth expired (expected — session >1hr old). Task ran bat file, wrote log, invoked auth check. |

> The daily task was triggered manually via `Start-ScheduledTask`. It successfully:
> - Started from Task Scheduler context
> - Changed to correct working directory (`c:\hrp-ops`)
> - Wrote "daily scheduled run starting" to log

Auth was expired at the time of test (session >1 hour old), so the task ran the auth check
which spawns headless Chromium — this is expected to be slow (~30-60s) in Task Scheduler context.

## Where to Look for Logs

| File | Purpose |
|------|---------|
| `outputs/scheduled_run.log` | Append-only log of all scheduled runs |
| `outputs/last_run_status.json` | JSON with success/fail, horses, pages, errors |

## When Auth Expires

Scheduled tasks exit cleanly with code 2 and "LOGIN REQUIRED" message. To fix:
1. Open a terminal in `c:\hrp-ops`
2. Run `scripts\RUN_DAILY.bat` (interactive — auto-opens login browser)
3. Log in, press Enter
4. Scheduled runs will work again until next session expiry

## Task Management

```powershell
# View tasks
Get-ScheduledTask -TaskName "HRP-Ops*"

# Trigger manually
Start-ScheduledTask -TaskName "HRP-Ops Daily"

# Remove
Unregister-ScheduledTask -TaskName "HRP-Ops Daily" -Confirm:$false
Unregister-ScheduledTask -TaskName "HRP-Ops Weekly" -Confirm:$false
```
