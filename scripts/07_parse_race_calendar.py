"""07_parse_race_calendar.py — Parse race_calendar.html into structured JSON.

Input:  inputs/export/raw/_global/race_calendar.html
Output: outputs/race_calendar_YYYY-MM-DD.json

HRP race calendar uses repeating blocks:
  RACE DATE / TIME / DEADLINE / TRACK / RACE ## / DISTANCE / SURFACE / RACE TYPE
  [value for each header]
  [conditions lines...]
  Owners: N / Field Size: N

This parser extracts each block into a structured race record.
"""

import json
import re
from datetime import date
from hashlib import md5
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
GLOBAL_DIR = ROOT / "inputs" / "export" / "raw" / "_global"
OUTPUTS = ROOT / "outputs"

# Block headers that signal a new race
BLOCK_HEADERS = ["RACE DATE", "TIME", "DEADLINE", "TRACK", "RACE ##", "DISTANCE", "SURFACE", "RACE TYPE"]

# Known HRP track codes
TRACK_CODES = {
    "ALB", "AP", "AQU", "ARP", "ASD", "ATL", "BEL", "BEU", "BM", "BOI",
    "BTP", "CBY", "CD", "CLS", "CNL", "CRC", "CT", "DED", "DEL", "DMR",
    "ELP", "EMD", "EVD", "FE", "FER", "FG", "FL", "FMT", "FNO", "FON",
    "FP", "FPX", "GG", "GP", "GRP", "HAW", "HOL", "HOO", "HOU", "HPO",
    "HST", "IND", "KD", "KEE", "LA", "LAD", "LNN", "LRL", "LS", "MAN",
    "MD", "MED", "MNR", "MTH", "NP", "OP", "PEN", "PID", "PIM", "PLN",
    "PM", "PRM", "PRX", "RD", "RET", "RIL", "RP", "RUI", "SA", "SAC",
    "SAR", "SR", "SRP", "STK", "SUD", "SUF", "SUN", "TAM", "TDN", "TP",
    "TUP", "WO", "YAV", "ZIA",
}


def make_race_id(date_str: str, track: str, race_num: str, post_time: str) -> str:
    """Stable race ID from date + track + race number + time."""
    raw = f"{date_str}_{track}_{race_num}_{post_time}".lower().strip()
    return md5(raw.encode()).hexdigest()[:12]


def parse_race_calendar() -> List[Dict[str, Any]]:
    """Parse race calendar by extracting repeating header→value blocks."""
    cal_path = GLOBAL_DIR / "race_calendar.html"
    if not cal_path.exists():
        print(f"  WARN: {cal_path} not found")
        return []

    soup = BeautifulSoup(cal_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    races: List[Dict[str, Any]] = []
    i = 0
    n = len(lines)

    while i < n:
        # Look for the start of a race block: "RACE DATE" header
        if lines[i] == "RACE DATE":
            # Read the 8 headers and their values
            # Headers: RACE DATE, TIME, DEADLINE, TRACK, RACE ##, DISTANCE, SURFACE, RACE TYPE
            # The headers appear first (L505-L512), then values follow (L513-L520+)
            # But they repeat as a group for each race block

            # Verify we have enough lines for headers
            if i + 7 >= n:
                break

            # Check that lines i..i+7 are the expected headers
            expected = ["RACE DATE", "TIME", "DEADLINE", "TRACK", "RACE ##", "DISTANCE", "SURFACE", "RACE TYPE"]
            headers_match = True
            for k, exp in enumerate(expected):
                if i + k >= n or lines[i + k] != exp:
                    headers_match = False
                    break

            if not headers_match:
                i += 1
                continue

            # Values follow immediately after the 8 headers
            val_start = i + 8
            if val_start + 7 >= n:
                break

            race_date = lines[val_start] if val_start < n else ""
            post_time = lines[val_start + 1] if val_start + 1 < n else ""
            deadline = lines[val_start + 2] if val_start + 2 < n else ""
            track = lines[val_start + 3] if val_start + 3 < n else ""
            race_num_raw = lines[val_start + 4] if val_start + 4 < n else ""
            distance = lines[val_start + 5] if val_start + 5 < n else ""
            surface = lines[val_start + 6] if val_start + 6 < n else ""
            race_type = lines[val_start + 7] if val_start + 7 < n else ""

            # Validate track code
            if track.upper() not in TRACK_CODES:
                i += 1
                continue

            # Validate date
            if not re.match(r"\d{1,2}/\d{1,2}/\d{2,4}", race_date):
                i += 1
                continue

            # Extract race number
            race_num_m = re.search(r"#(\d+)", race_num_raw)
            race_num = race_num_m.group(1) if race_num_m else ""

            # Collect conditions text (everything after RACE TYPE value until next "Owners:" or "RACE DATE")
            conditions_lines = []
            j = val_start + 8
            field_size = None
            owners_count = None

            while j < n:
                line = lines[j]
                if line == "RACE DATE":
                    break  # Next race block
                if line.startswith("Owners:"):
                    j += 1
                    if j < n and lines[j].isdigit():
                        owners_count = int(lines[j])
                    j += 1
                    continue
                if line.startswith("Field Size:"):
                    j += 1
                    if j < n and lines[j].isdigit():
                        field_size = int(lines[j])
                    j += 1
                    continue
                # Skip if it's a block header (next race)
                if line in BLOCK_HEADERS:
                    break
                conditions_lines.append(line)
                j += 1

            conditions = " ".join(conditions_lines).strip()

            # Build race record
            race_id = make_race_id(race_date, track.upper(), race_num, post_time)
            race: Dict[str, Any] = {
                "race_id": race_id,
                "date": race_date,
                "post_time": post_time,
                "deadline": deadline,
                "track": track.upper(),
                "race_num": race_num,
                "distance": distance,
                "surface": surface,
                "race_type": race_type,
                "conditions": conditions,
                "field_size": field_size,
                "owners": owners_count,
            }

            # Add purse if visible
            purse_m = re.search(r"Purse \$([0-9,.]+)", conditions)
            if purse_m:
                race["purse"] = purse_m.group(1)

            # Add claiming price if visible
            claim_m = re.search(r"Claiming Price \$([0-9,.]+)", conditions)
            if claim_m:
                race["claiming_price"] = claim_m.group(1)

            races.append(race)
            i = j  # Skip to where we left off
        else:
            i += 1

    return races


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    races = parse_race_calendar()
    output = {
        "date": today,
        "source": "race_calendar.html",
        "total_races": len(races),
        "races": races,
    }

    out_path = OUTPUTS / f"race_calendar_{today}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Race calendar: {out_path}")
    print(f"  Total: {len(races)} valid races")

    # Validation checks
    errors = 0
    field_zeros = 0
    for r in races:
        track = r.get("track", "")
        dt = r.get("date", "")
        if track in ("TRACK", "RACE TYPE") or dt in ("RACE TYPE", "TRACK"):
            print(f"  ERROR: Malformed race: track={track} date={dt}")
            errors += 1
        if r.get("field_size") == 0:
            field_zeros += 1

    if errors:
        print(f"  {errors} MALFORMED ERRORS!")
    else:
        print("  CLEAN: No malformed entries ✓")

    if field_zeros:
        print(f"  WARN: {field_zeros} races with field_size=0")

    # Stats
    tracks = set(r["track"] for r in races)
    field_sizes = [r["field_size"] for r in races if r.get("field_size")]
    print(f"\n  Tracks: {sorted(tracks)}")
    if field_sizes:
        print(f"  Field sizes: min={min(field_sizes)} max={max(field_sizes)} avg={sum(field_sizes)/len(field_sizes):.1f}")

    # Sample
    if races:
        print(f"\n  Sample races:")
        for r in races[:5]:
            print(f"    {r['date']:12s} {r['post_time']:6s} {r['track']:5s} R#{r['race_num']:2s} "
                  f"{r['distance']:8s} {r['surface']:5s} {r['race_type']:20s} F={r.get('field_size','?')}")


if __name__ == "__main__":
    main()
