@echo off
setlocal

if not exist "inputs\export\auth.json" (
  echo Missing inputs\export\auth.json
  echo Run: python scripts\01_login_save_state.py
  exit /b 1
)

python scripts\03_make_fresh_tracker.py
if errorlevel 1 exit /b 1

python scripts\02_export_stable.py
if errorlevel 1 exit /b 1

python scripts\04_parse_and_fill.py
if errorlevel 1 exit /b 1

echo Full rebuild complete.
exit /b 0
