---
description: Daily HRP stable snapshot and report update
---
// turbo-all

# Daily Snapshot Workflow

## Prerequisites
- Python venv at `c:\hrp-ops\.venv`
- Valid auth.json (run `01_login_save_state.py` if expired)

## Steps

1. Check environment:
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/00_env_check.py
```

2. Check auth (if fails, run step 2b):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/00_auth_check.py
```

2b. (Only if auth expired) Login and save state:
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/01_login_save_state.py
```

3. Export stable data (daily mode, ~12 min):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/02_export_stable.py --mode daily
```

4. Parse and fill tracker:
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/04_parse_and_fill.py
```

5. Build stable snapshot:
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/05_build_stable_snapshot.py
```

6. Generate reports (Dashboard, Weekly Plan, Decisions Log):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/06_generate_reports.py
```

7. Race recommendations (calendar parsing + horse-to-race matching):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/recommend_races.py
```

8. Compare snapshots (day-over-day changes):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/compare_snapshots.py
```

9. Write run status:
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/07_write_run_status.py
```

10. Sanity check:
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/sanity_check.py
```

11. Commit and push:
```
cd c:\hrp-ops; git add -A; git commit -m "Daily snapshot $(Get-Date -Format yyyy-MM-dd)"; git push
```
