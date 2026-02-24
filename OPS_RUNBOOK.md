# 📖 HRP-Ops Runbook

> How to operate the HRP automation pipeline. Written for non-technical users.

---

## Quick Start

### First Time Setup
```
cd c:\hrp-ops
.venv\Scripts\python.exe scripts\00_env_check.py
```
If anything says `[FAIL]`, install missing packages:
```
.venv\Scripts\pip.exe install -r requirements.txt
python -m playwright install chromium
```

### Daily Run (~25 minutes)
```
scripts\RUN_DAILY.bat
```
This will:
1. ✅ Check environment
2. 🔑 Check auth (auto-launches login browser if expired)
3. 📥 Export stable roster + global pages + 3 key pages per horse
4. 📊 Parse HTML into HRP_Tracker.xlsx
5. 📈 Build snapshot + generate reports

### Weekly Run (~60 minutes)
```
scripts\RUN_WEEKLY.bat
```
Same as daily but exports **all 8 pages per horse** (includes pedigree, conformation, accessories, foals).

---

## What Gets Exported

### Daily Mode (3 pages/horse + globals)
| Page | Why |
|------|-----|
| profile_allraces | Race results, nominations, entries |
| works_all | Timed workout history |
| meters | Condition, stamina, consistency, distance |
| + Global pages | Race calendar, stakes, weather, account history |

### Weekly Mode (8 pages/horse + globals)
All of the above, plus:
| Page | Why |
|------|-----|
| profile_printable | Printable profile version |
| pedigree | Bloodline analysis |
| conformation | Body/leg/gait traits |
| accessories | Blinkers, bute, wraps |
| foals | Offspring data |

---

## Authentication

HRP sessions expire every **~20 minutes**. The pipeline handles this:

1. `00_auth_check.py` verifies your session before exporting
2. If expired, `RUN_DAILY.bat` auto-launches a browser for re-login
3. You log in manually, press Enter, and it saves the session
4. The session is stored at `inputs/export/auth.json` (never committed to git)

### Manual Login (if needed)
```
.venv\Scripts\python.exe scripts\01_login_save_state.py
```
This opens a browser → you log in → press Enter → session saved.

---

## Output Files

| File | Location | Updated |
|------|----------|---------|
| Raw HTML | `inputs/export/raw/{horse}/` | Each export run |
| Global HTML | `inputs/export/raw/_global/` | Each export run |
| Daily Snapshot | `inputs/YYYY-MM-DD/stable_snapshot.json` | Daily |
| Tracker | `tracker/HRP_Tracker.xlsx` | Each parse run |
| Dashboard | `reports/Stable_Dashboard.md` | Each report run |
| Weekly Plan | `reports/Weekly_Plan.md` | Each report run |
| Decisions Log | `reports/Decisions_Log.md` | Append-only |

---

## What Requires Manual Approval

> **⚠️ SAFETY RULE: The pipeline NEVER takes in-game actions.**

These actions must be done manually (or by an approved agent):

| Action | Risk | Where |
|--------|------|-------|
| Nominate for race | Spends credits | HRP → Stables → Nominate |
| Scratch from race | May lose nom fee | HRP → Horse → Nominations |
| Apply accessories | Changes horse | HRP → Horse → Accessories |
| Ship/Relocate | In-transit downtime | HRP → Horse → Relocate |
| Train/Work | Affects meters | HRP → Horse → Train |
| Buy/Sell/Claim | Ownership change | HRP → various |
| Breed | Permanent action | HRP → Stables → Breed |
| Retire | Permanent action | HRP → Horse → Retire |

---

## Troubleshooting

### "AUTH_EXPIRED" during export
The 20-min session timed out mid-export. Re-run:
```
.venv\Scripts\python.exe scripts\01_login_save_state.py
scripts\RUN_DAILY.bat
```

### "PARTIAL EXPORT" message
The export saved progress for the horses it completed. After re-login, running the export again will overwrite with fresh data.

### Tracker not updating
Make sure `tracker/HRP_Tracker.xlsx` exists:
```
.venv\Scripts\python.exe scripts\03_make_fresh_tracker.py
```

### Reports look stale
Re-run the snapshot + report scripts:
```
.venv\Scripts\python.exe scripts\05_build_stable_snapshot.py
.venv\Scripts\python.exe scripts\06_generate_reports.py
```

---

## Script Reference

| Script | Purpose | Auto-safe? |
|--------|---------|------------|
| `00_env_check.py` | Verify Python, packages, Chromium | ✅ Read-only |
| `00_auth_check.py` | Verify HRP session is valid | ✅ Read-only |
| `01_login_save_state.py` | Interactive login → save cookies | ✅ Manual login |
| `02_export_stable.py` | Download HTML from HRP | ✅ Read-only scraping |
| `03_make_fresh_tracker.py` | Create empty tracker from template | ✅ Local only |
| `04_parse_and_fill.py` | Parse HTML → populate tracker | ✅ Local only |
| `05_build_stable_snapshot.py` | Build JSON snapshot from HTML | ✅ Local only |
| `06_generate_reports.py` | Generate markdown reports | ✅ Local only |
| `RUN_DAILY.bat` | Full daily pipeline | ✅ Read-only |
| `RUN_WEEKLY.bat` | Full weekly pipeline | ✅ Read-only |

All scripts are **read-only** — they never modify your HRP account.
