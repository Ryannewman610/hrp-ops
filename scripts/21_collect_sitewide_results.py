"""21_collect_sitewide_results.py — Parse race results into structured CSV.

Parses results.html into outputs/sitewide/sitewide_races.csv with:
  date, track, surface, distance, class/conditions, purse,
  horse_name, finish_pos, stable_name, jockey, weight, time

Also parses stakes_calendar.html into outputs/sitewide/sitewide_stakes.csv.

SAFETY: Read-only. Parses already-exported HTML only.
"""

import csv
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
GLOBAL_DIR = ROOT / "inputs" / "export" / "raw" / "_global"
OUTPUTS = ROOT / "outputs" / "sitewide"


def parse_results() -> List[Dict]:
    """Parse results.html into structured race result rows."""
    rp = GLOBAL_DIR / "results.html"
    if not rp.exists():
        return []

    soup = BeautifulSoup(rp.read_text(encoding="utf-8", errors="replace"), "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    results: List[Dict] = []
    race_info: Dict[str, Any] = {}
    position = 0
    state = "scan"  # scan, in_race, in_entry
    entry: Dict[str, Any] = {}

    # Find track from page context
    track = ""
    for line in lines:
        # Track codes are 2-3 letter sequences in the weather section
        if re.match(r"^[A-Z]{2,3} (?:Fast|Good|Sloppy|Muddy|Firm|Yielding|Soft|XXXX)/", line):
            track = line.split()[0]
            break

    # Find date from page
    race_date = date.today().strftime("%-m/%-d/%Y")
    for line in lines:
        dm = re.match(r"(\d{1,2}/\d{1,2}/\d{4})", line)
        if dm:
            race_date = dm.group(1)
            break

    i = 0
    while i < len(lines):
        line = lines[i]

        # Race header
        race_m = re.match(r"Race #(\d+)\s+(\d{1,2}:\d{2})", line)
        if race_m:
            race_info = {
                "race_num": race_m.group(1),
                "post_time": race_m.group(2),
                "date": race_date,
                "track": track,
            }
            # Next line: conditions
            if i + 1 < len(lines):
                desc = lines[i + 1]
                race_info["conditions"] = desc
                # Parse components
                if "Dirt" in desc:
                    race_info["surface"] = "Dirt"
                elif "Turf" in desc:
                    race_info["surface"] = "Turf"
                else:
                    race_info["surface"] = ""

                dist_m = re.match(r"([\d\s/]+(?:Furlongs?|Mile))", desc, re.I)
                if dist_m:
                    race_info["distance"] = dist_m.group(1).strip()

                purse_m = re.search(r"Purse \$([\d,.]+)", desc)
                race_info["purse"] = purse_m.group(1) if purse_m else ""

                if "Maiden" in desc:
                    race_info["class"] = "Maiden"
                elif "Claiming" in desc:
                    race_info["class"] = "Claiming"
                elif "Allowance" in desc:
                    race_info["class"] = "Allowance"
                elif "Stakes" in desc or "Handicap" in desc:
                    race_info["class"] = "Stakes"
                else:
                    race_info["class"] = "Other"

            state = "in_race"
            position = 0
            i += 2
            continue

        if state == "in_race":
            # Skip column headers
            if line in ("##", "Horse Name", "Owner Name", "Jockey", "Wt", "Amt Won", "Time", "Cl"):
                i += 1
                continue

            # Position number
            if re.match(r"^\d{1,2}$", line) and int(line) <= 20:
                pos = int(line)
                if pos > position or pos == 1:
                    position = pos
                    entry = {**race_info, "finish_pos": str(pos)}
                    state = "expect_horse"
            elif line.startswith("Race #"):
                state = "scan"
                continue
            else:
                i += 1
                continue

        elif state == "expect_horse":
            entry["horse_name"] = line
            state = "expect_owner"

        elif state == "expect_owner":
            # Could be owner or jockey if name spans multiple lines
            if line.startswith("Jockey"):
                entry["stable_name"] = entry.get("stable_name", "Unknown")
                entry["jockey"] = line
                state = "expect_weight"
            else:
                entry["stable_name"] = line
                state = "expect_jockey"

        elif state == "expect_jockey":
            entry["jockey"] = line
            state = "expect_weight"

        elif state == "expect_weight":
            entry["weight"] = line
            state = "expect_amtwon"

        elif state == "expect_amtwon":
            entry["amt_won"] = line
            state = "expect_time"

        elif state == "expect_time":
            entry["time"] = line
            state = "expect_cl"

        elif state == "expect_cl":
            entry["cl_price"] = line
            results.append(dict(entry))
            state = "in_race"

        i += 1

    return results


def parse_stakes_calendar() -> List[Dict]:
    """Parse stakes_calendar.html into structured stakes data."""
    sp = GLOBAL_DIR / "stakes_calendar.html"
    if not sp.exists():
        return []

    soup = BeautifulSoup(sp.read_text(encoding="utf-8", errors="replace"), "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    stakes: List[Dict] = []

    # Find the structured table section
    # Headers: RACE DATE, STAKE NAME, RESTRICT, ENTRIES, TRK, AGE, SEX, DIST, S, PURSE
    header_idx = -1
    for i, line in enumerate(lines):
        if line == "RACE DATE":
            header_idx = i
            break

    if header_idx < 0:
        return []

    # Skip past headers to data rows
    # After headers, data comes in groups: date, name, [restrict], entries_frac, [grade], track, age, sex, dist, surface, purse
    i = header_idx
    while i < len(lines) and lines[i] in ("RACE DATE", "STAKE NAME", "RESTRICT", "ENTRIES",
                                            "TRK", "AGE", "SEX", "DIST", "S", "PURSE"):
        i += 1

    while i < len(lines):
        line = lines[i]
        # Date line starts a new stake
        date_m = re.match(r"(\d{1,2}/\d{1,2}/\d{4})", line)
        if date_m:
            stake = {"date": date_m.group(1)}
            i += 1
            if i >= len(lines):
                break

            # Stake name (may include grade on next line)
            stake["name"] = lines[i]
            i += 1

            # Read remaining fields until next date or end
            remaining = []
            while i < len(lines) and not re.match(r"\d{1,2}/\d{1,2}/\d{4}", lines[i]):
                remaining.append(lines[i])
                i += 1

            # Parse remaining — look for track code, entries, purse
            for r in remaining:
                # Entries pattern: "N/N"
                em = re.match(r"(\d+)/(\d+)", r)
                if em:
                    stake["entries"] = int(em.group(1))
                    stake["max_entries"] = int(em.group(2))
                    continue
                # Grade
                if r.startswith("(G"):
                    stake["grade"] = r.strip("()")
                    continue
                # Track code (2-3 uppercase letters)
                if re.match(r"^[A-Z]{2,3}$", r):
                    stake["track"] = r
                    continue
                # Age
                if r in ("2", "3", "3+", "4+", "3 / 3+", "3+ / 4+"):
                    stake["age"] = r
                    continue
                # Sex
                if r in ("O", "F", "M", "C&G"):
                    stake["sex"] = r
                    continue
                # Surface
                if r in ("D", "T"):
                    stake["surface"] = "Dirt" if r == "D" else "Turf"
                    continue
                # Distance
                dist_m = re.match(r"(\d[\d\s/]*)", r)
                if dist_m and len(r) <= 10:
                    stake["distance"] = r
                    continue
                # Purse
                purse_m = re.match(r"([\d,.]+)", r)
                if purse_m and "." in r:
                    stake["purse"] = r
                    continue
                # Restrict tags
                if r.startswith("["):
                    stake["restrict"] = r
                    continue

            if stake.get("track"):
                stakes.append(stake)
        else:
            i += 1

    return stakes


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    # Parse race results
    results = parse_results()
    print(f"Sitewide race results: {len(results)} finisher rows")

    if results:
        csv_path = OUTPUTS / "sitewide_races.csv"
        fieldnames = ["date", "track", "race_num", "post_time", "surface", "distance",
                      "class", "conditions", "purse", "horse_name", "finish_pos",
                      "stable_name", "jockey", "weight", "amt_won", "time", "cl_price"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)
        print(f"  → sitewide_races.csv: {len(results)} rows")

        # Quick stats
        stables = set(r["stable_name"] for r in results if r.get("stable_name"))
        horses = set(r["horse_name"] for r in results if r.get("horse_name"))
        print(f"  Unique stables: {len(stables)}")
        print(f"  Unique horses: {len(horses)}")

    # Parse stakes calendar
    stakes = parse_stakes_calendar()
    print(f"\nStakes calendar: {len(stakes)} stakes")

    if stakes:
        csv_path = OUTPUTS / "sitewide_stakes.csv"
        fieldnames = ["date", "name", "grade", "track", "age", "sex", "distance",
                      "surface", "purse", "entries", "max_entries", "restrict"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(stakes)
        print(f"  → sitewide_stakes.csv: {len(stakes)} rows")

    # Save combined JSON
    combined = {
        "generated": today,
        "race_results": len(results),
        "stakes_parsed": len(stakes),
    }
    (OUTPUTS / f"collection_manifest_{today}.json").write_text(
        json.dumps(combined, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
