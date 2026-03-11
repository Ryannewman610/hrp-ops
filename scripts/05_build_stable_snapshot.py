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

    # Works count — count only actual work rows (first cell matches DDMmmYY date)
    if works_s:
        work_date_re = re.compile(r"\d{1,2}[A-Za-z]{3}\d{2}")
        work_count = 0
        for tr in works_s.find_all("tr"):
            first_td = tr.find("td")
            if first_td and work_date_re.match(first_td.get_text(strip=True)):
                work_count += 1
        record["works_count"] = work_count

    # Conformation highlights
    for trait in ["Leg Style", "Legs", "Gait", "Frame Size"]:
        m = re.search(rf"{trait}[:\s]*([\w\s]+?)(?:\s{{2,}}|$)", conf_text)
        if m:
            record[f"conf_{trait.lower().replace(' ', '_')}"] = m.group(1).strip()

    # Accessories
    acc_items = []
    for item in ["Blinkers", "Bute", "Lasix", "Shadow Roll"]:
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

    # Parse race results from the profile HTML using the ACTUAL race table structure
    # Race rows contain DDMmmYY-#TRK identifiers (e.g. "4Mar26-5TUP") and have a specific
    # column layout with surface, distance, splits, race class link, SRF, field size,
    # and running position columns. The LAST running position is the finish position.
    if profile_s:
        race_id_re = re.compile(r"(\d{1,2}[A-Za-z]{3}\d{2})-(\d+)([A-Z]{2,4})")
        races: List[Dict[str, str]] = []
        seen_race_keys: set = set()

        # Race rows are deeply nested (table > tbody > tr > td > table > ...),
        # so search ALL <tr> elements in the document instead of traversing
        # table hierarchies.  Deduplicate by race-id text.
        for row in profile_s.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 10:
                continue

            # Extract text from first cell, check for race-id pattern
            first_cell_text = cells[0].get_text(strip=True)
            m = race_id_re.match(first_cell_text)
            if not m:
                continue

            # Deduplicate (nested tables can surface the same row multiple times)
            if first_cell_text in seen_race_keys:
                continue
            seen_race_keys.add(first_cell_text)

            # Confirm this is a race row (must have a race class link to race.aspx)
            race_link = row.find("a", href=re.compile(r"race\.aspx\?raceid="))
            if not race_link:
                continue

            # Parse race ID components
            date_str = m.group(1)  # e.g. "4Mar26"
            track = m.group(3)     # e.g. "TUP"

            # Convert date to sortable format
            date_match = re.match(r"(\d{1,2})([A-Za-z]{3})(\d{2})", date_str)
            iso_date = ""
            if date_match:
                months = {"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
                          "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}
                mo = months.get(date_match.group(2).capitalize(), "")
                if mo:
                    iso_date = f"20{date_match.group(3)}-{mo}-{int(date_match.group(1)):02d}"

            # Extract cell values, stripping superscript margin text
            # HRP uses <sup><font>...</font></sup> for margins (e.g. "3/4" lengths behind)
            # which get concatenated into the base text by get_text().
            def cell_text_clean(idx: int) -> str:
                """Get cell text with <sup> content removed."""
                if idx < len(cells):
                    from copy import copy
                    cell_copy = copy(cells[idx])
                    for sup in cell_copy.find_all("sup"):
                        sup.decompose()
                    return cell_copy.get_text(strip=True)
                return ""

            surface = cell_text_clean(1)   # "fst", "gd", etc.
            # Distance cell: <sup> contains actual distance info (e.g. 70 yards),
            # NOT margin text, so use raw text instead of cell_text_clean.
            distance = cells[2].get_text(strip=True) if len(cells) > 2 else ""

            # Get split times (cells 4-7, width=28 each)
            splits = []
            for si in range(4, 8):
                st = cell_text_clean(si)
                if st and re.match(r"[:0-9]", st):
                    splits.append(st)

            # Final time is the LAST split
            final_time = splits[-1] if splits else ""

            # Race class from link text: "OClm10/N2X-N", "Clm8.00(10-8)N3L", etc.
            race_class = race_link.get_text(strip=True) if race_link else ""

            # SRF rating: bold number in cell after race class (width=20)
            srf = cell_text_clean(9) if len(cells) > 9 else ""
            if not srf.isdigit():
                srf = ""

            # Field size: cell with width=16 (cell 10)
            # Running positions: cells with width=25 (cells 11+)
            field_size = ""
            finish_pos = ""

            found_field = False
            position_cells_list = []
            for ci, c in enumerate(cells):
                w = c.get("width", "")
                if w == "16" and not found_field:
                    ct = cell_text_clean(ci)
                    if ct.isdigit():
                        field_size = ct
                        found_field = True
                elif w == "25" and found_field:
                    ct = cell_text_clean(ci)
                    if re.match(r"\d", ct):
                        position_cells_list.append(ct)

            # The LAST position cell is the finish position
            if position_cells_list:
                last_pos = position_cells_list[-1]
                fp_match = re.match(r"(\d+)", last_pos)
                if fp_match:
                    finish_pos = fp_match.group(1)

            if not finish_pos or not field_size:
                continue

            races.append({
                "finish": finish_pos,
                "field": field_size,
                "date": date_str,
                "iso_date": iso_date,
                "track": track,
                "distance": distance.rstrip("f").strip() + "f" if distance and not distance.endswith("f") else distance,
                "surface": surface,
                "time": final_time,
                "srf": srf,
                "race_class": race_class,
            })

        # Sort by date descending and keep up to 10
        races.sort(key=lambda r: r.get("iso_date", ""), reverse=True)
        if races:
            record["recent_races"] = races[:10]

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
