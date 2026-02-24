"""05_build_stable_snapshot.py — Build stable_snapshot.json from raw HTML exports.

Reads inputs/export/raw/{horse}/ HTML files and produces a structured
JSON snapshot at inputs/YYYY-MM-DD/stable_snapshot.json.

This is a lightweight alternative to 04_parse_and_fill.py that produces
a JSON file optimized for report generation, not a full tracker update.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "inputs" / "export" / "raw"
GLOBAL_DIR = RAW_ROOT / "_global"


def read_html(path: Path) -> Optional[BeautifulSoup]:
    if not path.exists():
        return None
    return BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")


def text_of(s: Optional[BeautifulSoup]) -> str:
    if s is None:
        return ""
    return " ".join(s.stripped_strings)


def extract_field(text: str, label: str) -> str:
    """Extract a field value following a label in text."""
    pat = re.compile(rf"{re.escape(label)}[:\s]*(.+?)(?:\s{{2,}}|\n|$)", re.IGNORECASE)
    m = pat.search(text)
    return m.group(1).strip() if m else ""


def parse_roster_html() -> List[Dict[str, str]]:
    """Parse the stable roster global page for quick horse summary data."""
    roster_path = GLOBAL_DIR / "stable_roster.html"
    s = read_html(roster_path)
    if s is None:
        return []

    horses: List[Dict[str, str]] = []
    # Find the main roster table (has HORSE NAME header)
    for table in s.find_all("table"):
        txt = table.get_text(" ", strip=True).lower()
        if "horse name" not in txt:
            continue
        rows = table.find_all("tr")
        headers: List[str] = []
        for row in rows:
            cells = row.find_all(["th", "td"])
            cell_texts = [c.get_text(" ", strip=True) for c in cells]
            if not headers:
                if any("horse" in c.lower() for c in cell_texts):
                    headers = [c.strip().upper() for c in cell_texts]
                continue
            if len(cell_texts) < 3:
                continue
            h: Dict[str, str] = {}
            for i, hdr in enumerate(headers):
                if i < len(cell_texts):
                    h[hdr] = cell_texts[i]
            # Extract horse name from link
            link = row.find("a", href=True)
            if link:
                h["HORSE NAME"] = link.get_text(strip=True)
            horses.append(h)
        if horses:
            break
    return horses


def parse_horse_dir(horse_dir: Path) -> Dict[str, Any]:
    """Parse a single horse directory into a snapshot record."""
    profile_s = read_html(horse_dir / "profile_allraces.html")
    if profile_s is None:
        profile_s = read_html(horse_dir / "profile_printable.html")

    meters_s = read_html(horse_dir / "meters.html")
    works_s = read_html(horse_dir / "works_all.html")
    conf_s = read_html(horse_dir / "conformation.html")
    acc_s = read_html(horse_dir / "accessories.html")

    profile_text = text_of(profile_s)
    meters_text = text_of(meters_s)
    conf_text = text_of(conf_s)
    acc_text = text_of(acc_s)

    # Extract horse name
    name = horse_dir.name.replace("_", " ")
    if profile_s:
        h2 = profile_s.find("h2")
        if h2:
            raw = h2.get_text(strip=True)
            # Often "Past Performance - Horse Name"
            if " - " in raw:
                name = raw.split(" - ", 1)[1].strip()
            else:
                name = raw.strip()

    # Basic profile fields
    record: Dict[str, Any] = {
        "name": name,
        "dir": horse_dir.name,
    }

    # Age/sex/weight from profile text
    age_match = re.search(r"\b(\d+)\s*\((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\)", profile_text)
    if age_match:
        record["age"] = age_match.group(1)

    sex_match = re.search(r"\b(B\.|Ch\.|Dk\.|Gr\.|Ro\.)\s*(c|f|g|h|m|r)\.\s*(\d+)", profile_text, re.IGNORECASE)
    if sex_match:
        record["color"] = sex_match.group(1)
        record["sex"] = sex_match.group(2)

    height_match = re.search(r"(\d+\.\d+)h", profile_text)
    if height_match:
        record["height"] = height_match.group(1)

    weight_match = re.search(r"(\d+)\s*lbs", profile_text)
    if weight_match:
        record["weight"] = weight_match.group(1)

    # Sire/Dam
    sire_match = re.search(r"Sire:\s*(\S.+?)(?:\s{2}|Dam:)", profile_text)
    if sire_match:
        record["sire"] = sire_match.group(1).strip()
    dam_match = re.search(r"Dam:\s*(\S.+?)(?:\s{2}|Br:)", profile_text)
    if dam_match:
        record["dam"] = dam_match.group(1).strip()

    # Track
    track_match = re.search(r"Track:\s*(\S+)", profile_text)
    if track_match:
        record["track"] = track_match.group(1).strip()

    # Condition/Stamina/Consistency/Distance from meters (line-by-line)
    if meters_s:
        strings = list(meters_s.stripped_strings)
        for i, s in enumerate(strings):
            sl = s.strip().lower().rstrip(":")
            if sl == "condition" and i + 1 < len(strings):
                val = strings[i + 1].strip()
                if "%" in val:
                    record["condition"] = val
            elif sl == "stamina" and i + 1 < len(strings):
                val = strings[i + 1].strip()
                if "%" in val:
                    record["stamina"] = val
            elif sl == "consistency" and i + 1 < len(strings):
                val = strings[i + 1].strip()
                if re.match(r"[+-]?\d+", val):
                    record["consistency"] = val
            elif sl == "distance" and i + 1 < len(strings):
                val = strings[i + 1].strip()
                if val.isdigit():
                    record["distance_meter"] = val

    # Works count
    if works_s:
        work_rows = works_s.find_all("tr")
        record["works_count"] = max(0, len(work_rows) - 1)  # subtract header

    # Conformation highlights
    for trait in ["Leg Style", "Legs", "Gait", "Frame Size"]:
        m = re.search(rf"{trait}[:\s]*([\w\s]+?)(?:\s{{2,}}|$)", conf_text)
        if m:
            record[f"conf_{trait.lower().replace(' ', '_')}"] = m.group(1).strip()

    # Accessories
    acc_items = []
    for item in ["Blinkers", "Bute", "Front Wraps"]:
        if acc_text and re.search(rf"{item}.*?(?:Applied|Yes|✓|APPLY)", acc_text, re.IGNORECASE):
            acc_items.append(item)
    if acc_items:
        record["accessories"] = acc_items

    # Nominations from profile text
    noms_match = re.search(r"Nominations.*?(\d+)", profile_text)
    if profile_s:
        nom_section = profile_s.find(string=re.compile(r"Nominations", re.I))
        if nom_section:
            parent = nom_section.find_parent("table")
            if parent:
                nom_rows = parent.find_all("tr")
                noms = []
                for row in nom_rows[1:]:
                    cells = row.find_all("td")
                    if len(cells) >= 3:
                        noms.append({
                            "race": cells[0].get_text(strip=True),
                            "date": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                            "track": cells[3].get_text(strip=True) if len(cells) > 3 else "",
                        })
                if noms:
                    record["nominations"] = noms

    # Also try to find nominations from text pattern (backup)
    if "nominations" not in record and profile_s:
        strings = list(profile_s.stripped_strings)
        in_noms = False
        nom_data: Dict[str, str] = {}
        noms_list: list = []
        for i, s in enumerate(strings):
            sl = s.strip()
            if sl == "Nominations":
                in_noms = True
                continue
            if in_noms:
                if sl == "Entries":
                    in_noms = False
                    if nom_data.get("date"):
                        noms_list.append(dict(nom_data))
                    break
                if sl == "DATE" and i + 1 < len(strings):
                    if nom_data.get("date"):
                        noms_list.append(dict(nom_data))
                    nom_data = {"date": strings[i + 1].strip()}
                elif sl == "TRACK" and i + 1 < len(strings):
                    nom_data["track"] = strings[i + 1].strip()
                elif sl == "DISTANCE" and i + 1 < len(strings):
                    nom_data["distance"] = strings[i + 1].strip()
                elif sl == "#/#(#)" and i + 1 < len(strings):
                    nom_data["field"] = strings[i + 1].strip()
                elif sl == "SURF" and i + 1 < len(strings):
                    nom_data["surface"] = strings[i + 1].strip()
        if in_noms and nom_data.get("date"):
            noms_list.append(dict(nom_data))
        if noms_list:
            record["nominations"] = noms_list

    # Race record (LIFE line)
    life_match = re.search(r"LIFE\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", profile_text)
    if life_match:
        record["record"] = {
            "starts": life_match.group(1),
            "wins": life_match.group(2),
            "places": life_match.group(3),
            "shows": life_match.group(4),
        }

    # Parse individual race result lines from profile text
    # Format: "3/4" (finish), "12Feb26 TUP" (date/track), "5f fst 1:00" (dist/surf/time)
    if profile_s:
        strings = list(profile_s.stripped_strings)
        races: List[Dict[str, str]] = []
        i = 0
        while i < len(strings):
            s = strings[i].strip()
            # Match finish position pattern: digit/digit or digit-digit/digit-digit
            finish_match = re.match(r"^(\d+)/(\d+)$", s)
            if finish_match and i + 1 < len(strings):
                finish_pos = finish_match.group(1)
                field_size = finish_match.group(2)
                # Next string should be date + track
                next_s = strings[i + 1].strip() if i + 1 < len(strings) else ""
                date_trk = re.match(r"(\d{1,2}\w{3}\d{2})\s+(\w+)", next_s)
                if date_trk:
                    race = {
                        "finish": finish_pos,
                        "field": field_size,
                        "date": date_trk.group(1),
                        "track": date_trk.group(2),
                    }
                    # Next should be distance/surface/time
                    detail = strings[i + 2].strip() if i + 2 < len(strings) else ""
                    dist_match = re.match(r"([\d/]+\s*[fm])\s+(\w+)\s+([\d:.]+)", detail)
                    if dist_match:
                        race["distance"] = dist_match.group(1)
                        race["surface"] = dist_match.group(2)
                        race["time"] = dist_match.group(3)
                    races.append(race)
            i += 1
        if races:
            record["recent_races"] = races[:10]  # keep last 10

    return record


def parse_global_balance() -> Optional[str]:
    """Extract stable balance from any global page header."""
    for html_file in GLOBAL_DIR.glob("*.html"):
        s = read_html(html_file)
        if s is None:
            continue
        text = text_of(s)
        m = re.search(r"Balance:\s*\$?([\d.]+)", text)
        if m:
            return m.group(1)
    return None


def main() -> None:
    today = date.today().isoformat()
    out_dir = ROOT / "inputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "stable_snapshot.json"

    snapshot: Dict[str, Any] = {
        "date": today,
        "source": "02_export → 05_build_stable_snapshot",
        "horses": [],
    }

    # Parse balance from global pages
    balance = parse_global_balance()
    if balance:
        snapshot["balance"] = balance

    # Parse roster for quick summary
    roster = parse_roster_html()
    roster_by_name = {h.get("HORSE NAME", "").lower(): h for h in roster}

    # Parse individual horse directories
    if not RAW_ROOT.exists():
        print(f"No raw export data at {RAW_ROOT}")
        return

    horse_dirs = sorted([
        d for d in RAW_ROOT.iterdir()
        if d.is_dir() and d.name != "_global"
    ])

    for horse_dir in horse_dirs:
        try:
            record = parse_horse_dir(horse_dir)

            # Merge roster data if available
            roster_entry = roster_by_name.get(record["name"].lower(), {})
            if roster_entry:
                for key in ["RC", "S.A", "ST", "TRACK", "COND", "STAM", "CONSIST", "D", "LR", "LW", "MODE"]:
                    if key in roster_entry and key not in record:
                        record[f"roster_{key.lower()}"] = roster_entry[key]

            snapshot["horses"].append(record)
        except Exception as e:  # noqa: BLE001
            print(f"WARN: failed to parse {horse_dir.name}: {e}")

    out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Snapshot: {out_path}")
    print(f"  Date: {today}")
    print(f"  Horses: {len(snapshot['horses'])}")
    if balance:
        print(f"  Balance: ${balance}")


if __name__ == "__main__":
    main()
