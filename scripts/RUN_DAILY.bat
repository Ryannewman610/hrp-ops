@echo off
REM ============================================================
REM  HRP-Ops DAILY RUN (v3 pipeline)
REM  Full pipeline: export → parse → model → recommend → plan
REM  Estimated time: ~25 minutes with 35 horses
REM ============================================================

cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8

echo.
echo ========================================
echo  HRP-Ops Daily Run (v3)
echo ========================================
echo.

REM Step 0: Environment check
echo [1/10] Checking environment...
.venv\Scripts\python.exe scripts\00_env_check.py
if errorlevel 1 (
    echo FAILED: Environment check failed. See above.
    pause
    exit /b 1
)

REM Step 1: Auth check
echo.
echo [2/10] Checking authentication...
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
    echo AUTH EXPIRED: Session has expired. Launching login...
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

REM Step 2: Export (daily mode)
echo.
echo [3/10] Exporting stable data (daily mode)...
.venv\Scripts\python.exe scripts\02_export_stable.py --mode daily
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
echo [4/10] Parsing exports into tracker...
.venv\Scripts\python.exe scripts\04_parse_and_fill.py

REM Step 4: Build snapshot + base reports
echo.
echo [5/10] Building snapshot and base reports...
.venv\Scripts\python.exe scripts\05_build_stable_snapshot.py
.venv\Scripts\python.exe scripts\06_generate_reports.py

REM Step 5: Race calendar + model
echo.
echo [6/10] Parsing race calendar + building model...
.venv\Scripts\python.exe scripts\07_parse_race_calendar.py
.venv\Scripts\python.exe scripts\09_build_model_dataset.py
.venv\Scripts\python.exe scripts\10_fit_trainer_brain.py

REM Step 6: Recommendations + predictions log
echo.
echo [7/10] Generating recommendations + predictions log...
.venv\Scripts\python.exe scripts\11_recommend_with_trainer_brain.py

REM Step 7: Works intelligence + peak planner
echo.
echo [8/10] Works intelligence + peak planner...
.venv\Scripts\python.exe scripts\16_works_intelligence.py
.venv\Scripts\python.exe scripts\17_peak_planner.py

REM Step 8: Execution log + outcomes
echo.
echo [9/10] Execution log + outcomes + scoreboard...
.venv\Scripts\python.exe scripts\18_execution_log.py
.venv\Scripts\python.exe scripts\13_ingest_outcomes.py
.venv\Scripts\python.exe scripts\14_trainer_scoreboard.py

REM Step 9: Trust gate + sanity checks
echo.
echo [10/10] Running trust gate + sanity checks...
.venv\Scripts\python.exe scripts\trust_gate.py
if errorlevel 1 (
    echo.
    echo TRUST GATE FAILED! Reports contain broken tokens.
    echo Fix the pipeline before publishing outputs.
    pause
    exit /b 1
)
.venv\Scripts\python.exe scripts\sanity_check.py
if errorlevel 1 (
    echo.
    echo SANITY CHECK FAILED!
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Daily run complete! All checks passed.
echo  Check: reports\Stable_Dashboard.md
echo         reports\Race_Opportunities.md
echo         reports\Training_Plan.md
echo         reports\Approval_Pack.md
echo ========================================
pause
