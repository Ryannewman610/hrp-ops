"""00_env_check.py — Verify HRP-ops environment is ready to run."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ok = True


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok
    status = "OK" if passed else "FAIL"
    msg = f"[{status}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not passed:
        ok = False


# Python
check("Python", True, f"{sys.executable} ({sys.version.split()[0]})")

# Key packages
for pkg in ("openpyxl", "bs4", "playwright"):
    try:
        __import__(pkg)
        check(f"import {pkg}", True)
    except ImportError:
        check(f"import {pkg}", False, "pip install -r requirements.txt")

# Playwright Chromium binary
try:
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    browser.close()
    pw.stop()
    check("Chromium binary", True)
except Exception as e:
    check("Chromium binary", False, f"{e}  →  python -m playwright install chromium")

# Auth file
auth_path = ROOT / "inputs" / "export" / "auth.json"
check("auth.json exists", auth_path.exists(), str(auth_path))

# Tracker
tracker_path = ROOT / "tracker" / "HRP_Tracker.xlsx"
check("HRP_Tracker.xlsx exists", tracker_path.exists(), str(tracker_path))

print()
if ok:
    print("Environment is ready. ✓")
    sys.exit(0)
else:
    print("Some checks failed. Fix the items marked FAIL above.")
    sys.exit(1)
