@echo off
REM ============================================================
REM  HRP-Ops DAILY SCHEDULED (non-interactive)
REM  For Task Scheduler — exits cleanly if login required.
REM  Does NOT open a browser or prompt for input.
REM ============================================================

cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
set PIPELINE_OK=1

echo [%date% %time%] Daily scheduled run starting >> outputs\scheduled_run.log

REM Step 1: Environment check
.venv\Scripts\python.exe scripts\00_env_check.py
if errorlevel 1 (
    echo [%date% %time%] FAIL: Environment check >> outputs\scheduled_run.log
    .venv\Scripts\python.exe scripts\07_write_run_status.py 1 env_check
    exit /b 1
)

REM Step 2: Auth check (non-interactive — just exit if expired)
.venv\Scripts\python.exe scripts\00_auth_check.py
if errorlevel 1 (
    echo [%date% %time%] LOGIN REQUIRED: Session expired. Run scripts\RUN_DAILY.bat manually. >> outputs\scheduled_run.log
    echo.
    echo ========================================
    echo  LOGIN REQUIRED
    echo  Session expired. Run manually:
    echo    scripts\RUN_DAILY.bat
    echo ========================================
    .venv\Scripts\python.exe scripts\07_write_run_status.py 2 auth_expired
    exit /b 2
)

REM Step 3: Export (daily mode)
.venv\Scripts\python.exe scripts\02_export_stable.py --mode daily
if errorlevel 2 (
    echo [%date% %time%] PARTIAL: Session expired mid-export >> outputs\scheduled_run.log
    set PIPELINE_OK=0
)
if errorlevel 1 (
    if %PIPELINE_OK%==1 (
        echo [%date% %time%] FAIL: Export failed >> outputs\scheduled_run.log
        .venv\Scripts\python.exe scripts\07_write_run_status.py 1 export
        exit /b 1
    )
)

REM Step 4: Parse into tracker
.venv\Scripts\python.exe scripts\04_parse_and_fill.py

REM Step 5: Build snapshot + reports
.venv\Scripts\python.exe scripts\05_build_stable_snapshot.py
.venv\Scripts\python.exe scripts\06_generate_reports.py

REM Step 6: Write status file
if %PIPELINE_OK%==1 (
    .venv\Scripts\python.exe scripts\07_write_run_status.py 0 complete
    echo [%date% %time%] SUCCESS: Daily run complete >> outputs\scheduled_run.log
) else (
    .venv\Scripts\python.exe scripts\07_write_run_status.py 2 partial_export
    echo [%date% %time%] PARTIAL: Daily run completed with partial export >> outputs\scheduled_run.log
)

exit /b 0
