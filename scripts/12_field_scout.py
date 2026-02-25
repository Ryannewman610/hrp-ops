"""12_field_scout.py — Fetch race detail pages and parse entrant fields.

Reads candidate races from race_calendar JSON and fetches the HRP
race entries page for each to determine:
  - field size
  - entrants (horse names, stable names if visible)
  - field_strength_score (heuristic)
  - softness_rank

Uses authenticated session cookies for polite scraping.
Caches fetched pages to avoid refetching.

SAFETY: Read-only. No form submissions. No entering/nominating.
"""

import json
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
AUTH_PATH = ROOT / "inputs" / "export" / "auth.json"
CACHE_DIR = OUTPUTS / "field_scout_cache"
BASE_URL = "https://www.horseracingpark.com"

# HRP track code → full URL identifier mapping
# We'll discover race pages through the race calendar page itself
RACE_CALENDAR_URL = f"{BASE_URL}/handicapping/race_calendar.aspx"
ENTRIES_URL_TEMPLATE = f"{BASE_URL}/handicapping/entries.aspx"


def load_cookies() -> Dict[str, str]:
    """Load session cookies from auth.json."""
    if not AUTH_PATH.exists():
        print("ERROR: auth.json not found")
        return {}
    auth = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    return {c["name"]: c["value"] for c in auth.get("cookies", [])}


def fetch_page(url: str, cookies: Dict[str, str], cache_key: str) -> Optional[str]:
    """Fetch a page with caching and polite delays."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{cache_key}.html"

    # Use cache if exists and is from today
    if cache_path.exists():
        stat = cache_path.stat()
        today = date.today()
        from datetime import datetime
        mtime = datetime.fromtimestamp(stat.st_mtime).date()
        if mtime == today:
            return cache_path.read_text(encoding="utf-8", errors="replace")

    # Fetch with authenticated session
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HRP-Ops/1.0",
        "Accept": "text/html",
    }
    try:
        time.sleep(3)  # Polite delay
        resp = requests.get(url, cookies=cookies, headers=headers, timeout=30)
        if resp.status_code == 200:
            html = resp.text
            cache_path.write_text(html, encoding="utf-8")
            return html
        else:
            print(f"  WARN: HTTP {resp.status_code} for {url}")
            return None
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def parse_entries_page(html: str) -> Dict[str, Any]:
    """Parse a race entries/detail page for field information."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    entrants: List[Dict[str, str]] = []
    field_size = 0

    # Look for entry rows in tables
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        headers = [c.get_text(" ", strip=True).upper() for c in rows[0].find_all(["th", "td"])]
        header_text = " ".join(headers)

        # Check if this table has horse/entry data
        if any(kw in header_text for kw in ["HORSE", "ENTRY", "PP", "POST", "JOCKEY", "TRAINER"]):
            for row in rows[1:]:
                cells = [c.get_text(" ", strip=True) for c in row.find_all(["td"])]
                if len(cells) < 2:
                    continue

                entry = {}
                for k, hdr in enumerate(headers):
                    if k >= len(cells):
                        break
                    val = cells[k].strip()
                    if not val:
                        continue
                    if "HORSE" in hdr or "NAME" in hdr:
                        entry["horse"] = val
                    elif "STABLE" in hdr or "OWNER" in hdr:
                        entry["stable"] = val
                    elif "JOCKEY" in hdr:
                        entry["jockey"] = val
                    elif "TRAINER" in hdr:
                        entry["trainer"] = val
                    elif "RECORD" in hdr or "W-P-S" in hdr:
                        entry["record"] = val
                    elif "SRF" in hdr:
                        entry["srf"] = val
                    elif "EARNING" in hdr:
                        entry["earnings"] = val
                    elif "PP" in hdr or "POST" in hdr:
                        entry["post_position"] = val

                if entry.get("horse"):
                    entrants.append(entry)

    field_size = len(entrants)

    # If no table entries found, try text patterns
    if not entrants:
        # Look for numbered entries like "1. Horse Name (Stable)"
        for line in lines:
            m = re.match(r"^\d+\.\s+(.+?)(?:\s*\((.+?)\))?$", line)
            if m:
                entry = {"horse": m.group(1).strip()}
                if m.group(2):
                    entry["stable"] = m.group(2).strip()
                entrants.append(entry)
        field_size = len(entrants)

    # Compute field strength heuristic
    strength_score = compute_field_strength(entrants)

    return {
        "field_size": field_size,
        "entrants": entrants,
        "field_strength_score": strength_score,
    }


def compute_field_strength(entrants: List[Dict]) -> float:
    """Compute a simple field strength heuristic (0-100 scale).
    Higher = stronger field = harder race.
    """
    if not entrants:
        return 50.0  # Unknown

    score = 50.0  # Baseline

    # Smaller fields are softer
    n = len(entrants)
    if n <= 4:
        score -= 15
    elif n <= 6:
        score -= 5
    elif n >= 10:
        score += 10
    elif n >= 12:
        score += 20

    # If we have record data, use it
    records = [e.get("record", "") for e in entrants if e.get("record")]
    if records:
        # Parse W-P-S records
        total_wins = 0
        total_starts = 0
        for rec in records:
            parts = re.findall(r"\d+", rec)
            if len(parts) >= 1:
                total_wins += int(parts[0])
                if len(parts) >= 4:
                    total_starts += int(parts[3]) if len(parts) > 3 else sum(int(p) for p in parts)

        if total_starts > 0:
            win_rate = total_wins / total_starts
            if win_rate > 0.25:
                score += 15  # Strong field
            elif win_rate < 0.10:
                score -= 15  # Weak field

    return round(min(max(score, 0), 100), 1)


# ── Main Pipeline ────────────────────────────────────────

def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    # Load cookies
    cookies = load_cookies()
    if not cookies:
        print("No auth cookies. Run 01_login_save_state.py first.")
        return

    # Load race calendar
    cal_path = OUTPUTS / f"race_calendar_{today}.json"
    if not cal_path.exists():
        cals = sorted(OUTPUTS.glob("race_calendar_*.json"), reverse=True)
        if cals:
            cal_path = cals[0]
    if not cal_path.exists():
        print("No race calendar found. Run 07_parse_race_calendar.py first.")
        return

    cal = json.loads(cal_path.read_text(encoding="utf-8"))
    races = cal.get("races", [])
    print(f"Race calendar: {len(races)} races")

    # Load horse ratings for filtering
    ratings_path = OUTPUTS / "model" / "horse_ratings.json"
    horse_models = {}
    if ratings_path.exists():
        horse_models = json.loads(ratings_path.read_text(encoding="utf-8"))

    # Select top candidate races (up to 25)
    # Prefer races with dates and tracks
    candidate_races = [r for r in races if r.get("date") and r.get("track")][:25]
    print(f"Candidate races to scout: {len(candidate_races)}")

    # First, get the entries/nominations page to find race links
    print("\nFetching entries page...")
    entries_html = fetch_page(ENTRIES_URL_TEMPLATE, cookies, "entries_main")

    race_links = {}
    if entries_html:
        soup = BeautifulSoup(entries_html, "html.parser")
        # Find links to individual race pages
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if "race" in href.lower() and ("entries" in href.lower() or "card" in href.lower()):
                full_url = href if href.startswith("http") else BASE_URL + href
                race_links[text] = full_url

    print(f"  Found {len(race_links)} race links")

    # Scout each candidate race
    scouted_races: List[Dict[str, Any]] = []
    for i, race in enumerate(candidate_races):
        track = race.get("track", "")
        race_date = race.get("date", "")
        conditions = race.get("conditions", "")[:50]
        race_id = race.get("race_id", f"race_{i}")

        print(f"\n[{i+1}/{len(candidate_races)}] {race_date} {track} {conditions}")

        # Try to find a matching link
        page_url = None
        for link_text, link_url in race_links.items():
            if track.lower() in link_text.lower() or track.lower() in link_url.lower():
                page_url = link_url
                break

        field_data = {"field_size": 0, "entrants": [], "field_strength_score": 50.0}

        if page_url:
            cache_key = f"race_{race_id}"
            html = fetch_page(page_url, cookies, cache_key)
            if html:
                field_data = parse_entries_page(html)
                print(f"  Field size: {field_data['field_size']}, Strength: {field_data['field_strength_score']}")
        else:
            print(f"  No direct link found — using estimated field data")
            # Estimate from conditions text
            if "maiden" in conditions.lower():
                field_data["field_strength_score"] = 35.0  # Maiden = softer
            elif "clm" in conditions.lower() and "10" not in conditions:
                field_data["field_strength_score"] = 40.0  # Low claiming = softer
            elif "stk" in conditions.lower() or "stakes" in conditions.lower():
                field_data["field_strength_score"] = 70.0  # Stakes = harder

        scouted_races.append({
            "race_id": race_id,
            "date": race_date,
            "track": track,
            "conditions": conditions,
            "distance": race.get("distance", ""),
            "surface": race.get("surface", ""),
            "field_size": field_data["field_size"],
            "entrants": field_data["entrants"],
            "field_strength_score": field_data["field_strength_score"],
            "softness_rank": 0,  # Computed after all races scouted
            "page_url": page_url or "",
        })

    # Compute softness rank (1 = softest)
    scouted_races.sort(key=lambda x: x["field_strength_score"])
    for i, r in enumerate(scouted_races):
        r["softness_rank"] = i + 1

    # Save output
    output = {
        "date": today,
        "total_scouted": len(scouted_races),
        "races": scouted_races,
    }
    out_path = OUTPUTS / f"field_scout_{today}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nfield_scout_{today}.json: {len(scouted_races)} races scouted")

    # Show summary
    print("\nSoftness Ranking:")
    for r in scouted_races[:10]:
        print(f"  #{r['softness_rank']:2d} | Str={r['field_strength_score']:5.1f} | "
              f"Field={r['field_size']:2d} | {r['date']} {r['track']} {r['conditions'][:35]}")


if __name__ == "__main__":
    main()
