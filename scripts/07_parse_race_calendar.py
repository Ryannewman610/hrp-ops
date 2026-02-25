"""07_parse_race_calendar.py — Parse race_calendar.html into structured JSON.

Input:  inputs/export/raw/_global/race_calendar.html
Output: outputs/race_calendar_YYYY-MM-DD.json

HARD FILTERS: Explicitly excludes navigation labels and non-race text.
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

# ── Garbage filter ──────────────────────────────────────────
# These terms, if found in a candidate line, disqualify it as a race
GARBAGE_EXACT = {
    "handicapping", "handicapping - wager pad", "stakes calendar",
    "track calendar", "wager pad", "track condition", "weather",
    "no headlines", "toggle", "stables", "auctions", "breeding",
    "farms", "credits", "retire", "purchase", "bulk move",
    "bulk train", "owner stats", "private sales", "purchase horse",
    "purchase srf", "retire horse", "sitemap", "privacy",
    "my stable", "month day year", "budgeted views",
}

GARBAGE_SUBSTRINGS = [
    "handicapping", "wager pad", "stakes calendar", "track calendar",
    "headlines", "toggle", "privacy", "sitemap", "budgeted",
    "bulk move", "bulk train", "owner stats", "purchase horse",
    "purchase srf", "retire horse", "private sales",
]

# Valid race class keywords (must appear for a line to be a race)
RACE_CLASS_KEYWORDS = [
    "clm", "oclm", "mdn", "mdspwt", "alw", "stk", "hcp", "wcl",
    "opt", "maiden", "claiming", "allowance", "stakes", "handicap",
    "statebred", "fillies", "colts", "geldings",
    "n1x", "n2x", "n3x", "n1l", "n2l", "n3l",
    "year-old", "three-year", "four-year", "two-year",
]


def is_garbage(text: str) -> bool:
    """Check if text is a navigation/menu item, not a race."""
    t = text.strip().lower()
    if t in GARBAGE_EXACT:
        return True
    for sub in GARBAGE_SUBSTRINGS:
        if sub in t:
            return True
    return False


def has_race_class(text: str) -> bool:
    """Check if text contains valid race classification keywords."""
    t = text.lower()
    return any(kw in t for kw in RACE_CLASS_KEYWORDS)


def make_race_id(date_str: str, track: str, conditions: str) -> str:
    """Generate synthetic race ID from components."""
    raw = f"{date_str}_{track}_{conditions}".lower()
    return md5(raw.encode()).hexdigest()[:12]


def parse_distance_furlongs(dist: str) -> Optional[float]:
    """Convert '5f', '6 1/2f', '1m' to furlongs."""
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


# ── Table-based Parser ──────────────────────────────────────

def parse_from_tables(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extract races from HTML tables."""
    races = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers = [c.get_text(" ", strip=True).upper() for c in header_cells]

        race_keywords = {"RACE", "TRACK", "DISTANCE", "TIME", "CLASS", "#", "SURF", "SURFACE", "CONDITIONS"}
        if not any(k in " ".join(headers) for k in race_keywords):
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            cell_texts = [c.get_text(" ", strip=True) for c in cells]
            raw_text = " | ".join(cell_texts)

            if is_garbage(raw_text):
                continue

            race: Dict[str, Any] = {"raw_text": raw_text}
            for i, hdr in enumerate(headers):
                if i >= len(cell_texts):
                    break
                val = cell_texts[i].strip()
                if not val:
                    continue
                if "DATE" in hdr:
                    race["date"] = val
                elif "TIME" in hdr:
                    race["post_time"] = val
                elif "TRACK" in hdr:
                    race["track"] = val
                elif "DIST" in hdr:
                    race["distance"] = val
                    race["distance_f"] = parse_distance_furlongs(val)
                elif "SURF" in hdr:
                    race["surface"] = val
                elif "CLASS" in hdr or "COND" in hdr:
                    race.setdefault("conditions", val)
                elif hdr.strip() in ("#", "##", "RACE#", "RACE"):
                    if val.isdigit():
                        race["race_num"] = val
                    else:
                        race.setdefault("conditions", val)
                elif "PURSE" in hdr or "FEE" in hdr:
                    race["purse"] = val

            # Validate: must have track or conditions that look like a real race
            if race.get("track") and (race.get("distance") or race.get("conditions")):
                if not is_garbage(race.get("conditions", "")):
                    race["race_id"] = make_race_id(
                        race.get("date", ""), race.get("track", ""), race.get("conditions", ""))
                    races.append(race)

    return races


# ── Text-based Parser (fallback) ─────────────────────────────

def parse_from_text(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extract races from page text using pattern matching."""
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    races = []
    current_date = ""
    current_track = ""

    for line in lines:
        if not line or len(line) < 3:
            continue

        # Skip garbage
        if is_garbage(line):
            continue

        # Date pattern
        date_m = re.match(r"^(\d{1,2}/\d{1,2}/\d{2,4})$", line)
        if date_m:
            current_date = date_m.group(1)
            continue

        # Track pattern (3-4 uppercase letters alone)
        track_m = re.match(r"^([A-Z]{2,5})$", line)
        if track_m and len(line) <= 5:
            current_track = track_m.group(1)
            continue

        # Must contain race class keywords and NOT be garbage
        if has_race_class(line) and len(line) > 5:
            race: Dict[str, Any] = {
                "conditions": line,
                "raw_text": line,
            }

            if current_date:
                race["date"] = current_date
            if current_track:
                race["track"] = current_track

            # Extract distance
            dist_m = re.search(r"(\d+\s*\d*/?\d*\s*[fm])\b", line)
            if dist_m:
                race["distance"] = dist_m.group(1).strip()
                race["distance_f"] = parse_distance_furlongs(dist_m.group(1))

            # Extract surface
            if "Turf" in line:
                race["surface"] = "Turf"
            elif "Dirt" in line:
                race["surface"] = "Dirt"

            # Extract purse
            purse_m = re.search(r"\$[\d,.]+", line)
            if purse_m:
                race["purse"] = purse_m.group(0)

            # Extract post time
            time_m = re.search(r"(\d{1,2}:\d{2})\s*(AM|PM)?", line, re.I)
            if time_m:
                race["post_time"] = time_m.group(0)

            # Generate race ID
            race["race_id"] = make_race_id(
                race.get("date", ""), race.get("track", ""), race.get("conditions", ""))

            races.append(race)

    return races


# ── Main ─────────────────────────────────────────────────

def parse_race_calendar() -> List[Dict[str, Any]]:
    """Parse race calendar with garbage filtering and dedup."""
    cal_path = GLOBAL_DIR / "race_calendar.html"
    if not cal_path.exists():
        print(f"  WARN: {cal_path} not found")
        return []

    soup = BeautifulSoup(cal_path.read_text(encoding="utf-8", errors="replace"), "html.parser")

    # Run BOTH parsers and merge (tables may find some, text finds others)
    table_races = parse_from_tables(soup)
    text_races = parse_from_text(soup)
    all_races = table_races + text_races

    # Final dedup by raw_text
    seen = set()
    unique = []
    for r in all_races:
        key = r.get("raw_text", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    # Final garbage sweep
    clean = []
    for r in unique:
        cond = r.get("conditions", "").lower()
        raw = r.get("raw_text", "").lower()
        combined = cond + " " + raw
        if is_garbage(combined):
            continue
        clean.append(r)

    return clean


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
    print(f"  Races parsed: {len(races)}")

    # Verify no garbage
    for r in races:
        cond = r.get("conditions", "")
        if any(g in cond.lower() for g in ["handicapping", "stakes calendar", "wager pad"]):
            print(f"  ERROR: Garbage leaked: {cond}")

    if races:
        print(f"\n  Sample races:")
        for r in races[:5]:
            parts = [r.get("date", "?"), r.get("track", "?"),
                     r.get("distance", "?"), r.get("conditions", "?")[:40]]
            print(f"    {' | '.join(parts)}")


if __name__ == "__main__":
    main()
