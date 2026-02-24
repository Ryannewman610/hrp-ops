# HRP-Ops Quickstart

## Daily Run (~12 min)
```
scripts\RUN_DAILY.bat
```
Exports roster + 5 global pages + 3 pages/horse (profile, works, meters) → parses → snapshot → reports.

## Weekly Run (~55 min)
```
scripts\RUN_WEEKLY.bat
```
Same as daily but exports all 8 pages/horse (adds pedigree, conformation, accessories, foals).

## When Login Expires
The pipeline auto-detects expired sessions. If it happens:
1. A Chromium browser opens automatically
2. Log in at HRP
3. Return to terminal, press Enter
4. Pipeline continues

Manual login: `.venv\Scripts\python.exe scripts\01_login_save_state.py`

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
| Auth cookies | `inputs/export/auth.json` (gitignored) |
