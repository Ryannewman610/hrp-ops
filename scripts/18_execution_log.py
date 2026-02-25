"""18_execution_log.py — Parse Approval_Pack checkboxes, track execution.

Reads reports/Approval_Pack.md for [x] approved vs [ ] not-approved items.
Writes outputs/execution_log.csv (append-only) and daily JSON.

Schema:
  date, horse, action_type (race/work/rest), target_race_id,
  approved (yes/no), executed (pending), result (pending)
"""

import csv
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"


def parse_approval_pack() -> List[Dict]:
    """Parse Approval_Pack.md checkboxes."""
    ap = REPORTS / "Approval_Pack.md"
    if not ap.exists():
        print("  No Approval_Pack.md found")
        return []

    content = ap.read_text(encoding="utf-8")
    lines = content.split("\n")
    entries = []
    current_section = ""

    for line in lines:
        # Section headers
        if "## ✅ Already Nominated" in line:
            current_section = "review"
        elif "## 🎯 Recommended Entries" in line:
            current_section = "race"
        elif "## 🏋️ Training / Rest" in line:
            current_section = "training"

        # Parse checkbox lines
        m = re.match(r"^- \[([ xX])\] \*\*(.+?)\*\*(.*)$", line.strip())
        if m:
            checked = m.group(1).lower() == "x"
            horse = m.group(2).strip()
            rest_text = m.group(3).strip()

            entry: Dict[str, Any] = {
                "date": date.today().isoformat(),
                "horse": horse,
                "approved": "yes" if checked else "no",
                "executed": "pending",
                "result": "pending",
            }

            if current_section == "race":
                entry["action_type"] = "race"
                # Extract track and race info from "→ DATE TRACK R#N ..."
                race_m = re.search(r"→\s*(.+?)$", rest_text)
                if race_m:
                    entry["target_info"] = race_m.group(1).strip()
            elif current_section == "review":
                entry["action_type"] = "review"
            elif current_section == "training":
                if "Rest" in rest_text:
                    entry["action_type"] = "rest"
                else:
                    entry["action_type"] = "work"
                entry["approved"] = "yes"  # Training items auto-approved

            entries.append(entry)

    return entries


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    entries = parse_approval_pack()
    print(f"Parsed {len(entries)} items from Approval_Pack.md")

    if not entries:
        return

    approved = sum(1 for e in entries if e["approved"] == "yes")
    print(f"  Approved: {approved}, Not approved: {len(entries) - approved}")

    # Save daily JSON
    json_path = OUTPUTS / f"execution_log_{today}.json"
    json_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"execution_log_{today}.json: {len(entries)} entries")

    # Append to CSV
    csv_path = OUTPUTS / "execution_log.csv"
    csv_exists = csv_path.exists()
    fieldnames = ["date", "horse", "action_type", "target_info", "approved", "executed", "result"]
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not csv_exists:
            writer.writeheader()
        for e in entries:
            writer.writerow(e)
    print(f"execution_log.csv: appended {len(entries)} rows")


if __name__ == "__main__":
    main()
