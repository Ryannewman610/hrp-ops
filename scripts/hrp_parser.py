"""hrp_parser.py — Shared HRP Past Performance parser.

Provides the canonical PP parsing functions used by both the outcome
ingest (13_ingest_outcomes.py) and the model dataset builder
(09_build_model_dataset.py). Single source of truth for PP parsing.

Extracts: SRF speed figure, finish position, jockey, post position,
weight, odds, field size, condition/stamina, race class, surface, distance.
"""

import re
from pathlib import Path
from typing import Any, Dict, List

from bs4 import BeautifulSoup

SURFACE_MAP = {
    "fst": ("Fast", "Dirt"), "gd": ("Good", "Dirt"),
    "sly": ("Sloppy", "Dirt"), "mdy": ("Muddy", "Dirt"),
    "fm": ("Firm", "Turf"), "yl": ("Yielding", "Turf"), "sft": ("Soft", "Turf"),
}

CLASS_RE = re.compile(
    r'^(?:f)?(?:Clm|OClm|Alw|MdSpWt|MdClm|Md|Stk|Stakes|HCap)'
    r'[A-Za-z0-9./()_-]*$', re.IGNORECASE
)

MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
    "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def norm(name: str) -> str:
    """Normalize horse name for dedup."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_hrp_date(d: str) -> str:
    """Parse HRP date '14Feb26' to '2026-02-14'."""
    m = re.match(r"(\d{1,2})([A-Z][a-z]{2})(\d{2})", d.strip())
    if not m:
        return d
    day, mon, yr = m.groups()
    mo = MONTHS.get(mon, "00")
    return f"20{yr}-{mo}-{day.zfill(2)}"


def parse_distance_furlongs(dist: str) -> float:
    """Convert '5f', '6 1/2f', '1m', '1 1/16m' to furlongs."""
    if not dist:
        return 0.0
    dist = dist.strip().replace("T", "").strip()
    if dist.endswith("m"):
        body = dist[:-1].strip()
        parts = body.split()
        miles = float(parts[0])
        if len(parts) == 2 and "/" in parts[1]:
            n, d = parts[1].split("/")
            miles += float(n) / float(d)
        return miles * 8.0
    elif dist.endswith("f"):
        body = dist[:-1].strip()
        parts = body.split()
        furlongs = float(parts[0])
        if len(parts) == 2 and "/" in parts[1]:
            n, d = parts[1].split("/")
            furlongs += float(n) / float(d)
        return furlongs
    return 0.0


def extract_pp_races(text: str) -> List[Dict]:
    """Extract race results from HRP profile text with SRF speed figures.

    Returns list of dicts with keys: date, track, race_num, surface,
    surface_type, distance, race_class, srf, finish_position, jockey,
    post_position, weight, odds, race_condition, race_stamina, field_size.
    """
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    races = []

    # Find PP start lines: "19Feb26-6TUP"
    pp_starts = []
    for i, line in enumerate(lines):
        m = re.match(r'^(\d{1,2}[A-Z][a-z]{2}\d{2})-(\d+)([A-Z]{2,5})$', line)
        if m:
            pp_starts.append((i, m.group(1), m.group(2), m.group(3)))

    for idx, (start_i, date_str, race_num, track) in enumerate(pp_starts):
        end_i = pp_starts[idx + 1][0] if idx + 1 < len(pp_starts) else min(start_i + 40, len(lines))
        block = lines[start_i + 1: end_i]
        if len(block) < 5:
            continue

        race: Dict[str, Any] = {
            "date": parse_hrp_date(date_str),
            "track": track,
            "race_num": race_num,
        }

        # Surface
        if block[0].lower() in SURFACE_MAP:
            race["surface"], race["surface_type"] = SURFACE_MAP[block[0].lower()]

        # Distance
        dist = block[1] if len(block) > 1 else ""
        race["distance"] = dist
        race["distance_f"] = parse_distance_furlongs(dist) if dist else None

        # Race class
        class_idx = None
        for bi, bline in enumerate(block):
            if CLASS_RE.match(bline) or re.match(r'^(?:f)?(?:Clm|OClm|Alw|MdSpWt|Md)\d', bline):
                race["race_class"] = bline
                class_idx = bi
                break

        if class_idx is None:
            races.append(race)
            continue

        after = block[class_idx + 1:]

        # SRF = first token after class (2-3 digit number)
        srf_raw = after[0] if after else ""
        if re.match(r'^\d{2,3}$', srf_raw):
            val = int(srf_raw)
            if 50 <= val <= 120:
                race["srf"] = val
        elif srf_raw == '---':
            race["srf"] = None

        # Find jockey
        jockey_idx = None
        for ai, aline in enumerate(after):
            if aline.startswith("Jockey"):
                race["jockey"] = aline
                jockey_idx = ai
                break

        # Running line + finish between SRF and Jockey
        if jockey_idx is not None and jockey_idx > 1:
            running = after[1:jockey_idx]
            if running and re.match(r'^\d+$', running[0]):
                race["post_position"] = int(running[0])
            for token in reversed(running):
                if re.match(r'^\d+$', token):
                    val = int(token)
                    if 1 <= val <= 20:
                        race["finish_position"] = val
                        break

            # After jockey: weight, odds, condition-stamina, field size
            post_jockey = after[jockey_idx + 1:]
            for pj in post_jockey:
                if re.match(r'^\d{3}$', pj):
                    val = int(pj)
                    if 100 <= val <= 140:
                        race["weight"] = val
                elif re.match(r'^\*?[\d.]+$', pj) and '.' in pj:
                    race["odds"] = pj.lstrip('*')
                elif re.match(r'^\d{2,3}-\d{1,2}$', pj):
                    parts = pj.split('-')
                    race["race_condition"] = int(parts[0])
                    race["race_stamina"] = int(parts[1])
                elif re.match(r'^\d{1,2}$', pj):
                    val = int(pj)
                    if 2 <= val <= 16:
                        race["field_size"] = val

        # Claim info
        block_text = ' '.join(block)
        if 'Claimed' in block_text:
            claim_m = re.search(r'Claimed.*?\$(\d+(?:\.\d+)?)', block_text)
            if claim_m:
                race["claimed_for"] = float(claim_m.group(1))

        races.append(race)

    return races


def parse_profile_html(html_path: Path, horse_name: str) -> Dict:
    """Parse a horse's profile_allraces.html into structured data.

    Returns dict with keys: horse_name, life_record, best_srf, races.
    """
    if not html_path.exists():
        return {"horse_name": horse_name, "races": [], "life_record": {}}

    soup = BeautifulSoup(
        html_path.read_text(encoding="utf-8", errors="replace"),
        "html.parser"
    )
    text = soup.get_text('\n', strip=True)

    # LIFE record
    life = {}
    life_m = re.search(r'LIFE\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+(\d+)', text)
    if life_m:
        life = {
            "starts": int(life_m.group(1)),
            "wins": int(life_m.group(2)),
            "places": int(life_m.group(3)),
            "shows": int(life_m.group(4)),
            "earnings": float(life_m.group(5)),
            "best_srf": int(life_m.group(6)),
        }

    races = extract_pp_races(text)
    for r in races:
        r["horse_name"] = horse_name

    return {
        "horse_name": horse_name,
        "life_record": life,
        "best_srf": life.get("best_srf"),
        "races": races,
    }
