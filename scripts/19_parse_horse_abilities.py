"""19_parse_horse_abilities.py — Extract per-horse ability profiles from meters.html.

Parses each horse's meters.html to extract:
  - Condition%, Stamina%, Consistency, Distance counter
  - Weight(lbs), Height(hands)
  - Race records by category: LIFE, WET, TURF, LONG with speed ratings
  - Bio: color, sex, age

Derives:
  - preferred_surface (Dirt/Turf based on speed ratings + record)
  - preferred_distance (Sprint/Route based on LONG record)
  - best_speed (highest LIFE speed)
  - wet_ability (WET speed vs LIFE speed)
  - turf_ability (TURF speed vs LIFE speed)
  - class_level (from race class in profile_printable)

Output: outputs/horse_abilities.json

SAFETY: Read-only. Parses already-exported HTML only.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "inputs" / "export" / "raw"
OUTPUTS = ROOT / "outputs"


def parse_meters(horse_dir: Path) -> Dict[str, Any]:
    """Parse meters.html for a single horse."""
    mf = horse_dir / "meters.html"
    if not mf.exists():
        return {}

    soup = BeautifulSoup(mf.read_text(encoding="utf-8", errors="replace"), "html.parser")
    text = soup.get_text("\n", strip=True)
    # Clean unicode artifacts
    text = text.replace("\xa0", " ").replace("á", " ")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    result: Dict[str, Any] = {}

    # --- Extract header stats ---
    # Pattern: "Condition:" followed by percentage on nearby line
    for i, line in enumerate(lines):
        if line.startswith("Condition:"):
            # Value may be on same line or next
            val = line.replace("Condition:", "").strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1]
            m = re.search(r"(\d+)%?", val)
            if m:
                result["condition"] = int(m.group(1))

        elif line.startswith("Stamina:"):
            val = line.replace("Stamina:", "").strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1]
            m = re.search(r"(\d+)%?", val)
            if m:
                result["stamina"] = int(m.group(1))

        elif line.startswith("Consistency:"):
            val = line.replace("Consistency:", "").strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1]
            m = re.search(r"([+-]?\d+)", val)
            if m:
                result["consistency"] = int(m.group(1))

        elif line.startswith("Distance:"):
            val = line.replace("Distance:", "").strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1]
            m = re.search(r"(\d+)", val)
            if m:
                result["distance_counter"] = int(m.group(1))

        elif line.startswith("Track:"):
            val = line.replace("Track:", "").strip()
            if not val and i + 1 < len(lines):
                val = lines[i + 1]
            result["current_track"] = val.split()[0] if val else ""

    # --- Extract bio line: "Bl. g. 7 (Feb) 16.1h 1276lbs Active" ---
    for line in lines:
        bio_m = re.match(
            r"(\w+\.?\s+\w+\.?)\s+(\d+)\s+\((\w+)\)\s+([\d.]+)h\s+(\d+)lbs\s+(\w+)",
            line
        )
        if bio_m:
            result["bio_code"] = bio_m.group(1)  # "Bl. g."
            result["age"] = int(bio_m.group(2))
            result["birth_month"] = bio_m.group(3)
            result["height"] = float(bio_m.group(4))
            result["weight"] = int(bio_m.group(5))
            result["status"] = bio_m.group(6)  # Active/Training

            # Parse sex from bio code
            code = bio_m.group(1).lower()
            if " g." in code or " g " in code:
                result["sex"] = "gelding"
            elif " c." in code or " c " in code:
                result["sex"] = "colt"
            elif " f." in code or " f " in code:
                result["sex"] = "filly"
            elif " m." in code or " m " in code:
                result["sex"] = "mare"
            elif " h." in code or " h " in code:
                result["sex"] = "horse"
            elif " r." in code or " r " in code:
                result["sex"] = "ridgling"
            break

    # --- Extract race records by category ---
    # Look for LIFE, year, WET, TURF, LONG sections
    # Format: category label, then: starts, wins, places, shows, earnings, speed
    categories = {}
    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for category markers
        cat = None
        if line == "LIFE":
            cat = "LIFE"
        elif line == "WET":
            cat = "WET"
        elif line == "TURF":
            cat = "TURF"
        elif line == "LONG":
            cat = "LONG"
        elif re.match(r"^(2025|2026|2024|2023|2022|2021|2020)$", line):
            cat = line  # Year

        if cat:
            # Attempt to read the record — next lines should be numbers
            nums = []
            j = i + 1
            while j < len(lines) and len(nums) < 6:
                nm = re.match(r"^[\d.]+$", lines[j])
                if nm:
                    nums.append(lines[j])
                    j += 1
                else:
                    break

            if len(nums) >= 5:
                try:
                    rec = {
                        "starts": int(nums[0]),
                        "wins": int(nums[1]),
                        "places": int(nums[2]),
                        "shows": int(nums[3]),
                        "earnings": float(nums[4]),
                    }
                    if len(nums) >= 6:
                        rec["speed"] = int(float(nums[5]))
                    categories[cat] = rec
                except (ValueError, IndexError):
                    pass
            i = j
            continue

        # Also try inline: check if LIFE is followed by numbers on nearby lines
        i += 1

    # Try harder: scan for the LIFE pattern where numbers follow sequentially
    if "LIFE" not in categories:
        for i, line in enumerate(lines):
            if line == "LIFE":
                nums = []
                for j in range(i - 6, i):  # Numbers may be BEFORE the label
                    if 0 <= j < len(lines) and re.match(r"^[\d.]+$", lines[j]):
                        nums.append(lines[j])
                if not nums:  # Or AFTER
                    for j in range(i + 1, min(i + 8, len(lines))):
                        if re.match(r"^[\d.]+$", lines[j]):
                            nums.append(lines[j])
                if len(nums) >= 5:
                    try:
                        categories["LIFE"] = {
                            "starts": int(nums[0]),
                            "wins": int(nums[1]),
                            "places": int(nums[2]),
                            "shows": int(nums[3]),
                            "earnings": float(nums[4]),
                            "speed": int(float(nums[5])) if len(nums) >= 6 else 0,
                        }
                    except (ValueError, IndexError):
                        pass

    result["records"] = categories

    # --- Parse full header compound line ---
    # Pattern: "Horse NameOwner: ...Condition:N%Stamina:N%Consistency:+N(N)Distance:N"
    for line in lines:
        hdr = re.search(
            r"Condition:\s*(\d+)%\s*Stamina:\s*(\d+)%\s*Consistency:\s*([+-]?\d+)\s*\((\d+)\)\s*Distance:\s*(\d+)",
            line
        )
        if hdr:
            result["condition"] = int(hdr.group(1))
            result["stamina"] = int(hdr.group(2))
            result["consistency"] = int(hdr.group(3))
            result["consistency_raw"] = int(hdr.group(4))
            result["distance_counter"] = int(hdr.group(5))
            break

    # --- Extract works and activity from event log (Audit Holes #2, #3) ---
    # Event log lines follow pattern: date, event_type, track, stats...
    # Format: lines[i-1]=date, lines[i]="Timed Work"/"Race", lines[i+1]=track
    # Event types: "Maintenance", "Timed Work", "Race", "Train-Hvy", "Train-Std", etc.
    work_count = 0
    race_count = 0
    work_tracks = []
    race_tracks = []
    activity_total = 0  # works + races
    last_work_by_track: Dict[str, str] = {}  # track -> most recent work date
    last_work_date = ""  # most recent work date overall

    for i, line in enumerate(lines):
        if line in ("Timed Work", "Race"):
            if line == "Timed Work":
                work_count += 1
            else:
                race_count += 1
            activity_total += 1

            # Extract date from line before event type
            event_date = ""
            if i - 1 >= 0:
                date_m = re.match(r"(\d{2}/\d{2}/\d{4})", lines[i - 1])
                if date_m:
                    event_date = date_m.group(1)

            # Extract track from line after event type
            track_clean = ""
            if i + 1 < len(lines):
                track_line = lines[i + 1]
                track_clean = re.sub(r"\s*\(.*\)", "", track_line)  # Remove (1/2) etc
                if not (track_clean and len(track_clean) <= 8 and re.match(r"^[A-Za-z]+", track_clean)):
                    track_clean = ""

            if line == "Timed Work":
                if track_clean:
                    work_tracks.append(track_clean)
                # Track most recent work date per track (for 90-day check)
                if event_date and track_clean:
                    if track_clean not in last_work_by_track or event_date > last_work_by_track[track_clean]:
                        last_work_by_track[track_clean] = event_date
                if event_date and (not last_work_date or event_date > last_work_date):
                    last_work_date = event_date
            else:
                if track_clean:
                    race_tracks.append(track_clean)

    result["work_count"] = work_count
    result["race_count"] = race_count
    result["activity_total"] = activity_total
    result["work_tracks"] = work_tracks
    result["race_tracks"] = race_tracks
    result["last_work_by_track"] = last_work_by_track
    result["last_work_date"] = last_work_date

    return result


def parse_profile_classes(horse_dir: Path) -> List[str]:
    """Parse profile_printable.html for race class history."""
    pf = horse_dir / "profile_printable.html"
    if not pf.exists():
        return []

    soup = BeautifulSoup(pf.read_text(encoding="utf-8", errors="replace"), "html.parser")
    text = soup.get_text("\n", strip=True).replace("\xa0", " ")

    classes = []
    # Look for race class codes: Msw, Mcl, Alw, OClm, Clm, Stakes, etc.
    for m in re.finditer(r"(Msw|Mcl|Alw|OClm|Clm|Stakes|Hcp|Whitmo|Pincay|PIDMil|AppMil|KnckGo)", text):
        cls = m.group(1)
        if cls in ("Msw", "Mcl"):
            classes.append("Maiden")
        elif cls in ("Alw",):
            classes.append("Allowance")
        elif cls in ("OClm", "Clm"):
            classes.append("Claiming")
        elif cls in ("Stakes", "Hcp", "Whitmo", "Pincay", "PIDMil", "AppMil", "KnckGo"):
            classes.append("Stakes")

    return classes


def derive_preferences(ability: Dict) -> Dict:
    """Derive preferred surface, distance, and ability summary."""
    records = ability.get("records", {})
    life = records.get("LIFE", {})
    turf = records.get("TURF", {})
    wet = records.get("WET", {})
    long_rec = records.get("LONG", {})

    life_speed = life.get("speed", 0)
    turf_speed = turf.get("speed", 0)
    wet_speed = wet.get("speed", 0)
    long_speed = long_rec.get("speed", 0)

    life_starts = life.get("starts", 0)
    turf_starts = turf.get("starts", 0)
    long_starts = long_rec.get("starts", 0)

    # Preferred surface
    # If turf speed is within 3 of life speed and has 3+ starts, turf is viable
    # If turf speed is higher, prefer turf
    if turf_starts >= 2 and turf_speed > 0:
        if turf_speed >= life_speed:
            pref_surface = "Turf"
        elif turf_speed >= life_speed - 3:
            pref_surface = "Both"
        else:
            pref_surface = "Dirt"
    else:
        pref_surface = "Dirt"  # Default if no turf data

    # Preferred distance
    # LONG = route races. If long_starts > 50% of life_starts, prefer route
    if life_starts > 0 and long_starts > 0:
        long_pct = long_starts / life_starts
        if long_pct >= 0.6:
            pref_distance = "Route"
        elif long_pct <= 0.3:
            pref_distance = "Sprint"
        else:
            pref_distance = "Both"
    elif life_starts == 0:
        pref_distance = "Unknown"
    else:
        pref_distance = "Sprint"  # No long races = likely sprinter

    # Wet ability rating (0-100 scale)
    if wet_speed > 0 and life_speed > 0:
        wet_ability = round(wet_speed / life_speed * 100)
    else:
        wet_ability = 50  # Unknown

    # Turf ability rating
    if turf_speed > 0 and life_speed > 0:
        turf_ability = round(turf_speed / life_speed * 100)
    else:
        turf_ability = 50  # Unknown

    # Class level from race history
    classes = ability.get("class_history", [])
    if not classes:
        class_level = "Unknown"
    elif "Stakes" in classes:
        class_level = "Stakes"
    elif "Allowance" in classes:
        class_level = "Allowance"
    elif "Claiming" in classes:
        class_level = "Claiming"
    else:
        class_level = "Maiden"

    # Win efficiency
    if life_starts > 0:
        win_rate = round(life.get("wins", 0) / life_starts * 100, 1)
    else:
        win_rate = 0

    return {
        "preferred_surface": pref_surface,
        "preferred_distance": pref_distance,
        "best_speed": life_speed,
        "turf_speed": turf_speed,
        "wet_speed": wet_speed,
        "long_speed": long_speed,
        "wet_ability": wet_ability,
        "turf_ability": turf_ability,
        "class_level": class_level,
        "win_rate": win_rate,
        "life_starts": life_starts,
        # Works-based differentiation for maidens
        "work_count": ability.get("work_count", 0),
        "race_count": ability.get("race_count", 0),
        "activity_total": ability.get("activity_total", 0),
    }


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    print("Parsing horse abilities from meters.html...")

    horse_dirs = sorted([
        d for d in RAW.iterdir()
        if d.is_dir() and d.name != "_global"
    ])

    abilities = []
    for hdir in horse_dirs:
        name = hdir.name.replace("_", " ")
        print(f"  {name}...", end=" ")

        ability = parse_meters(hdir)
        if not ability:
            print("SKIP (no meters)")
            continue

        # Add class history
        ability["class_history"] = parse_profile_classes(hdir)

        # Derive preferences
        prefs = derive_preferences(ability)
        ability.update(prefs)
        ability["horse_name"] = name

        abilities.append(ability)
        speed = ability.get("best_speed", 0)
        surf = ability.get("preferred_surface", "?")
        dist = ability.get("preferred_distance", "?")
        print(f"Speed={speed} Surf={surf} Dist={dist}")

    # Save
    out_path = OUTPUTS / "horse_abilities.json"
    out_path.write_text(json.dumps(abilities, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nhorse_abilities.json: {len(abilities)} horses")

    # Summary table
    print(f"\n{'Horse':30s} {'Speed':>5s} {'Surf':>6s} {'Dist':>7s} {'Wet':>4s} {'Turf':>5s} {'Class':>10s} {'W%':>5s}")
    print("-" * 85)
    for a in sorted(abilities, key=lambda x: -x.get("best_speed", 0)):
        print(f"{a['horse_name']:30s} "
              f"{a.get('best_speed', 0):5d} "
              f"{a.get('preferred_surface', '?'):>6s} "
              f"{a.get('preferred_distance', '?'):>7s} "
              f"{a.get('wet_ability', 50):4d} "
              f"{a.get('turf_ability', 50):5d} "
              f"{a.get('class_level', '?'):>10s} "
              f"{a.get('win_rate', 0):5.1f}")


if __name__ == "__main__":
    main()
