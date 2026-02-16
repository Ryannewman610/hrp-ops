# HRP Fresh Rebuild Setup

This project has a full rebuild pipeline that refreshes the tracker from live HRP pages.

## One-time setup

1. Install Python 3.10+.
2. Install required packages:

```powershell
pip install playwright openpyxl
python -m playwright install chromium
```

3. Confirm roster URL exists in `scripts\hrp_urls.json` under `stable_roster_url`.
4. Confirm template exists at exactly `tracker\TEMPLATE_HRP_Tracker.xlsx`.

## Login and save session

Run this when `inputs\export\auth.json` is missing or expired:

```powershell
python scripts\01_login_save_state.py
```

What it does:
- Opens Chromium in headed mode.
- Navigates to `stable_roster_url`.
- Waits for manual login.
- Saves session state to `inputs\export\auth.json`.

## Run full rebuild

```powershell
scripts\RUN_FULL_REBUILD.bat
```

Order:
1. `scripts\03_make_fresh_tracker.py`
2. `scripts\02_export_stable.py`
3. `scripts\04_parse_and_fill.py`

The batch runner stops and tells you to run `01_login_save_state.py` if auth is missing.

## Outputs

- Fresh tracker: `tracker\HRP_Tracker.xlsx`
- Raw exported pages and screenshots: `inputs\export\raw\<horse_id_or_name>\`
- Export manifest: `inputs\export\export_manifest.json`
- Import summary: `outputs\daily_reports\IMPORT_SUMMARY.md`

## Notes

- Exporter uses a 12-second delay between requests to avoid hammering.
- Parsing avoids guessing. Uncertain values are written to Notes/snippets.
- If the site layout changes, update keyword matching in `scripts\02_export_stable.py` and parsing rules in `scripts\04_parse_and_fill.py`.

## Run Unit Tests

```powershell
py -m unittest
```

## Windows PowerShell

Prefer no-activation workflows to avoid `Activate.ps1` ExecutionPolicy issues.

Recommended:

```powershell
.\scripts\bootstrap.ps1
.\scripts\run_tests.ps1
```

`bootstrap.ps1` will:
- create `.venv` if missing
- install/update pip + dependencies from `requirements.txt`
- install Playwright Chromium automatically
- run tests

Run Python directly from the venv path instead of activation:

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python .\tmp_check_counts.py
```

If you want activation, set policy once for your user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
