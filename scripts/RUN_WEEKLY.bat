@echo off
REM ============================================================
REM  HRP-Ops WEEKLY RUN
REM  Full export: 8 pages per horse + globals + parse + reports
REM  Estimated time: ~60 minutes with 35 horses
REM ============================================================

cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8

echo.
echo ========================================
echo  HRP-Ops Weekly Run (Full Export)
echo ========================================
echo.

REM Step 0: Environment check
echo [1/5] Checking environment...
.venv\Scripts\python.exe scripts\00_env_check.py
if errorlevel 1 (
    echo FAILED: Environment check failed. See above.
    pause
    exit /b 1
)

REM Step 1: Auth check
echo.
echo [2/5] Checking authentication...
.venv\Scripts\python.exe scripts\00_auth_check.py
if errorlevel 2 (
    echo.
    echo AUTH MISSING: Run login first:
    echo   .venv\Scripts\python.exe scripts\01_login_save_state.py
    pause
    exit /b 1
)
if errorlevel 1 (
    echo.
    echo AUTH EXPIRED: Launching login...
    .venv\Scripts\python.exe scripts\01_login_save_state.py
    echo.
    echo Re-checking auth...
    .venv\Scripts\python.exe scripts\00_auth_check.py
    if errorlevel 1 (
        echo AUTH STILL FAILED. Please try again.
        pause
        exit /b 1
    )
)

REM Step 2: Export (weekly = full 8 pages per horse)
echo.
echo [3/5] Exporting stable data (WEEKLY - full export)...
.venv\Scripts\python.exe scripts\02_export_stable.py --mode weekly
if errorlevel 2 (
    echo.
    echo PARTIAL EXPORT: Session expired mid-run. Re-login and retry.
    pause
    exit /b 2
)
if errorlevel 1 (
    echo EXPORT FAILED.
    pause
    exit /b 1
)

REM Step 3: Parse into tracker
echo.
echo [4/5] Parsing exports into tracker...
.venv\Scripts\python.exe scripts\04_parse_and_fill.py

REM Step 4: Build snapshot + reports
echo.
echo [5/5] Building snapshot and reports...
.venv\Scripts\python.exe scripts\05_build_stable_snapshot.py
.venv\Scripts\python.exe scripts\06_generate_reports.py

echo.
echo ========================================
echo  Weekly run complete!
echo  Check: reports\Stable_Dashboard.md
echo ========================================
pause
