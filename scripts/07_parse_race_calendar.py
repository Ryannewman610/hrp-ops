"""07_parse_race_calendar.py — Parse race_calendar.html into structured JSON.

Input:  inputs/export/raw/_global/race_calendar.html
Output: inputs/YYYY-MM-DD/race_calendar.json
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
GLOBAL_DIR = ROOT / "inputs" / "export" / "raw" / "_global"


def parse_race_calendar() -> List[Dict[str, Any]]:
    """Parse race calendar HTML into structured race list."""
    cal_path = GLOBAL_DIR / "race_calendar.html"
    if not cal_path.exists():
        print(f"  WARN: {cal_path} not found")
        return []

    soup = BeautifulSoup(
        cal_path.read_text(encoding="utf-8", errors="replace"), "html.parser"
    )

    races: List[Dict[str, Any]] = []

    # Strategy: find tables that contain race data
    # Race calendar tables typically have columns like:
    # Race#, Time, Track, Distance, Surface, Class/Conditions
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Try to identify header row
        header_cells = rows[0].find_all(["th", "td"])
        headers = [c.get_text(" ", strip=True).upper() for c in header_cells]

        # Check if this looks like a race table
        race_keywords = {"RACE", "TRACK", "DISTANCE", "TIME", "CLASS", "#", "SURF", "SURFACE", "CONDITIONS"}
        if not any(k in " ".join(headers) for k in race_keywords):
            continue

        # Parse data rows
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            cell_texts = [c.get_text(" ", strip=True) for c in cells]
            raw_text = " | ".join(cell_texts)

            # Build race entry by position/keyword matching
            race: Dict[str, Any] = {"raw_text": raw_text}

            # Map cells to headers
            for i, hdr in enumerate(headers):
                if i < len(cell_texts):
                    val = cell_texts[i].strip()
                    if not val:
                        continue
                    if "DATE" in hdr:
                        race["date"] = val
                    elif "TIME" in hdr:
                        race["time"] = val
                    elif "TRACK" in hdr:
                        race["track"] = val
                    elif "DIST" in hdr:
                        race["distance"] = val
                    elif "SURF" in hdr:
                        race["surface"] = val
                    elif "CLASS" in hdr or "COND" in hdr or "RACE" in hdr:
                        if "race_class" not in race:
                            race["race_class"] = val
                    elif "#" in hdr and hdr.strip() in ("#", "##", "RACE#"):
                        race["race_num"] = val
                    elif "PURSE" in hdr or "FEE" in hdr:
                        race["purse"] = val

            # Only keep if we got meaningful data
            if race.get("track") or race.get("distance") or race.get("race_class"):
                races.append(race)

    # Also try to extract from the text directly if table parsing missed data
    # Look for patterns in the text like "02/26/26 16:55 TUP 5f Dirt OClm10"
    if not races:
        text = soup.get_text("\n", strip=True)
        lines = text.split("\n")
        current_date = ""
        for line in lines:
            # Date pattern
            date_match = re.match(r"(\d{1,2}/\d{1,2}/\d{2,4})", line.strip())
            if date_match:
                current_date = date_match.group(1)
                continue

            # Race line pattern: time track distance surface class
            race_match = re.match(
                r"(\d{1,2}:\d{2})\s+([A-Z]{2,5})\s+([\d/]+\s*[fmy][\w]*)\s+(\w+)\s+(.*)",
                line.strip(),
            )
            if race_match and current_date:
                races.append({
                    "date": current_date,
                    "time": race_match.group(1),
                    "track": race_match.group(2),
                    "distance": race_match.group(3),
                    "surface": race_match.group(4),
                    "race_class": race_match.group(5).strip(),
                    "raw_text": line.strip(),
                })

    return races


def main() -> None:
    today = date.today().isoformat()
    out_dir = ROOT / "inputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "race_calendar.json"

    races = parse_race_calendar()

    output = {
        "date": today,
        "source": "race_calendar.html",
        "total_races": len(races),
        "races": races,
    }

    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Race calendar: {out_path}")
    print(f"  Races parsed: {len(races)}")

    # Show sample
    if races:
        print(f"\n  Sample races:")
        for r in races[:5]:
            track = r.get("track", "?")
            dist = r.get("distance", "?")
            cls = r.get("race_class", "?")
            dt = r.get("date", "?")
            print(f"    {dt} {track} {dist} {cls}")


if __name__ == "__main__":
    main()
