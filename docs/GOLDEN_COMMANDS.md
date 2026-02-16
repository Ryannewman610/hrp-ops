# Golden Commands (PowerShell)

Important:

- Lines starting with `PS C:\...>` are prompts, not commands.
- Paste only the command text.

## Setup + test (no activation required)

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -U pip pytest
.\.venv\Scripts\python -m pytest -q
```

## Run local scripts

```powershell
py .\tmp_check_counts.py
py .\tmp_debug_races.py
```

## Repo helpers

```powershell
.\scripts\bootstrap.ps1
.\scripts\run_tests.ps1
.\scripts\run_py.ps1 -Args "-m pytest -q"
```
