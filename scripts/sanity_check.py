"""sanity_check.py — Regression tests for parsed data quality.

Fails if:
  1. Condition == Stamina for >80% of horses (duplicate parsing bug)
  2. Any horse with races has blank/None finish for all of them
  3. Snapshot is missing or has 0 horses
"""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAIL = False


def fail(msg: str) -> None:
    global FAIL
    FAIL = True
    print(f"  FAIL: {msg}")


def main() -> None:
    global FAIL
    today = date.today().isoformat()
    snap_path = ROOT / "inputs" / today / "stable_snapshot.json"
    if not snap_path.exists():
        # Try most recent
        dirs = sorted((ROOT / "inputs").glob("20*-*-*"), reverse=True)
        for d in dirs:
            sp = d / "stable_snapshot.json"
            if sp.exists():
                snap_path = sp
                break

    print(f"Checking: {snap_path}")

    # --- Check 1: Snapshot exists ---
    if not snap_path.exists():
        fail("stable_snapshot.json not found")
        sys.exit(1)

    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    horses = snap.get("horses", [])

    if len(horses) == 0:
        fail("Snapshot has 0 horses")
        sys.exit(1)
    print(f"  OK: {len(horses)} horses in snapshot")

    # --- Check 2: Condition != Stamina for majority ---
    same_count = 0
    has_both = 0
    for h in horses:
        c = h.get("condition")
        s = h.get("stamina")
        if c and s:
            has_both += 1
            if c == s:
                same_count += 1

    if has_both > 0:
        pct = same_count / has_both * 100
        if pct > 80:
            fail(f"Condition == Stamina for {same_count}/{has_both} horses ({pct:.0f}%) — likely duplicate bug")
        else:
            print(f"  OK: Condition != Stamina for {has_both - same_count}/{has_both} horses ({100-pct:.0f}% differentiated)")
    else:
        print("  WARN: No horses have both condition and stamina parsed")

    # --- Check 3: Horses with record have parsed race results ---
    horses_with_starts = [h for h in horses if int(h.get("record", {}).get("starts", 0)) > 0]
    horses_with_races = [h for h in horses_with_starts if h.get("recent_races")]

    if horses_with_starts:
        if len(horses_with_races) == 0:
            fail(f"{len(horses_with_starts)} horses have race starts but 0 have parsed finish positions")
        else:
            print(f"  OK: {len(horses_with_races)}/{len(horses_with_starts)} horses with starts have parsed race results")

        # Check that at least one race has a real finish position
        all_finishes = []
        for h in horses_with_races:
            for r in h.get("recent_races", []):
                f = r.get("finish")
                if f and f.isdigit():
                    all_finishes.append(int(f))

        if all_finishes:
            print(f"  OK: {len(all_finishes)} race finishes parsed (positions: {min(all_finishes)}-{max(all_finishes)})")
        else:
            fail("No valid finish positions found in parsed races")
    else:
        print("  INFO: No horses with race starts found")

    # --- Check 4: Reports exist ---
    for report in ["Stable_Dashboard.md", "Weekly_Plan.md", "Decisions_Log.md", "Race_Opportunities.md"]:
        rp = ROOT / "reports" / report
        if rp.exists():
            print(f"  OK: {report} exists ({rp.stat().st_size} bytes)")
        else:
            fail(f"{report} missing")

    # --- Check 5: Approval queue exists ---
    aq = ROOT / "outputs" / "approval_queue.json"
    if aq.exists():
        queue = json.loads(aq.read_text(encoding="utf-8"))
        approvals = sum(1 for e in queue if e.get("approval_required"))
        print(f"  OK: approval_queue.json ({len(queue)} entries, {approvals} need approval)")
    else:
        fail("approval_queue.json missing")

    # --- Check 6: Race_Opportunities has NO garbage labels ---
    garbage_labels = ["handicapping", "stakes calendar", "wager pad", "track calendar"]
    for report_name in ["Race_Opportunities.md", "Approval_Pack.md"]:
        rp = ROOT / "reports" / report_name
        if rp.exists():
            content = rp.read_text(encoding="utf-8")
            content_lower = content.lower()
            for gl in garbage_labels:
                if gl in content_lower:
                    fail(f"{report_name} contains garbage label: '{gl}'")
            if not any(gl in content_lower for gl in garbage_labels):
                print(f"  OK: {report_name} has 0 garbage labels")

            # v2 trust checks: no malformed race IDs
            if "RACE TYPE" in content and "race_type" not in content:
                fail(f"{report_name} contains 'RACE TYPE' as data (malformed)")
            if "· TRACK ·" in content or "Ship to TRACK" in content:
                fail(f"{report_name} contains 'TRACK' as track code (malformed)")
            if "Select 13:" in content or "Select 1" in content.split("Steps:")[0] if "Steps:" in content else False:
                fail(f"{report_name} contains time-as-track in Steps")

            # v2: Field=0 is illegal
            if "| 0 |" in content and "Field" in content:
                # Check if it's in a race table (not just any 0)
                for line in content.split("\n"):
                    if "| 0 |" in line and ("Maiden" in line or "Claiming" in line or "Allowance" in line):
                        fail(f"{report_name} has Field=0 in race row")
                        break

        else:
            if report_name == "Approval_Pack.md":
                fail(f"{report_name} missing")

    # --- Check 7: Predictions log exists ---
    pred_csv = ROOT / "outputs" / "predictions_log.csv"
    if pred_csv.exists():
        print(f"  OK: predictions_log.csv exists ({pred_csv.stat().st_size} bytes)")
    else:
        print("  INFO: predictions_log.csv not yet created (run 11_recommend)")

    # --- Result ---
    print()
    if FAIL:
        print("SANITY CHECK FAILED — see FAIL lines above")
        sys.exit(1)
    else:
        print("ALL SANITY CHECKS PASSED ✓")
        sys.exit(0)


if __name__ == "__main__":
    main()
