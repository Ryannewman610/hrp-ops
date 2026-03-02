"""13_ingest_outcomes.py — Parse race results with SRF speed figures.

Uses the shared hrp_parser module to extract past-performance data
from each horse's profile_allraces.html.

Produces:
  - outputs/outcomes_log.csv
  - outputs/outcomes_log_{date}.json

SAFETY: Read-only. No form submissions.
"""

import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

# Import shared parser
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hrp_parser import norm, parse_profile_html

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "inputs" / "export" / "raw"
OUTPUTS = ROOT / "outputs"
INACTIVE = {"shebasbriar", "averyspluck", "hiptag793004736512"}


def ingest_from_profiles():
    """Parse race results from each horse's profile_allraces.html."""
    all_outcomes = []
    horse_dirs = sorted([d for d in EXPORT_DIR.iterdir()
                         if d.is_dir() and d.name != "_global"])

    for hdir in horse_dirs:
        horse_name = hdir.name.replace("_", " ").title()
        if norm(horse_name) in INACTIVE:
            continue

        profile = parse_profile_html(hdir / "profile_allraces.html", horse_name)
        for race in profile["races"]:
            race["source"] = "profile"
            race["life_best_srf"] = profile.get("best_srf", "")
        all_outcomes.extend(profile["races"])

    return all_outcomes


def main():
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    print("=" * 60)
    print("RACE OUTCOME INGEST WITH SRF SPEED FIGURES v3")
    print("=" * 60)

    outcomes = ingest_from_profiles()

    # Dedup
    seen = set()
    unique = []
    for o in outcomes:
        key = f"{norm(o.get('horse_name', ''))}_{o.get('date', '')}_{o.get('track', '')}_{o.get('race_num', '')}"
        if key not in seen:
            seen.add(key)
            unique.append(o)

    with_srf = sum(1 for o in unique if o.get("srf"))
    with_finish = sum(1 for o in unique if o.get("finish_position"))
    with_jockey = sum(1 for o in unique if o.get("jockey"))
    print(f"  Unique outcomes: {len(unique)}")
    print(f"  With SRF figures: {with_srf}")
    print(f"  With finish pos:  {with_finish}")
    print(f"  With jockey:      {with_jockey}")

    # Save JSON
    json_path = OUTPUTS / f"outcomes_log_{today}.json"
    json_path.write_text(json.dumps(unique, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write CSV
    csv_path = OUTPUTS / "outcomes_log.csv"
    fieldnames = [
        "horse_name", "date", "track", "race_num", "finish_position",
        "distance", "surface", "surface_type", "race_class",
        "srf", "life_best_srf", "jockey",
        "post_position", "weight", "odds", "field_size",
        "race_condition", "race_stamina",
        "claimed_for", "source",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for o in sorted(unique, key=lambda x: (x.get("horse_name", ""), x.get("date", ""))):
            writer.writerow(o)

    print(f"\n  outcomes_log.csv: {len(unique)} rows")

    # SRF Summary
    print("\n" + "=" * 60)
    print("SRF SPEED FIGURE SUMMARY BY HORSE")
    print("=" * 60)
    horse_srfs = defaultdict(list)
    for o in unique:
        if o.get("srf"):
            horse_srfs[o["horse_name"]].append(o["srf"])

    for horse in sorted(horse_srfs.keys()):
        srfs = horse_srfs[horse]
        avg = sum(srfs) / len(srfs)
        best = max(srfs)
        last = srfs[0]
        print(f"  {horse:25s}  Avg: {avg:5.1f}  Best: {best:3d}  Last: {last:3d}  ({len(srfs)} races)")

    if not horse_srfs:
        print("  No SRF data found — export may need re-running.")

    print("\nDone.")


if __name__ == "__main__":
    main()
