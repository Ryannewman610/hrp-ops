# PowerShell Troubleshooting

## Most Common Paste Error

Do **not** paste transcript prompts like:

```powershell
PS C:\hrp-ops> py -m pytest -q
```

Only paste the command text **after** `>`, for example:

```powershell
py -m pytest -q
```

Why this breaks:

- In PowerShell, `PS` is an alias (`ps` -> `Get-Process`).
- If you paste `PS C:\...> ...`, PowerShell may try to run `ps` and treat the rest as arguments.
- This causes errors like:
  - `Get-Process : A positional parameter cannot be found that accepts argument 'py'.`

## Do Not Paste Output Lines

Do not paste pip/pytest output back into the terminal.  
Only run actual commands.

## Running Local Python Scripts

Use one of these forms:

```powershell
py .\tmp_check_counts.py
py .\tmp_debug_races.py
```

or with venv python directly:

```powershell
.\.venv\Scripts\python .\tmp_check_counts.py
```

## ExecutionPolicy and venv Activation

If activation is blocked (`Activate.ps1 cannot be loaded`), use one of these:

### Option A (recommended): no activation

Run python directly from the venv:

```powershell
.\.venv\Scripts\python -m pytest -q
```

### Option B: allow activation for your user

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Safe Helpers in This Repo

Use these scripts to avoid activation issues:

```powershell
.\scripts\bootstrap.ps1
.\scripts\run_tests.ps1
.\scripts\run_py.ps1 -Args "-m pytest -q"
```
