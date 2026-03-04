"""09_build_model_dataset.py — Build training datasets from horse profile data.

Outputs:
  - outputs/model/dataset_races.csv (1 row per race start)
  - outputs/model/dataset_works.csv (1 row per timed work)
"""

import csv
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

# Import shared parser (single source of truth for PP parsing)
from hrp_parser import (
    norm,
    parse_hrp_date,
    parse_distance_furlongs,
    parse_profile_html,
)

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "inputs" / "export" / "raw"
MODEL_DIR = ROOT / "outputs" / "model"

# Known inactive — skip these
INACTIVE = {"shebasbriar", "averyspluck", "hiptag793004736512"}


def parse_profile_races(html_path: Path, horse_name: str) -> List[Dict]:
    """Extract race results using the shared hrp_parser module."""
    result = parse_profile_html(html_path, horse_name)
    races = result.get("races", [])
    # Map field names to match dataset expectations
    for r in races:
        # hrp_parser uses 'finish_position'; dataset expects 'finish'
        if "finish_position" in r:
            r["finish"] = str(r["finish_position"])
        # hrp_parser uses 'srf' as int or None; keep as-is
        if "srf" in r and r["srf"] is not None:
            r["srf"] = r["srf"]
    return races


def parse_profile_record(html_path: Path) -> Dict:
    """Extract LIFE record using the shared hrp_parser module."""
    if not html_path.exists():
        return {"starts": 0, "wins": 0, "places": 0, "shows": 0}
    result = parse_profile_html(html_path, "")
    life = result.get("life_record", {})
    return {
        "starts": life.get("starts", 0),
        "wins": life.get("wins", 0),
        "places": life.get("places", 0),
        "shows": life.get("shows", 0),
    }


# ── Works Parsing ────────────────────────────────────────

def parse_works(html_path: Path, horse_name: str) -> List[Dict]:
    """Extract timed works from works_all.html."""
    if not html_path.exists():
        return []
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    works: List[Dict] = []
    found_works_section = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # Find "Works:" section marker
        if line.lower().startswith("works"):
            found_works_section = True
            i += 1
            continue

        if found_works_section:
            # Stop at section boundaries
            if line.lower().startswith("races:") or line.lower().startswith("nominations"):
                found_works_section = False
                i += 1
                continue

            # Work pattern: 14Feb26-MouWV or 14Feb26 MouWV
            date_match = re.match(r"(\d{1,2}[A-Z][a-z]{2}\d{2})[\s\-]+(\S+)", line)
            if date_match:
                work_date = parse_hrp_date(date_match.group(1))
                track = date_match.group(2).replace("\xa0", " ").strip()

                dist = ""
                surface = ""
                time_str = ""
                rank = ""
                work_type = ""

                # HRP works format: separate lines for surface, distance, fractional times, rank, final time
                # 5f+: :24 / :49 / 1:02 (M:SS final time)
                # 4f:  :24 / :50 (last colon-prefixed value IS final time)
                # 3f:  :36 (single colon-prefixed value IS final time)
                # Sub-1-min 5f: :24 / :47 / :59 (no M:SS — :59 IS the final)
                last_split = ""  # Track last colon-prefixed time
                for j in range(i + 1, min(i + 12, len(lines))):
                    wline = lines[j].strip()
                    # If we hit another date pattern, stop
                    if re.match(r"\d{1,2}[A-Z][a-z]{2}\d{2}", wline):
                        break
                    # If we hit a new section, stop
                    if wline.lower() in ("works:", "races:", "nominations"):
                        break

                    # Combined distance line: "5f fst 1:00" or "5f fst :59"
                    # Must NOT match "7f fst  5/6" (race result format)
                    dist_m = re.match(r"(\d+\s*\d*/?\d*\s*[fm])\s+(\w+)\s+(:?\d+:\d{2}(?:\.\d+)?|:\d{2}(?:\.\d+)?)$", wline)
                    if dist_m:
                        dist = dist_m.group(1).strip()
                        surface = dist_m.group(2).strip()
                        raw_time = dist_m.group(3).strip()
                        if raw_time.startswith(":"):
                            time_str = "0" + raw_time  # :59 → 0:59
                        else:
                            time_str = raw_time
                        continue

                    # Surface only: fst, gd, sly, my, yl, fm (for turf 'firm')
                    if re.match(r"^(fst|gd|sly|my|yl|fm|sy|wf|sf|mdy)$", wline, re.I):
                        surface = wline
                        continue
                    # Distance only: 3f, 4f, 5f, 6f, 7f, 1m, etc.
                    if re.match(r"^\d+\s*\d*/?\d*\s*[fm]$", wline, re.I):
                        dist = wline
                        continue
                    # Full time (with minutes): 1:06, 1:12.4, etc.
                    if re.match(r"^\d+:\d{2}(\.\d+)?$", wline):
                        time_str = wline  # Keep overwriting; last full time is final time
                        continue
                    # Fractional/split time: :24, :49, :50 — track last one
                    if re.match(r"^:\d{2}(\.\d+)?$", wline):
                        last_split = wline
                        continue
                    # Rank: 1-3 digit number
                    if re.match(r"^\d{1,3}$", wline):
                        rank = wline
                        continue
                    # Type: single letter (b=breeze, h=handily, etc.)
                    if re.match(r"^[a-zA-Z]$", wline):
                        work_type = wline
                        continue
                    # Percentage like 80% — likely a meter reading, skip
                    if re.match(r"^\d+%$", wline):
                        continue
                    # 'T' for turf indicator
                    if wline == "T":
                        surface = "fm"  # turf = firm
                        continue

                # If no M:SS final time, use last split — with plausibility check
                # last_split is ":SS" format. For it to be a final time:
                #   3f: ~34-42s, 4f: ~46-58s, 5f: ~58-59s (rare sub-1-min)
                # Any value < 20 is definitely a split, not a final time
                if not time_str and last_split:
                    split_secs = int(last_split[1:3])  # ":50" → 50
                    if split_secs >= 30:
                        # Plausible final time for any distance
                        time_str = "0" + last_split  # :50 → 0:50

                if work_date:
                    works.append({
                        "horse_name": horse_name,
                        "date": work_date,
                        "track": track,
                        "distance": dist,
                        "distance_f": parse_distance_furlongs(dist) if dist else None,
                        "surface": surface,
                        "time": time_str,
                        "rank": rank,
                        "work_type": work_type,
                    })
        i += 1

    return works


# ── Meters Parsing ────────────────────────────────────────

def parse_meters(html_path: Path) -> Dict:
    """Extract meter readings from meters.html."""
    if not html_path.exists():
        return {}
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    meters: Dict[str, str] = {}
    for i, line in enumerate(lines):
        if line.lower().startswith("condition") and i + 1 < len(lines):
            m = re.search(r"(\d+)%", lines[i + 1] if "%" not in line else line)
            if m:
                meters["condition"] = m.group(1)
        elif line.lower().startswith("stamina") and i + 1 < len(lines):
            m = re.search(r"(\d+)%", lines[i + 1] if "%" not in line else line)
            if m:
                meters["stamina"] = m.group(1)
        elif line.lower().startswith("consistency"):
            # Consistency might be on same line or next
            for j in range(i, min(i + 3, len(lines))):
                m = re.search(r"(\d+)", lines[j])
                if m and lines[j] != line:
                    meters["consistency"] = m.group(1)
                    break

    return meters


# ── Main Pipeline ────────────────────────────────────────

def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Load snapshot for supplementary data
    snap_path = ROOT / "inputs" / date.today().isoformat() / "stable_snapshot.json"
    if not snap_path.exists():
        dirs = sorted((ROOT / "inputs").glob("20*-*-*"), reverse=True)
        for d in dirs:
            sp = d / "stable_snapshot.json"
            if sp.exists():
                snap_path = sp
                break

    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    snap_by_norm = {norm(h["name"]): h for h in snap.get("horses", [])}

    # Process all horse directories
    all_races: List[Dict] = []
    all_works: List[Dict] = []

    horse_dirs = sorted(d for d in RAW_ROOT.iterdir()
                        if d.is_dir() and d.name != "_global"
                        and norm(d.name.replace("_", " ")) not in INACTIVE)

    print(f"Processing {len(horse_dirs)} horse directories...")

    for hdir in horse_dirs:
        horse_name = hdir.name.replace("_", " ")
        h_norm = norm(horse_name)

        # Get snapshot data for this horse
        snap_h = snap_by_norm.get(h_norm, {})

        # Parse profile races
        profile_path = hdir / "profile_allraces.html"
        races = parse_profile_races(profile_path, horse_name)

        # Parse record
        record = parse_profile_record(profile_path)

        # Parse works
        works_path = hdir / "works_all.html"
        works = parse_works(works_path, horse_name)

        # Parse meters
        meters_path = hdir / "meters.html"
        meters = parse_meters(meters_path)

        # Enrich race rows with snapshot + meter data
        for r in races:
            r["stamina"] = meters.get("stamina", snap_h.get("stamina", "").replace("%", ""))
            r["condition"] = meters.get("condition", snap_h.get("condition", "").replace("%", ""))
            r["consistency"] = meters.get("consistency", snap_h.get("consistency", ""))
            r["lifetime_starts"] = record.get("starts", 0)
            r["lifetime_wins"] = record.get("wins", 0)
            r["lifetime_places"] = record.get("places", 0)
            r["lifetime_shows"] = record.get("shows", 0)
            r["works_count"] = len(works)
            # Compute days since last work before this race
            race_date = r.get("date", "")
            works_before = [w for w in works if w.get("date", "") < race_date] if race_date else []
            if works_before:
                last_work = max(works_before, key=lambda w: w["date"])
                try:
                    rd = datetime.strptime(race_date, "%Y-%m-%d")
                    wd = datetime.strptime(last_work["date"], "%Y-%m-%d")
                    r["days_since_last_work"] = (rd - wd).days
                except ValueError:
                    r["days_since_last_work"] = ""
            else:
                r["days_since_last_work"] = ""

            # Win/top3 labels
            if r.get("finish") and r["finish"].isdigit():
                fin = int(r["finish"])
                r["win"] = 1 if fin == 1 else 0
                r["top3"] = 1 if fin <= 3 else 0
            else:
                r["win"] = ""
                r["top3"] = ""

        all_races.extend(races)

        # Enrich work rows
        for w in works:
            w["stamina"] = meters.get("stamina", "")
            w["condition"] = meters.get("condition", "")
            w["consistency"] = meters.get("consistency", "")

        all_works.extend(works)

        n_races = len(races)
        n_works = len(works)
        if n_races or n_works:
            print(f"  {horse_name}: {n_races} races, {n_works} works")

    # Write race CSV
    race_cols = ["horse_name", "date", "track", "distance", "distance_f", "surface",
                 "time", "finish", "field_size", "win", "top3",
                 "stamina", "condition", "consistency",
                 "lifetime_starts", "lifetime_wins", "lifetime_places", "lifetime_shows",
                 "works_count", "days_since_last_work"]
    race_path = MODEL_DIR / "dataset_races.csv"
    with open(race_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=race_cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_races)
    print(f"\ndataset_races.csv: {len(all_races)} rows")

    # Write works CSV
    work_cols = ["horse_name", "date", "track", "distance", "distance_f", "surface",
                 "time", "rank", "work_type",
                 "stamina", "condition", "consistency"]
    work_path = MODEL_DIR / "dataset_works.csv"
    with open(work_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=work_cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_works)
    print(f"dataset_works.csv: {len(all_works)} rows")


if __name__ == "__main__":
    main()
