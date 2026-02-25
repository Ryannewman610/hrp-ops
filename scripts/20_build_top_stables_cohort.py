"""20_build_top_stables_cohort.py — Build cohort of top stables from results + stakes.

Parses sitewide race results and stakes entries to identify competitive stables.
Output: outputs/sitewide/top_stables.json

Metrics:
  - total_wins, total_starts, win_pct
  - total_top3, top3_pct
  - stakes_entries (from stakes calendar)
  - earnings proxy (win count × purse level)

SAFETY: Read-only. Parses already-exported HTML only.
"""

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
GLOBAL_DIR = ROOT / "inputs" / "export" / "raw" / "_global"
OUTPUTS = ROOT / "outputs" / "sitewide"


def parse_results_stables() -> Dict[str, Dict]:
    """Parse results.html to extract stable performance data."""
    rp = GLOBAL_DIR / "results.html"
    if not rp.exists():
        print("  WARN: results.html not found")
        return {}

    soup = BeautifulSoup(rp.read_text(encoding="utf-8", errors="replace"), "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    stables: Dict[str, Dict] = defaultdict(lambda: {
        "wins": 0, "top3": 0, "starts": 0, "races_entered": [],
        "tracks": set(), "surfaces": set(), "distances": set(),
        "horses": set(), "purse_total": 0.0,
    })

    current_race: Dict[str, Any] = {}
    in_race = False
    position = 0
    expect_horse = False
    expect_owner = False
    last_horse = ""

    i = 0
    while i < len(lines):
        line = lines[i]

        # Race header: "Race #N HH:MM"
        race_m = re.match(r"Race #(\d+)\s+(\d{1,2}:\d{2})", line)
        if race_m:
            current_race = {"race_num": race_m.group(1), "time": race_m.group(2)}
            # Next line has distance/surface/conditions
            if i + 1 < len(lines):
                desc = lines[i + 1]
                current_race["description"] = desc
                # Parse distance
                dist_m = re.match(r"([\d\s/]+(?:Furlongs?|Mile))", desc, re.I)
                if dist_m:
                    current_race["distance"] = dist_m.group(1).strip()
                # Parse surface
                if "Dirt" in desc:
                    current_race["surface"] = "Dirt"
                elif "Turf" in desc:
                    current_race["surface"] = "Turf"
                # Parse purse
                purse_m = re.search(r"Purse \$([\d,.]+)", desc)
                if purse_m:
                    current_race["purse"] = float(purse_m.group(1).replace(",", ""))
                # Parse class
                if "Maiden" in desc:
                    current_race["class"] = "Maiden"
                elif "Claiming" in desc:
                    current_race["class"] = "Claiming"
                elif "Allowance" in desc:
                    current_race["class"] = "Allowance"
                elif "Stakes" in desc or "Handicap" in desc:
                    current_race["class"] = "Stakes"
                else:
                    current_race["class"] = "Other"
            in_race = True
            position = 0
            i += 2
            continue

        if in_race:
            # Headers: ##, Horse Name, Owner Name, Jockey, Wt, Amt Won, Time, Cl
            if line == "##":
                i += 1
                continue
            if line in ("Horse Name", "Owner Name", "Jockey", "Wt", "Amt Won", "Time", "Cl"):
                i += 1
                continue

            # Position number (1-10+)
            if re.match(r"^\d{1,2}$", line) and int(line) <= 20:
                pos = int(line)
                if pos > position:
                    position = pos
                    expect_horse = True
                    i += 1
                    continue

            # Horse name (after position)
            if expect_horse:
                last_horse = line
                expect_horse = False
                expect_owner = True
                i += 1
                continue

            # Owner/stable name (after horse name)
            if expect_owner:
                stable_name = line
                expect_owner = False
                purse = current_race.get("purse", 0)

                # Skip non-stable text
                if stable_name.startswith("Jockey") or stable_name.startswith("Race #"):
                    i += 1
                    continue

                s = stables[stable_name]
                s["starts"] += 1
                s["horses"].add(last_horse)
                if position == 1:
                    s["wins"] += 1
                    s["purse_total"] += purse
                if position <= 3:
                    s["top3"] += 1
                if current_race.get("surface"):
                    s["surfaces"].add(current_race["surface"])
                if current_race.get("distance"):
                    s["distances"].add(current_race["distance"])

                i += 1
                continue

        i += 1

    return stables


def parse_stakes_entries() -> Dict[str, int]:
    """Parse stakes_calendar.html for stakes entry counts per stable."""
    sp = GLOBAL_DIR / "stakes_calendar.html"
    if not sp.exists():
        return {}

    soup = BeautifulSoup(sp.read_text(encoding="utf-8", errors="replace"), "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Count stakes entries — extract entries/field from "N/12" patterns
    stakes_count: Dict[str, int] = defaultdict(int)

    # The stakes calendar has structured rows  
    # We can count stakes by looking at entries available
    i = 0
    while i < len(lines):
        # Look for date patterns followed by stake names
        date_m = re.match(r"(\d{1,2}/\d{1,2}/\d{4})", lines[i])
        if date_m and i + 2 < len(lines):
            stake_name = lines[i + 1]
            if not re.match(r"\d", stake_name):  # Not another date
                stakes_count["_total"] += 1
        i += 1

    return stakes_count


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    print("Building top stables cohort...")

    # Parse results
    stables = parse_results_stables()
    print(f"  Stables from results: {len(stables)}")

    # Filter out noise
    valid_stables = {}
    for name, data in stables.items():
        if data["starts"] < 1:
            continue
        # Clean up sets for JSON
        s = dict(data)
        s["horses"] = sorted(data["horses"])
        s["surfaces"] = sorted(data["surfaces"])
        s["distances"] = sorted(data["distances"])
        s["horse_count"] = len(data["horses"])
        s["win_pct"] = round(data["wins"] / data["starts"] * 100, 1) if data["starts"] > 0 else 0
        s["top3_pct"] = round(data["top3"] / data["starts"] * 100, 1) if data["starts"] > 0 else 0
        s["purse_total"] = round(data["purse_total"], 2)
        del s["races_entered"]
        valid_stables[name] = s

    # Rank stables
    ranked = sorted(valid_stables.items(), key=lambda x: (
        -x[1]["wins"], -x[1]["top3"], -x[1]["starts"]
    ))

    # Build cohort with labels
    cohort = []
    top_by_wins = set(n for n, _ in ranked[:50])
    top_by_starts = set(n for n, _ in sorted(valid_stables.items(),
                                              key=lambda x: -x[1]["starts"])[:50])
    top_by_winpct = set(n for n, s in valid_stables.items()
                        if s["starts"] >= 2 and s["win_pct"] >= 20)

    for i, (name, data) in enumerate(ranked):
        labels = []
        if name in top_by_wins:
            labels.append("TopWins")
        if name in top_by_starts:
            labels.append("TopStarts")
        if name in top_by_winpct:
            labels.append("HighWinPct")

        cohort.append({
            "rank": i + 1,
            "stable_name": name,
            "cohort_labels": labels,
            **data,
        })

    # Save output
    output = {
        "generated": today,
        "source": "results.html",
        "total_stables": len(cohort),
        "top_50_by_wins": len(top_by_wins),
        "stables": cohort,
    }

    out_path = OUTPUTS / "top_stables.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ntop_stables.json: {len(cohort)} stables")

    # Summary
    print(f"\nTop 10 stables by wins:")
    for s in cohort[:10]:
        print(f"  {s['rank']:3d}. {s['stable_name']:30s} "
              f"W={s['wins']:2d} T3={s['top3']:2d} S={s['starts']:2d} "
              f"Win%={s['win_pct']:5.1f} Horses={s['horse_count']}")


if __name__ == "__main__":
    main()
