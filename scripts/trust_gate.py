"""trust_gate.py — Hard fail if published reports contain broken tokens.

Exits with code 1 if ANY trust violation is found.
Must pass before any pipeline output is considered valid.

Checks:
  1. "RACE TYPE" as data (not header label)
  2. "TRACK ·" or "Ship to TRACK" (header leaking as track code)
  3. "Select HH:MM" (time used as track in approval steps)
  4. "Ship to HH:MM" (time used as track in risk text)
  5. "| 0 |" in race rows (Field=0 is illegal)
  6. Garbage nav labels as race targets
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

FAIL = False


def fail(msg: str) -> None:
    global FAIL
    FAIL = True
    print(f"  FAIL: {msg}")


def check_file(path: Path) -> None:
    if not path.exists():
        print(f"  SKIP: {path.name} not found")
        return

    content = path.read_text(encoding="utf-8")
    name = path.name
    print(f"Checking {name}...")

    # 1. "RACE TYPE" as data (not in a header row or scheme description)
    # In clean reports, RACE TYPE should never appear as race identity data
    for i, line in enumerate(content.split("\n"), 1):
        if "RACE TYPE" in line and "|" in line:
            fail(f"{name}:L{i} — 'RACE TYPE' appears in table row: {line.strip()[:80]}")
        if "RACE TYPE" in line and "→" in line:
            fail(f"{name}:L{i} — 'RACE TYPE' in recommendation: {line.strip()[:80]}")

    # 2. "TRACK ·" or "Ship to TRACK" — header leaking as track code
    if "· TRACK ·" in content or "· TRACK " in content:
        fail(f"{name} — contains '· TRACK ·' (header as track code)")
    if "Ship to TRACK" in content:
        fail(f"{name} — contains 'Ship to TRACK'")

    # 3. "Select HH:MM" — time used as track in approval steps
    select_time = re.findall(r"Select\s+\d{1,2}:\d{2}", content)
    if select_time:
        fail(f"{name} — time used as track in steps: {select_time[:3]}")

    # 4. "Ship to HH:MM" — time as track in risk text
    ship_time = re.findall(r"Ship to \d{1,2}:\d{2}", content)
    if ship_time:
        fail(f"{name} — 'Ship to' uses time instead of track: {ship_time[:3]}")

    # 5. Field=0 in race rows (lines with race types + | 0 |)
    for i, line in enumerate(content.split("\n"), 1):
        if "| 0 |" in line:
            # Check it's a race row, not a header/separator
            low = line.lower()
            if any(kw in low for kw in ["maiden", "claiming", "allowance", "stakes",
                                        "handicap", "race #", "r#"]):
                fail(f"{name}:L{i} — Field=0 in race row: {line.strip()[:80]}")

    # 6. Garbage nav labels as race targets
    garbage = ["handicapping", "stakes calendar", "wager pad", "track calendar",
               "track condition", "weather", "no headlines"]
    content_lower = content.lower()
    for g in garbage:
        if g in content_lower:
            # Check it's not in the footer/meta section
            for i, line in enumerate(content.split("\n"), 1):
                if g in line.lower() and "|" in line:
                    fail(f"{name}:L{i} — garbage label '{g}' in data row")


def main() -> None:
    global FAIL
    print("=" * 50)
    print("  TRUST GATE — Output Integrity Check")
    print("=" * 50)

    check_file(REPORTS / "Race_Opportunities.md")
    check_file(REPORTS / "Approval_Pack.md")
    check_file(REPORTS / "Training_Plan.md")

    print()
    if FAIL:
        print("❌ TRUST GATE FAILED — see FAIL lines above")
        print("   Reports contain broken tokens. Do NOT proceed.")
        sys.exit(1)
    else:
        print("✅ TRUST GATE PASSED — all reports clean")
        sys.exit(0)


if __name__ == "__main__":
    main()
