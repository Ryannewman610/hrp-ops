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

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "inputs" / "export" / "raw"
MODEL_DIR = ROOT / "outputs" / "model"

# Known inactive — skip these
INACTIVE = {"shebasbriar", "averyspluck", "hiptag793004736512"}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_hrp_date(d: str) -> Optional[str]:
    """Parse HRP date format '14Feb26' to ISO '2026-02-14'."""
    m = re.match(r"(\d{1,2})([A-Z][a-z]{2})(\d{2})", d.strip())
    if not m:
        return None
    day, mon, yr = m.groups()
    months = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
              "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
              "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
    mo = months.get(mon)
    if not mo:
        return None
    return f"20{yr}-{mo}-{int(day):02d}"


def parse_distance_furlongs(dist: str) -> Optional[float]:
    """Convert '5f', '6 1/2f', '1m', '1 1/16m' to furlongs."""
    dist = dist.strip().lower()
    m = re.match(r"(\d+)\s*(\d+/\d+)?\s*([fm])", dist)
    if not m:
        return None
    whole = int(m.group(1))
    frac = 0.0
    if m.group(2):
        num, den = m.group(2).split("/")
        frac = int(num) / int(den)
    val = whole + frac
    if m.group(3) == "m":
        val *= 8
    return round(val, 2)


# ── Profile Page Parsing ────────────────────────────────────

def parse_profile_races(html_path: Path, horse_name: str) -> List[Dict]:
    """Extract race results from profile_allraces.html."""
    if not html_path.exists():
        return []
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    races: List[Dict] = []
    record = {"starts": 0, "wins": 0, "places": 0, "shows": 0}

    # Find LIFE record
    for i, line in enumerate(lines):
        if line == "LIFE":
            # Next lines should be starts/wins/places/shows
            for j in range(i + 1, min(i + 20, len(lines))):
                nums = re.findall(r"\d+", lines[j])
                if len(nums) >= 4:
                    record = {"starts": int(nums[0]), "wins": int(nums[1]),
                              "places": int(nums[2]), "shows": int(nums[3])}
                    break
            break

    # Parse individual race lines
    # Pattern: date+track on one line, then distance+surface+time, then position/field
    i = 0
    while i < len(lines):
        # Match date pattern: 14Feb26
        date_match = re.match(r"(\d{1,2}[A-Z][a-z]{2}\d{2})[\s\-]+(\S+)", lines[i])
        if date_match:
            race_date = parse_hrp_date(date_match.group(1))
            track = date_match.group(2).replace("\xa0", " ").strip()

            # Next line(s): distance surface time
            dist = ""
            surface = ""
            time_str = ""
            finish = ""
            field_size = ""

            for j in range(i + 1, min(i + 5, len(lines))):
                line = lines[j]
                # Distance pattern: 5f, 6 1/2f, 1m etc.
                dist_m = re.match(r"(\d+\s*\d*/?\d*\s*[fm])\s+(fst|gd|sly|my|yl|turf|dirt)\s*([\d:.]+)?", line, re.I)
                if dist_m:
                    dist = dist_m.group(1).strip()
                    surface = dist_m.group(2).strip()
                    if dist_m.group(3):
                        time_str = dist_m.group(3).strip()
                    continue

                # Finish position: digit/digit
                fin_m = re.match(r"(\d+)/(\d+)", line)
                if fin_m:
                    finish = fin_m.group(1)
                    field_size = fin_m.group(2)
                    break

            if race_date:
                race = {
                    "horse_name": horse_name,
                    "date": race_date,
                    "track": track,
                    "distance": dist,
                    "distance_f": parse_distance_furlongs(dist) if dist else None,
                    "surface": surface,
                    "time": time_str,
                    "finish": finish,
                    "field_size": field_size,
                }
                races.append(race)

        i += 1

    return races


def parse_profile_record(html_path: Path) -> Dict:
    """Extract LIFE record from profile page."""
    if not html_path.exists():
        return {"starts": 0, "wins": 0, "places": 0, "shows": 0}
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for i, line in enumerate(lines):
        if line == "LIFE":
            for j in range(i + 1, min(i + 20, len(lines))):
                nums = re.findall(r"\d+", lines[j])
                if len(nums) >= 4:
                    return {"starts": int(nums[0]), "wins": int(nums[1]),
                            "places": int(nums[2]), "shows": int(nums[3])}
    return {"starts": 0, "wins": 0, "places": 0, "shows": 0}


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
                # e.g.: sly / 5f / :25 / :51 / 2 / 1:06
                # or combined: 5f fst 1:00
                for j in range(i + 1, min(i + 12, len(lines))):
                    wline = lines[j].strip()
                    # If we hit another date pattern, stop
                    if re.match(r"\d{1,2}[A-Z][a-z]{2}\d{2}", wline):
                        break
                    # If we hit a new section (like a horse name or "Works:"), stop
                    if wline.lower() == "works:":
                        break

                    # Combined distance line: 5f fst 1:00
                    dist_m = re.match(r"(\d+\s*\d*/?\d*\s*[fm])\s+(\w+)\s+([\d:.]+)", wline)
                    if dist_m:
                        dist = dist_m.group(1).strip()
                        surface = dist_m.group(2).strip()
                        time_str = dist_m.group(3).strip()
                        continue

                    # Surface only: fst, gd, sly, my, yl, fm (for turf 'firm')
                    if re.match(r"^(fst|gd|sly|my|yl|fm|sy|wf|sf)$", wline, re.I):
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
                    # Fractional time: :25, :51 (quarter/half splits) — skip these
                    if re.match(r"^:\d{2}(\.\d+)?$", wline):
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
