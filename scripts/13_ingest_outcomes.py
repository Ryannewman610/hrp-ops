"""13_ingest_outcomes.py — Parse race results for our horses.

Produces outputs/outcomes_log.csv (append-only) with:
  race_id, date, track, race_num, horse_name, finish_position,
  purse_earned, field_size_final, notes

Sources (in priority order):
  1. Horse profile "All Races" pages (profile_allraces.html)
  2. results.html global export
  3. Snapshot recent_races

SAFETY: Read-only. No form submissions.
"""

import csv
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "inputs" / "export" / "raw"
OUTPUTS = ROOT / "outputs"
INACTIVE = {"shebasbriar", "averyspluck", "hiptag793004736512"}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_hrp_date(d: str) -> str:
    """Parse HRP date '14Feb26' to '2/14/2026'."""
    m = re.match(r"(\d{1,2})([A-Z][a-z]{2})(\d{2})", d.strip())
    if not m:
        return d
    day, mon, yr = m.groups()
    months = {"Jan": "1", "Feb": "2", "Mar": "3", "Apr": "4", "May": "5", "Jun": "6",
              "Jul": "7", "Aug": "8", "Sep": "9", "Oct": "10", "Nov": "11", "Dec": "12"}
    mo = months.get(mon, "0")
    return f"{mo}/{day}/20{yr}"


def ingest_from_profiles() -> List[Dict]:
    """Parse race results from each horse's profile_allraces.html."""
    outcomes = []
    horse_dirs = [d for d in (EXPORT_DIR).iterdir() if d.is_dir() and d.name != "_global"]

    for hdir in horse_dirs:
        horse_name = hdir.name.replace("_", " ").title()
        if norm(horse_name) in INACTIVE:
            continue

        races_file = hdir / "profile_allraces.html"
        if not races_file.exists():
            continue

        soup = BeautifulSoup(races_file.read_text(encoding="utf-8", errors="replace"), "html.parser")

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            headers = [c.get_text(" ", strip=True).upper() for c in rows[0].find_all(["th", "td"])]
            header_text = " ".join(headers)
            if not any(kw in header_text for kw in ["DATE", "TRACK", "FINISH", "PURSE", "RACE"]):
                continue

            for row in rows[1:]:
                cells = [c.get_text(" ", strip=True) for c in row.find_all(["td"])]
                if len(cells) < 3:
                    continue

                result: Dict[str, Any] = {"horse_name": horse_name, "source": "profile"}
                for k, hdr in enumerate(headers):
                    if k >= len(cells):
                        break
                    val = cells[k].strip()
                    if not val:
                        continue
                    if "DATE" in hdr:
                        result["date"] = parse_hrp_date(val) if re.match(r"\d{1,2}[A-Z]", val) else val
                    elif "TRACK" in hdr:
                        result["track"] = val
                    elif "RACE" in hdr and "#" in hdr:
                        result["race_num"] = val.replace("Race #", "").strip()
                    elif "FINISH" in hdr or "POS" in hdr:
                        result["finish_position"] = val
                    elif "PURSE" in hdr or "EARN" in hdr:
                        result["purse_earned"] = val
                    elif "DIST" in hdr:
                        result["distance"] = val
                    elif "SRF" in hdr:
                        result["srf"] = val
                    elif "FIELD" in hdr:
                        result["field_size_final"] = val

                if result.get("date") and result.get("track"):
                    outcomes.append(result)

    return outcomes


def ingest_from_results_html() -> List[Dict]:
    """Parse global results.html for race outcomes."""
    results_path = EXPORT_DIR / "_global" / "results.html"
    if not results_path.exists():
        return []

    soup = BeautifulSoup(results_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    outcomes = []

    # Look for result tables
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [c.get_text(" ", strip=True).upper() for c in rows[0].find_all(["th", "td"])]
        if not any(kw in " ".join(headers) for kw in ["FINISH", "HORSE", "RESULT"]):
            continue

        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td"])]
            if len(cells) < 2:
                continue
            result: Dict[str, Any] = {"source": "results_html"}
            for k, hdr in enumerate(headers):
                if k >= len(cells):
                    break
                val = cells[k].strip()
                if not val:
                    continue
                if "HORSE" in hdr:
                    result["horse_name"] = val
                elif "FINISH" in hdr or "POS" in hdr:
                    result["finish_position"] = val
                elif "DATE" in hdr:
                    result["date"] = val
                elif "TRACK" in hdr:
                    result["track"] = val
                elif "PURSE" in hdr or "EARN" in hdr:
                    result["purse_earned"] = val
            if result.get("horse_name"):
                outcomes.append(result)

    return outcomes


def ingest_from_snapshot() -> List[Dict]:
    """Parse recent_races from stable_snapshot.json."""
    today = date.today().isoformat()
    snap_path = ROOT / "inputs" / today / "stable_snapshot.json"
    if not snap_path.exists():
        dirs = sorted((ROOT / "inputs").glob("20*-*-*"), reverse=True)
        for d in dirs:
            sp = d / "stable_snapshot.json"
            if sp.exists():
                snap_path = sp
                break
    if not snap_path.exists():
        return []

    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    outcomes = []
    for h in snap.get("horses", []):
        if norm(h["name"]) in INACTIVE:
            continue
        for r in h.get("recent_races", []):
            outcomes.append({
                "horse_name": h["name"],
                "date": r.get("date", ""),
                "track": r.get("track", ""),
                "race_num": r.get("race_num", ""),
                "finish_position": r.get("finish", ""),
                "distance": r.get("distance", ""),
                "notes": r.get("class", ""),
                "source": "snapshot",
            })
    return outcomes


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    print("Ingesting outcomes...")

    # Collect from all sources
    profile_outcomes = ingest_from_profiles()
    results_outcomes = ingest_from_results_html()
    snapshot_outcomes = ingest_from_snapshot()

    print(f"  Profiles:  {len(profile_outcomes)} results")
    print(f"  Results:   {len(results_outcomes)} results")
    print(f"  Snapshot:  {len(snapshot_outcomes)} results")

    # Merge and deduplicate (prefer profile > results > snapshot)
    all_outcomes = profile_outcomes + results_outcomes + snapshot_outcomes

    # Dedup by horse_name + date + track
    seen = set()
    unique = []
    for o in all_outcomes:
        key = f"{norm(o.get('horse_name', ''))}_{o.get('date', '')}_{o.get('track', '')}"
        if key not in seen:
            seen.add(key)
            unique.append(o)

    print(f"  Unique outcomes: {len(unique)}")

    # Save daily JSON
    json_path = OUTPUTS / f"outcomes_log_{today}.json"
    json_path.write_text(json.dumps(unique, indent=2, ensure_ascii=False), encoding="utf-8")

    # Append to CSV
    csv_path = OUTPUTS / "outcomes_log.csv"
    csv_exists = csv_path.exists()
    fieldnames = [
        "horse_name", "date", "track", "race_num", "finish_position",
        "distance", "purse_earned", "srf", "field_size_final", "notes", "source",
    ]
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not csv_exists:
            writer.writeheader()
        for o in unique:
            writer.writerow(o)

    print(f"outcomes_log.csv: appended {len(unique)} rows")
    print(f"outcomes_log_{today}.json: {len(unique)} entries")


if __name__ == "__main__":
    main()
