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

6. Parse race calendar:
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/07_parse_race_calendar.py
```

7. Build horse models (ELO ratings):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/10_fit_trainer_brain.py
```

8. Parse horse abilities (speed/surface/distance from meters.html):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/19_parse_horse_abilities.py
```

9. Works intelligence (readiness, fatigue, trend):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/16_works_intelligence.py
```

10. Peak planner (14-day schedule):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/17_peak_planner.py
```

11. Race recommendations (ability-aware, eligibility-gated):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/11_recommend_with_trainer_brain.py
```

12. Generate reports (Dashboard, Weekly Plan, Decisions Log):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/06_generate_reports.py
```

13. Trainer scoreboard:
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/14_trainer_scoreboard.py
```

14. Compare snapshots (day-over-day changes):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/compare_snapshots.py
```

15. Trust gate (verify report integrity):
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/trust_gate.py
```

16. Sanity check:
```
cd c:\hrp-ops; .\.venv\Scripts\python.exe scripts/sanity_check.py
```

17. Commit and push:
```
cd c:\hrp-ops; git add -A; git commit -m "Daily snapshot $(Get-Date -Format yyyy-MM-dd)"; git push
```
