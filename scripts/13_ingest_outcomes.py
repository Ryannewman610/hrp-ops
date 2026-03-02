"""13_ingest_outcomes.py — Parse race results with SRF speed figures.

Reads each horse's profile_allraces.html (exported by 02_export_stable.py),
extracts past-performance lines, parses SRF speed figures, finish positions,
jockey IDs, race class, surface, distance, and more.

Fresh PP format (after SRF purchase):
  Line 0:  7Feb26-11BTP           (date-raceNum-track)
  Line 1:  fst                     (surface)
  Line 2:  5f                      (distance)
  Lines 3-N: fractional times      (:22, 2, :45, etc.)
  Line N+1: 4+Clm5.00N2L          (race class)
  Line N+2: 88                     (SRF SPEED FIGURE)
  Line N+3: 5                      (post position)
  Lines: 1, hd, 2, hd, 4, 1       (running calls + finish)
  Line: Jockey 1526                (jockey ID)
  Line: B/L                        (blinkers/lasix)
  Line: 121                        (weight carried)
  Line: b/h                        (effort: breezing/handily)
  Line: *2.30                      (odds)
  Line: 95-3                       (condition-stamina at race time)
  Line: 9                          (field size)

Produces:
  - outputs/outcomes_log.csv (overwrite with clean data)
  - outputs/outcomes_log_{date}.json (daily snapshot)

SAFETY: Read-only. No form submissions.
"""

import csv
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "inputs" / "export" / "raw"
OUTPUTS = ROOT / "outputs"
INACTIVE = {"shebasbriar", "averyspluck", "hiptag793004736512"}

SURFACE_MAP = {
    "fst": ("Fast", "Dirt"), "gd": ("Good", "Dirt"),
    "sly": ("Sloppy", "Dirt"), "mdy": ("Muddy", "Dirt"),
    "fm": ("Firm", "Turf"), "yl": ("Yielding", "Turf"), "sft": ("Soft", "Turf"),
}

CLASS_RE = re.compile(
    r'^(?:f)?(?:Clm|OClm|Alw|MdSpWt|MdClm|Md|Stk|Stakes|HCap|EastVw|WestVw)'
    r'[A-Za-z0-9./()_-]*$',
    re.IGNORECASE
)


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_hrp_date(d: str) -> str:
    """Parse HRP date '14Feb26' to '2026-02-14'."""
    m = re.match(r"(\d{1,2})([A-Z][a-z]{2})(\d{2})", d.strip())
    if not m:
        return d
    day, mon, yr = m.groups()
    months = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
              "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
    mo = months.get(mon, "00")
    return f"20{yr}-{mo}-{day.zfill(2)}"


def extract_pp_races(text: str) -> List[Dict]:
    """Extract race results from HRP profile text with SRF figures."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    races = []

    # Find PP start lines: "19Feb26-6TUP" or "8Oct25-2MNR"
    pp_starts = []
    for i, line in enumerate(lines):
        m = re.match(r'^(\d{1,2}[A-Z][a-z]{2}\d{2})-(\d+)([A-Z]{2,5})$', line)
        if m:
            pp_starts.append((i, m.group(1), m.group(2), m.group(3)))

    for idx, (start_i, date_str, race_num, track) in enumerate(pp_starts):
        end_i = pp_starts[idx + 1][0] if idx + 1 < len(pp_starts) else min(start_i + 40, len(lines))
        block = lines[start_i + 1: end_i]
        if len(block) < 5:
            continue

        race: Dict[str, Any] = {
            "date": parse_hrp_date(date_str),
            "track": track,
            "race_num": race_num,
        }

        # Surface (first token)
        if block[0].lower() in SURFACE_MAP:
            race["surface"], race["surface_type"] = SURFACE_MAP[block[0].lower()]

        # Distance (second token)
        race["distance"] = block[1] if len(block) > 1 else ""

        # Find race class line
        class_idx = None
        for bi, bline in enumerate(block):
            if CLASS_RE.match(bline) or re.match(r'^(?:f)?(?:Clm|OClm|Alw|MdSpWt|Md)\d', bline):
                race["race_class"] = bline
                class_idx = bi
                break

        if class_idx is None:
            races.append(race)
            continue

        # After class: SRF, PP, running calls, finish, jockey, weight, odds, cond-stam, field
        after = block[class_idx + 1:]

        # SRF = first token after class (2-3 digit number, or '---' if unavailable)
        srf_raw = after[0] if after else ""
        if re.match(r'^\d{2,3}$', srf_raw):
            srf_val = int(srf_raw)
            if 50 <= srf_val <= 120:
                race["srf"] = srf_val
        elif srf_raw == '---':
            race["srf"] = None  # No SRF available

        # Find jockey line (contains "Jockey")
        jockey_idx = None
        for ai, aline in enumerate(after):
            if aline.startswith("Jockey"):
                race["jockey"] = aline
                jockey_idx = ai
                break

        # Extract running line + finish between SRF and Jockey
        if jockey_idx is not None and jockey_idx > 1:
            running = after[1:jockey_idx]  # Between SRF and Jockey
            # First token = post position
            if running and re.match(r'^\d+$', running[0]):
                race["post_position"] = int(running[0])

            # Last numeric token before jockey = finish position
            for token in reversed(running):
                if re.match(r'^\d+$', token):
                    val = int(token)
                    if 1 <= val <= 20:
                        race["finish_position"] = val
                        break

            # After jockey: accessories, weight, effort, odds, cond-stam, field
            post_jockey = after[jockey_idx + 1:]
            for pj in post_jockey:
                # Weight (3-digit number, 100-140 range)
                if re.match(r'^\d{3}$', pj):
                    val = int(pj)
                    if 100 <= val <= 140:
                        race["weight"] = val
                # Odds (starts with * or is like "2.30")
                elif re.match(r'^\*?[\d.]+$', pj) and '.' in pj:
                    race["odds"] = pj.lstrip('*')
                # Condition-stamina (like "95-3" or "95-7")
                elif re.match(r'^\d{2,3}-\d{1,2}$', pj):
                    parts = pj.split('-')
                    race["race_condition"] = int(parts[0])
                    race["race_stamina"] = int(parts[1])
                # Field size (single 1-2 digit number at end)
                elif re.match(r'^\d{1,2}$', pj):
                    val = int(pj)
                    if 2 <= val <= 16:
                        race["field_size"] = val

        # Check for claim info
        block_text = ' '.join(block)
        if 'Claimed' in block_text:
            claim_m = re.search(r'Claimed.*?\$(\d+(?:\.\d+)?)', block_text)
            if claim_m:
                race["claimed_for"] = float(claim_m.group(1))

        races.append(race)

    return races


def ingest_from_profiles() -> List[Dict]:
    """Parse race results from each horse's profile_allraces.html."""
    all_outcomes = []
    horse_dirs = sorted([d for d in EXPORT_DIR.iterdir()
                         if d.is_dir() and d.name != "_global"])

    for hdir in horse_dirs:
        horse_name = hdir.name.replace("_", " ").title()
        if norm(horse_name) in INACTIVE:
            continue

        races_file = hdir / "profile_allraces.html"
        if not races_file.exists():
            continue

        soup = BeautifulSoup(
            races_file.read_text(encoding="utf-8", errors="replace"),
            "html.parser"
        )
        text = soup.get_text('\n', strip=True)

        # Extract LIFE record
        life_m = re.search(r'LIFE\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+(\d+)', text)
        life_best_srf = ""
        if life_m:
            life_best_srf = life_m.group(6)

        races = extract_pp_races(text)
        for race in races:
            race["horse_name"] = horse_name
            race["source"] = "profile"
            race["life_best_srf"] = life_best_srf
        all_outcomes.extend(races)

    return all_outcomes


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    print("=" * 60)
    print("RACE OUTCOME INGEST WITH SRF SPEED FIGURES v2")
    print("=" * 60)

    profile_outcomes = ingest_from_profiles()

    print(f"  Profiles:  {len(profile_outcomes)} race results")

    # Dedup
    seen = set()
    unique = []
    for o in profile_outcomes:
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
        print("  No SRF data found — export may still be running.")
        print("  Re-run after export completes.")

    print("\nDone.")


if __name__ == "__main__":
    main()
