"""claiming_scout.py v2.1 -- Multi-dimensional claiming value analyzer.

Finds genuinely valuable claiming candidates by scoring horses across:
  - Age upside (young > old)
  - Breeding value (intact colts, fillies/mares > geldings)
  - Form trajectory via SRF speed figures (improving > declining)
  - Earnings efficiency (earnings-per-start vs claim price)
  - Class drops (ALW/Stakes dropping to CLM = opportunity)
  - Pedigree quality (known good sires, stud fee awareness)
  - State-bred bonus potential (bonus ROI calculation)
  - Claim history (previously claimed? price trajectory?)

Uses Playwright with saved auth for authenticated scraping.
SAFETY: Read-only. No form submissions. No claiming actions.
"""

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = ROOT / "inputs" / "export" / "auth.json"
CONFIG_PATH = ROOT / "scripts" / "claiming_config.json"
OUTPUT_DIR = ROOT / "outputs" / "claiming_scout"
BASE_URL = "https://www.horseracingpark.com"
DELAY_SECONDS = 3


#  Helpers 

def load_config() -> Dict[str, Any]:
    """Load claiming scout configuration."""
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    # Defaults
    return {
        "track_tiers": {
            "premium": ["GP", "SA", "KEE", "CD", "BEL", "AQU", "SAR", "DMR"],
            "good": ["TAM", "FG", "LRL", "OP", "PIM", "DEL", "PRX", "WO"],
            "fair": ["BTP", "MNR", "CT", "PEN", "MED", "TDN", "TP"],
            "skip": [],
        },
        "claim_price_range": [5, 100],
        "max_age": 6,
        "preferred_sex": ["filly", "mare", "colt"],
        "min_score_threshold": 40,
        "max_races_to_scout": 50,
        "max_horses_to_profile": 30,
        "known_good_sires": [],
        "scoring_weights": {
            "age_upside": 0.25,
            "breeding_value": 0.20,
            "form_trajectory": 0.20,
            "earnings_efficiency": 0.15,
            "class_drop": 0.10,
            "pedigree_conformation": 0.10,
        },
    }


def safe_goto(page, url: str) -> None:
    for attempt in range(1, 4):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return
        except Exception:
            if attempt < 3:
                print(f"  Retry {attempt}/3 for: {url}")
                time.sleep(2)
            else:
                raise


def polite_delay(seconds: int = DELAY_SECONDS):
    time.sleep(seconds)


def assert_logged_in(page) -> bool:
    """Check if the page shows authenticated content."""
    text = page.inner_text("body")[:500].lower()
    if "log in" in text and "password" in text and "register" in text:
        if "my account" not in text and "stables" not in text:
            return False
    return True


def get_track_tier(track: str, config: Dict) -> Optional[str]:
    """Return the tier for a track code, or None if it should be skipped."""
    tiers = config.get("track_tiers", {})
    for tier_name, tracks in tiers.items():
        if track.upper() in tracks:
            return tier_name
    return "fair"  # Default: include unknown tracks as fair


def parse_hrp_profile_header(text: str) -> Dict[str, Any]:
    """Parse HRP profile header line like 'B. f. 3 (Feb) 16.0h 1219lbs Active'.

    Sex codes: f=filly, m=mare, g=gelding, c=colt, h=stallion/horse
    Color codes: B.=bay, Ch.=chestnut, Dk B./Br.=dark bay, Bl.=black, Gr.=gray, Ro.=roan
    """
    result: Dict[str, Any] = {}

    # Match the header pattern: Color. sex. age (month) height weight status
    m = re.search(
        r"(?:B\.|Ch\.|Dk B\.|Br\.|Bl\.|Gr\.|Ro\.)\s*"
        r"([fmgch])\.\s*(\d+)\s*\(",
        text, re.IGNORECASE,
    )
    if m:
        sex_code = m.group(1).lower()
        sex_map = {"f": "filly", "m": "mare", "g": "gelding", "c": "colt", "h": "stallion"}
        result["sex"] = sex_map.get(sex_code, "unknown")
        result["age"] = int(m.group(2))

    return result


def parse_hrp_life_record(text: str) -> Dict[str, Any]:
    """Parse HRP LIFE record line like 'LIFE 9 2 1 2 103.66 90'."""
    m = re.search(r"LIFE\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+(\d+)", text)
    if m:
        return {
            "starts": int(m.group(1)),
            "wins": int(m.group(2)),
            "places": int(m.group(3)),
            "shows": int(m.group(4)),
            "earnings": float(m.group(5)),
            "best_srf": int(m.group(6)),
        }
    return {}


def parse_hrp_pp_lines(text: str) -> List[Dict]:
    """Parse HRP past-performance lines to extract SRF, class, and finish data.

    Example line:
    7Feb26-2AQU fst 7f :23 :463 1:103 1:223 fEastVw135.00 91 2 2hd 2no 31/2 41
    The number after the race description (91) is the SRF speed figure.
    """
    races = []
    # Match PP lines: date-track surface distance ... class_and_purse SRF ...
    pp_pattern = re.compile(
        r"(\d{1,2}\w{3}\d{2})-(\d+)(\w{2,4})\s+"  # date-race#track
        r"(\w+)\s+"                                  # surface
        r"([\d\s/:f]+[fmFM])\s+"                     # distance + fractions
        r"(.+?)\s+"                                   # class/cond
        r"(\d{2,3})\s+"                               # SRF speed figure
        r"(\d+)\s+"                                   # post position or field
        r"(.+)$",                                     # running line + finish
        re.MULTILINE,
    )

    # Simpler fallback: just grab SRF figures from lines with track codes
    # HRP format: lines containing track codes (AQU, SA, GP, etc.) with SRF
    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) < 30:
            continue

        # Look for PP line pattern: starts with date like "7Feb26" or "28Dec25"
        date_m = re.match(r"(\d{1,2}\w{3}\d{2})-(\d+)(\w{2,4})", line)
        if not date_m:
            continue

        race_info: Dict[str, Any] = {
            "date": date_m.group(1),
            "race_num": date_m.group(2),
            "track": date_m.group(3),
        }

        # Extract surface
        surf_m = re.search(r"\b(fst|gd|sly|mdy|fm|yl|sft)\b", line, re.IGNORECASE)
        if surf_m:
            surf_map = {"fst": "dirt", "gd": "dirt", "sly": "dirt", "mdy": "dirt",
                        "fm": "turf", "yl": "turf", "sft": "turf"}
            race_info["surface"] = surf_map.get(surf_m.group(1).lower(), "dirt")

        # Extract class/condition (e.g., fEastVw135.00, fClm75.00, Alw46.00N1X, MdSpWt8.00)
        class_m = re.search(
            r"((?:f)?(?:Clm|OClm|Alw|MdSpWt|Md|Stk|Stakes|[A-Z][a-z]+)[\w./]*[\d.]+(?:N\dX)?(?:-N)?)",
            line,
        )
        if class_m:
            race_info["class"] = class_m.group(1)

        # Extract SRF speed figure -- appears after the race class description
        # IMPORTANT: Must NOT match fractional times (preceded by :) or purse amounts
        # HRP PP format: ...fClm14.00(16-14)N2L 89 1 44 44 22 13/4
        #                                       ^^-- SRF is here
        # Strategy: find the class/condition marker, then look for 2-digit number after it
        if class_m:
            after_class = line[class_m.end():]
            srf_m = re.search(r"^\s*(\d{2,3})\s+\d", after_class)
            if srf_m:
                num = int(srf_m.group(1))
                if 70 <= num <= 110:
                    race_info["speed"] = num
        else:
            # Fallback: find standalone 2-digit numbers NOT preceded by : or .
            srf_candidates = re.findall(r"(?<![:.])(?<!\d)\b(\d{2})\b(?!\d)", line)
            for num_str in srf_candidates:
                num = int(num_str)
                if 80 <= num <= 105:  # Tighter range for fallback
                    race_info["speed"] = num
                    break

        # Extract finish position -- last number on the line or before "Jockey"
        finish_section = line.split("Jockey")[0] if "Jockey" in line else line
        running_m = re.findall(r"(\d+)(?:hd|nk|no|\d*/\d+)?\s*$", finish_section)
        if running_m:
            race_info["finish"] = int(running_m[-1])

        # Detect if this was a claim
        if "claimed" in line.lower():
            claim_m = re.search(r"[Cc]laimed.*?\$(\d+(?:\.\d+)?)", line)
            if claim_m:
                race_info["claimed_price"] = float(claim_m.group(1))

        races.append(race_info)

    return races


def parse_claim_history(text: str) -> List[Dict]:
    """Extract claim history from profile text.

    Looks for lines like 'Claimed from Angelos Stable for $15.00'
    or 'Claimed for $40.00, $6.00, $7.50'
    """
    claims = []
    for m in re.finditer(r"[Cc]laimed\s+(?:from\s+(.+?)\s+)?for\s+\$(\d+(?:\.\d+)?)", text):
        claim = {"price": float(m.group(2))}
        if m.group(1):
            claim["from_stable"] = m.group(1).strip()
        claims.append(claim)
    return claims


def parse_stud_fee(sire_line: str) -> Optional[float]:
    """Extract stud fee from sire line like 'Sire: Commanding $10.00'."""
    m = re.search(r"\$(\d+(?:\.\d+)?)", sire_line)
    if m:
        return float(m.group(1))
    return None


def parse_bred_state(text: str) -> str:
    """Extract breeding state from HRP profile.

    Looks for 'Br: Stable (NY*)' or 'Br: Stable (Cal)' patterns.
    """
    m = re.search(r"Br:\s*.+?\(([A-Za-z*]+)\)", text)
    if m:
        state = m.group(1).rstrip("*").strip()
        # Normalize state codes
        state_map = {
            "NY": "NY", "Cal": "CA", "Fla": "FL", "Ky": "KY", "Tex": "TX",
            "Pa": "PA", "NJ": "NJ", "La": "LA", "ON": "ON", "BC": "BC",
            "NM": "NM", "WV": "WV", "AZ": "AZ",
        }
        return state_map.get(state, state.upper())
    return ""


# State-bred bonus percentages (from official rules)
STATEBRED_BONUSES = {
    "NY": {"sire_in": 0.15, "sire_out": 0.075},
    "CA": {"sire_in": 0.30, "sire_out": 0.15},
    "FL": {"sire_in": 0.20, "sire_out": 0.10},
    "KY": {"sire_in": 0.40, "sire_out": 0.20},
    "PA": {"sire_in": 0.20, "sire_out": 0.10},
    "ON": {"sire_in": 0.15, "sire_out": 0.075},
    "LA": {"sire_in": 0.15, "sire_out": 0.075},
    "NJ": {"sire_in": 0.15, "sire_out": 0.075},
    "TX": {"sire_in": 0.15, "sire_out": 0.075},
    "NM": {"sire_in": 0.20, "sire_out": 0.10},
    "BC": {"sire_in": 0.30, "sire_out": 0.15},
}


def estimate_statebred_bonus(bred_state: str, avg_purse: float = 20.0) -> float:
    """Estimate annual state-bred bonus value."""
    if not bred_state or bred_state not in STATEBRED_BONUSES:
        return 0.0
    bonus_pct = STATEBRED_BONUSES[bred_state]["sire_out"]  # Conservative estimate
    # Assume ~8 races/year, earning ~30% of purse on average
    return avg_purse * 8 * 0.30 * bonus_pct


def parse_age_from_text(text: str) -> Optional[int]:
    """Extract horse age from profile text."""
    # Try HRP header format first: "B. f. 3 (Feb)"
    header = parse_hrp_profile_header(text)
    if "age" in header:
        return header["age"]

    m = re.search(r"(\d+)\s*(?:year|yr|yo)", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"Age:\s*(\d+)", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"Foaled:\s*(\d+)/(\d{4})", text, re.IGNORECASE)
    if m:
        foal_year = int(m.group(2))
        return date.today().year - foal_year
    return None


def parse_sex_from_text(text: str) -> str:
    """Extract horse sex from profile text."""
    # Try HRP header format first
    header = parse_hrp_profile_header(text)
    if "sex" in header:
        return header["sex"]

    text_lower = text.lower()
    for sex_word in ["filly", "mare", "gelding", "colt", "stallion"]:
        if sex_word in text_lower:
            return sex_word

    m = re.search(r"\b(F|M|G|C|H)\b", text[:200])
    if m:
        sex_map = {"F": "filly", "M": "mare", "G": "gelding", "C": "colt", "H": "stallion"}
        return sex_map.get(m.group(1), "unknown")
    return "unknown"


def parse_record(text: str) -> Dict[str, int]:
    """Parse race record (starts-wins-places-shows) from text."""
    # Try HRP LIFE record first
    life = parse_hrp_life_record(text)
    if life:
        return {
            "starts": life["starts"],
            "wins": life["wins"],
            "places": life["places"],
            "shows": life["shows"],
        }

    m = re.search(r"(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\s*-\s*(\d+)", text)
    if m:
        return {
            "starts": int(m.group(1)),
            "wins": int(m.group(2)),
            "places": int(m.group(3)),
            "shows": int(m.group(4)),
        }
    return {"starts": 0, "wins": 0, "places": 0, "shows": 0}


def parse_earnings(text: str) -> float:
    """Extract total earnings from text."""
    # Try HRP LIFE record first
    life = parse_hrp_life_record(text)
    if life and "earnings" in life:
        return life["earnings"]

    m = re.search(r"(?:Earnings?|Earned).*?\$\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if m:
        return float(m.group(1).replace(",", ""))
    return 0.0


def parse_sire(text: str) -> str:
    """Extract sire name from profile text (without stud fee)."""
    m = re.search(r"Sire:\s*(.+?)(?:\$[\d.]+)?\s*(?:\n|$)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def is_gelded(text: str) -> bool:
    """Check if the horse is a gelding."""
    return "gelding" in text.lower() or bool(re.search(r"\b[gG]\. \d", text))

#  Scoring Engine 

# -- Dynamic weight profiles per horse type --
WEIGHT_PROFILES = {
    "racing_machine": {  # Geldings -- pure racing ROI, no breeding exit
        "label": "[RACING] Racing Machine",
        "form_trajectory": 0.25,
        "conformation": 0.15,
        "class_drop": 0.15,
        "earnings_efficiency": 0.15,
        "works": 0.10,
        "age_upside": 0.10,
        "pedigree": 0.05,
        "statebred": 0.05,
        "breeding_value": 0.00,  # Geldings can't breed
    },
    "broodmare_prospect": {  # Fillies/Mares -- breeding exit strategy
        "label": "[BREED] Broodmare Prospect",
        "breeding_value": 0.15,
        "pedigree": 0.15,
        "conformation": 0.12,  # Good WR = good genes to pass
        "form_trajectory": 0.12,
        "age_upside": 0.10,
        "statebred": 0.10,
        "class_drop": 0.08,
        "works": 0.08,
        "earnings_efficiency": 0.10,
    },
    "stallion_prospect": {  # Intact colts/stallions -- highest breeding ceiling
        "label": "[STUD] Stallion Prospect",
        "pedigree": 0.20,
        "breeding_value": 0.15,
        "conformation": 0.12,
        "form_trajectory": 0.12,
        "age_upside": 0.10,
        "class_drop": 0.08,
        "works": 0.08,
        "earnings_efficiency": 0.08,
        "statebred": 0.07,
    },
}


def get_horse_profile(sex: str) -> str:
    """Determine which weight profile to use based on sex."""
    sex_lower = sex.lower()
    if sex_lower == "gelding":
        return "racing_machine"
    elif sex_lower in ("filly", "mare"):
        return "broodmare_prospect"
    elif sex_lower in ("colt", "stallion"):
        return "stallion_prospect"
    return "broodmare_prospect"  # Default: assume breedable


def parse_wr_meters(text: str) -> Dict[str, Any]:
    """Parse WR conformation meters from HRP profile.

    Format: WR: 101 (100,101,100,100)
    Or: WR: NR (not rated)
    """
    result: Dict[str, Any] = {"wr": None, "meters": [], "rated": False}

    m = re.search(r"WR:\s*(\d+)\s*\(([\d,]+)\)", text)
    if m:
        result["wr"] = int(m.group(1))
        result["meters"] = [int(x.strip()) for x in m.group(2).split(",")]
        result["rated"] = True
        return result

    # Check for NR (Not Rated)
    if re.search(r"WR:\s*NR", text, re.IGNORECASE):
        result["wr"] = None
        result["rated"] = False

    return result


def parse_timed_works(text: str) -> List[Dict]:
    """Parse timed work data from HRP profile text.

    Work lines look like:
    Work: 5f :584 BTP fst 1/5
    Or they may appear as part of the profile workout section.
    """
    works = []

    # Pattern 1: Explicit work lines
    work_pattern = re.compile(
        r"(?:Work|Wk).*?"  # Work prefix
        r"(\d+[fmFM])\s*"  # Distance (5f, 1m, etc.)
        r":?(\d{2,3}(?:\.\d)?)?"  # Time (:584, 1:032, etc.)
        r".*?([A-Z]{2,4})"  # Track code
        r".*?(fst|gd|fm|mdy|sly|sft|yl)"  # Surface
        r".*?(\d+/\d+)?",  # Ranking (1/5, 3/12)
        re.IGNORECASE,
    )
    for m in work_pattern.finditer(text):
        work = {
            "distance": m.group(1),
            "time": m.group(2) or "",
            "track": m.group(3),
            "surface": m.group(4),
            "ranking": m.group(5) or "",
        }
        works.append(work)

    # Pattern 2: Bullet/bullet-style work lines from profile
    # "5f fst :591 (8/42)" or "5f :584 H" (H=handily, B=breezing)
    bullet_pattern = re.compile(
        r"[]?\s*(\d+[fmFM])\s+"
        r"(?:fst|gd|fm|mdy)?\s*"
        r":?(\d{2,3}(?:\.\d)?)"
        r"(?:\s*[HBhb])?"
        r"(?:\s*\((\d+/\d+)\))?",
    )
    for m in bullet_pattern.finditer(text):
        work = {
            "distance": m.group(1),
            "time": m.group(2) or "",
            "ranking": m.group(3) or "",
        }
        # Avoid duplicates
        if not any(w["time"] == work["time"] and w["distance"] == work["distance"] for w in works):
            works.append(work)

    return works


def score_conformation(wr_data: Dict) -> float:
    """Score 0-100 based on WR conformation meters.

    WR reflects the horse's developed physical ability.
    Higher WR = horse has been worked into better shape = higher ceiling.
    NR = untested = risk discount.
    """
    if not wr_data.get("rated", False) or wr_data.get("wr") is None:
        return 25.0  # NR = unknown, significant risk

    wr = wr_data["wr"]
    if wr >= 103:
        return 100.0  # Elite -- exceptional development
    elif wr >= 101:
        return 90.0   # Very well developed
    elif wr == 100:
        return 70.0   # Average baseline
    elif wr >= 98:
        return 50.0   # Below average
    elif wr >= 95:
        return 30.0   # Poor development
    else:
        return 10.0   # Under-developed


def score_works(works: List[Dict], recent_races: List[Dict]) -> float:
    """Score 0-100 based on timed workout activity.

    Recent works = actively managed horse = positive signal.
    No works = owner may have abandoned = risk.
    Works quality (ranking) also matters.
    """
    if not works and not recent_races:
        return 15.0  # No data at all

    if not works:
        # No explicit works found, but has races -- race itself is a "work"
        if recent_races:
            return 50.0  # Racing substitutes for working
        return 20.0

    # Score based on number and recency
    num_works = len(works)

    if num_works >= 5:
        base = 85.0  # Very active workout program
    elif num_works >= 3:
        base = 70.0
    elif num_works >= 1:
        base = 55.0
    else:
        base = 30.0

    # Bonus for good rankings (if available)
    for work in works[:3]:
        ranking = work.get("ranking", "")
        if ranking:
            parts = ranking.split("/")
            if len(parts) == 2:
                try:
                    pos, total = int(parts[0]), int(parts[1])
                    if total > 0 and pos <= max(1, total // 4):
                        base = min(100, base + 10)  # Top 25% ranking
                except ValueError:
                    pass

    return min(100.0, base)


def generate_risk_flags(horse: Dict) -> List[str]:
    """Generate risk warning flags that identify potential problems."""
    flags = []
    wr_data = horse.get("wr_data", {})
    works = horse.get("works", [])
    age = horse.get("age")
    claim_history = horse.get("claim_history", [])
    sex = horse.get("sex", "").lower()
    record = horse.get("record", {})
    starts = record.get("starts", 0)
    wins = record.get("wins", 0)

    # WR: NR -- unknown ceiling
    if not wr_data.get("rated", False):
        flags.append("[RISK] WR: NR -- unknown physical ceiling")

    # No recent works
    if not works and not horse.get("recent_races"):
        flags.append("[RISK] No works or races found -- may need reconditioning")

    # Old horse
    if age and age >= 7:
        flags.append(f"[WARN] Age {age} -- limited earning window remaining")

    # Gelding with no upside
    if sex == "gelding" and age and age >= 6:
        flags.append("[WARN] Older gelding -- no breeding exit, declining asset")

    # Frequently claimed -- market keeps rejecting
    if len(claim_history) >= 3:
        flags.append(f"[WARN] Claimed {len(claim_history)}x -- market repeatedly drops")

    # 0-for-many -- chronic loser
    if starts >= 10 and wins == 0:
        flags.append(f"[WARN] 0-for-{starts} -- has never won")

    # Low WR
    if wr_data.get("rated") and wr_data.get("wr", 100) < 98:
        flags.append(f"[WARN] WR {wr_data['wr']} -- below average development")

    return flags


def estimate_roi(horse: Dict) -> Dict[str, float]:
    """Estimate 12-month ROI for a claimed horse.

    Returns projected racing earnings, breeding value, and ROI ratio.
    """
    claim_price = horse.get("claim_price", 0)
    if claim_price <= 0:
        return {"racing": 0, "breeding": 0, "statebred": 0, "total": 0, "roi_pct": 0}

    sex = horse.get("sex", "").lower()
    age = horse.get("age")
    earnings = horse.get("earnings", 0)
    record = horse.get("record", {})
    starts = record.get("starts", 0)
    bred_state = horse.get("bred_state", "")
    stud_fee = horse.get("stud_fee")

    # Racing ROI: est earnings per start  projected starts/year
    if starts > 0:
        avg_earn_per_start = earnings / starts
    else:
        avg_earn_per_start = claim_price * 0.2  # Conservative estimate

    est_starts_per_year = 8  # ~8 races/year is typical
    if age and age >= 6:
        est_starts_per_year = 6  # Older horses race less

    racing_roi = avg_earn_per_start * est_starts_per_year

    # State-bred bonus ROI
    statebred_roi = estimate_statebred_bonus(bred_state, claim_price)

    # Breeding ROI (fillies/mares only -- foal value estimate)
    breeding_roi = 0.0
    if sex in ("filly", "mare") and age and age <= 12:
        # Foal value  function of sire quality + mare's racing record
        base_foal_value = 5.0  # Minimum foal sale value
        if stud_fee and stud_fee >= 10:
            base_foal_value = 15.0
        elif stud_fee and stud_fee >= 5:
            base_foal_value = 10.0

        # Winning mares produce more valuable foals
        win_pct = (record.get("wins", 0) / max(starts, 1)) if starts > 0 else 0
        if win_pct > 0.3:
            base_foal_value *= 1.5
        elif win_pct > 0.15:
            base_foal_value *= 1.2

        breeding_roi = base_foal_value  # 1 foal per year

    elif sex in ("colt", "stallion") and age and age <= 8:
        # Stallion stud fee potential (if horse has top record)
        if record.get("wins", 0) >= 3 and earnings > 50:
            breeding_roi = 10.0  # Estimated annual stud income
        else:
            breeding_roi = 3.0

    total_roi = racing_roi + statebred_roi + breeding_roi
    roi_pct = ((total_roi - claim_price) / claim_price * 100) if claim_price > 0 else 0

    return {
        "racing": round(racing_roi, 2),
        "breeding": round(breeding_roi, 2),
        "statebred": round(statebred_roi, 2),
        "total": round(total_roi, 2),
        "roi_pct": round(roi_pct, 1),
    }

def score_age_upside(age: Optional[int]) -> float:
    """Score 0-100 based on age. Younger = more upside."""
    if age is None:
        return 30.0
    scores = {2: 100, 3: 100, 4: 80, 5: 50, 6: 20, 7: 5, 8: 0}
    return float(scores.get(age, 0 if age > 8 else 30))


def score_breeding_value(sex: str, age: Optional[int]) -> float:
    """Score 0-100 based on breeding potential."""
    sex_lower = sex.lower()
    if sex_lower == "colt" or sex_lower == "stallion":
        # Intact males have highest breeding value
        base = 100.0
    elif sex_lower in ("filly", "mare"):
        # Fillies/mares have broodmare value
        base = 75.0
    elif sex_lower == "gelding":
        # No breeding value
        return 0.0
    else:
        base = 30.0

    # Young breeders are worth more
    if age and age > 10:
        base *= 0.3
    elif age and age > 7:
        base *= 0.6

    return base


def score_form_trajectory(races: List[Dict]) -> float:
    """Score 0-100 based on recent form trajectory using SRF speed figures.
    Improving = high score, declining = low score.
    Now properly weights SRF data when available.
    """
    if not races or len(races) < 2:
        return 50.0  # Unknown

    # Extract SRF speed figures from recent races
    speeds = []
    for race in races[:8]:
        speed = race.get("speed", 0)
        if speed and 50 <= speed <= 120:  # Validate SRF range
            speeds.append(float(speed))

    if len(speeds) >= 3:
        # Split into recent (first 2-3) vs older
        mid = min(3, len(speeds) // 2 + 1)
        recent_avg = sum(speeds[:mid]) / mid
        older_avg = sum(speeds[mid:]) / max(len(speeds[mid:]), 1)

        if older_avg > 0:
            improvement = (recent_avg - older_avg) / older_avg * 100
            # More granular mapping for SRF-based analysis
            if improvement > 5:
                return 95.0   # Strongly improving -- big SRF jump
            elif improvement > 3:
                return 85.0
            elif improvement > 1:
                return 70.0
            elif improvement > -1:
                return 55.0   # Stable form
            elif improvement > -3:
                return 35.0   # Slightly declining
            elif improvement > -5:
                return 20.0
            else:
                return 10.0   # Steep decline

        # If all speeds are high (90+), that's still good form
        if recent_avg >= 95:
            return 80.0
        elif recent_avg >= 90:
            return 65.0

    elif len(speeds) == 2:
        if speeds[0] > speeds[1]:
            return 70.0  # Most recent faster
        elif speeds[0] == speeds[1]:
            return 55.0
        else:
            return 35.0  # Slower

    # Fall back to finish positions
    finishes = []
    for race in races[:6]:
        finish = race.get("finish", 0)
        if finish:
            finishes.append(int(finish))

    if len(finishes) >= 2:
        mid = min(3, len(finishes) // 2 + 1)
        recent_avg = sum(finishes[:mid]) / mid
        older_avg = sum(finishes[mid:]) / max(len(finishes[mid:]), 1)
        if recent_avg < older_avg:
            return 70.0
        elif recent_avg == older_avg:
            return 50.0
        else:
            return 30.0

    return 50.0


def score_earnings_efficiency(earnings: float, starts: int, claim_price: float) -> float:
    """Score 0-100 based on earnings per start relative to claim price."""
    if starts == 0 or claim_price == 0:
        return 30.0

    earnings_per_start = earnings / starts
    ratio = earnings_per_start / claim_price

    if ratio > 2.0:
        return 95.0
    elif ratio > 1.0:
        return 80.0
    elif ratio > 0.5:
        return 60.0
    elif ratio > 0.2:
        return 40.0
    else:
        return 15.0


def score_class_drop(race_history_text: str, current_race_type: str) -> float:
    """Score 0-100 based on class drop detection.
    Horse dropping from higher class = opportunity.
    """
    text_lower = race_history_text.lower()
    current_lower = current_race_type.lower()

    # Check if horse has run in higher class races
    higher_markers = ["allowance", "alw", "stakes", "stk", "graded"]
    has_run_higher = any(m in text_lower for m in higher_markers)

    is_claiming_now = "claim" in current_lower or "clm" in current_lower

    if has_run_higher and is_claiming_now:
        # Count how many higher-class finishes
        alw_count = text_lower.count("allowance") + text_lower.count("alw")
        stk_count = text_lower.count("stakes") + text_lower.count("stk")

        if stk_count > 0:
            return 90.0  # Stakes horse dropping to CLM -- major flag
        elif alw_count >= 3:
            return 75.0  # Consistent ALW horse dropping
        elif alw_count >= 1:
            return 60.0  # Some ALW experience
        return 50.0

    return 30.0  # No clear class drop


def score_pedigree(sire: str, stud_fee: Optional[float], config: Dict) -> float:
    """Score 0-100 based on sire quality and stud fee."""
    known_sires = config.get("known_good_sires", [])
    score = 30.0  # default

    if sire:
        sire_lower = sire.lower().strip()
        for ks in known_sires:
            if ks.lower() in sire_lower or sire_lower in ks.lower():
                score = 90.0
                break

    # Stud fee is a strong signal of sire quality
    if stud_fee is not None:
        if stud_fee >= 15:
            score = max(score, 95.0)
        elif stud_fee >= 10:
            score = max(score, 85.0)
        elif stud_fee >= 5:
            score = max(score, 65.0)
        elif stud_fee >= 2:
            score = max(score, 50.0)
        else:
            score = max(score, 35.0)  # $1 stud fee = low-quality sire

    return score


def score_statebred_value(bred_state: str, claim_price: float) -> float:
    """Score 0-100 based on state-bred bonus potential."""
    if not bred_state or bred_state not in STATEBRED_BONUSES:
        return 20.0  # No bonus

    bonus = STATEBRED_BONUSES[bred_state]
    pct = bonus["sire_out"]  # Conservative

    # Higher bonus states score higher
    if pct >= 0.20:   # KY 20/40%, CA 15/30%, BC 15/30%
        return 95.0
    elif pct >= 0.10:  # FL 10/20%, PA 10/20%, NM 10/20%
        return 75.0
    elif pct >= 0.075: # NY 7.5/15%, ON, LA, NJ, TX
        return 60.0
    return 30.0


def compute_composite_score(horse: Dict, config: Dict) -> float:
    """Compute final composite value score (0-100).

    v2.2: Dynamic weight profiles based on horse sex/type.
    Geldings get racing-focused weights, fillies/mares get breeding-focused,
    colts/stallions get stallion-prospect weights.
    """
    age = horse.get("age")
    sex = horse.get("sex", "unknown")
    earnings = horse.get("earnings", 0)
    record = horse.get("record", {})
    starts = record.get("starts", 0)
    claim_price = horse.get("claim_price", 0)
    sire = horse.get("sire", "")
    stud_fee = horse.get("stud_fee")
    races = horse.get("recent_races", [])
    race_text = horse.get("profile_text", "")
    race_type = horse.get("race_type", "")
    bred_state = horse.get("bred_state", "")
    claim_history = horse.get("claim_history", [])
    wr_data = horse.get("wr_data", {})
    works = horse.get("works", [])

    # Determine scoring profile
    profile_key = get_horse_profile(sex)
    profile = WEIGHT_PROFILES[profile_key]
    horse["profile_label"] = profile["label"]

    # Compute individual dimension scores
    scores = {
        "age_upside": score_age_upside(age),
        "breeding_value": score_breeding_value(sex, age),
        "form_trajectory": score_form_trajectory(races),
        "earnings_efficiency": score_earnings_efficiency(earnings, starts, claim_price),
        "class_drop": score_class_drop(race_text, race_type),
        "pedigree": score_pedigree(sire, stud_fee, config),
        "statebred": score_statebred_value(bred_state, claim_price),
        "conformation": score_conformation(wr_data),
        "works": score_works(works, races),
    }

    # Apply dynamic weights
    composite = sum(
        scores[dim] * profile.get(dim, 0)
        for dim in scores
    )

    # Claim history bonus (flat, applied after weights)
    claim_bonus = 0.0
    if claim_history:
        max_claimed = max(c.get("price", 0) for c in claim_history)
        if max_claimed > 0 and claim_price > 0:
            if max_claimed < claim_price:
                claim_bonus = 8.0  # Being sold UP in price
            elif max_claimed > claim_price * 2:
                claim_bonus = 4.0  # Steep drop -- opportunity?
    composite += claim_bonus

    # Risk flag penalties
    risk_flags = generate_risk_flags(horse)
    risk_penalty = min(len(risk_flags) * 3, 15)  # Max 15 point penalty
    composite -= risk_penalty
    composite = max(0, min(100, composite))  # Clamp to 0-100

    # ROI estimation
    roi = estimate_roi(horse)
    horse["roi"] = roi
    horse["risk_flags"] = risk_flags

    # Store all scores
    scores["claim_bonus"] = round(claim_bonus, 1)
    scores["risk_penalty"] = round(-risk_penalty, 1)
    scores["composite"] = round(composite, 1)
    horse["scores"] = {k: round(v, 1) for k, v in scores.items()}
    horse["weight_profile"] = profile_key

    return composite


#  Scraping Functions 

def scrape_filtered_races(page, config: Dict) -> List[Dict]:
    """Navigate to race calendar, filter for ALL CLM, extract race list."""
    print("PHASE 1: Filtering race calendar for claiming races...")
    cal_url = f"{BASE_URL}/races/index.aspx"
    safe_goto(page, cal_url)
    polite_delay()

    if not assert_logged_in(page):
        print("  ERROR: Not logged in. Run 01_login_save_state.py first.")
        return []

    # Set RaceType dropdown to ALL CLM and click Filter
    page.evaluate("""
        () => {
            const selects = document.querySelectorAll('select');
            for (const sel of selects) {
                const options = Array.from(sel.options);
                for (const opt of options) {
                    if (opt.text === 'ALL CLM' || opt.text.includes('ALL CLM')) {
                        sel.value = opt.value;
                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                        break;
                    }
                }
            }
        }
    """)
    polite_delay(1)

    # Click Filter button
    page.evaluate("""
        () => {
            const btns = document.querySelectorAll('input[type="submit"], input[type="button"]');
            for (const btn of btns) {
                if (btn.value && btn.value.toLowerCase().includes('filter')) {
                    btn.click();
                    break;
                }
            }
        }
    """)
    page.wait_for_load_state("domcontentloaded", timeout=30000)
    polite_delay()

    # Extract race data via JS
    raw_races = page.evaluate("""
        () => {
            const races = [];
            const body = document.body.innerText || '';

            // Get pagination info
            const pagMatch = body.match(/Showing\\s+(\\d+)\\s+through\\s+(\\d+)\\s+of\\s+(\\d+)/i);
            const total = pagMatch ? parseInt(pagMatch[3]) : 0;

            // Find race entry links and their containing rows
            const allLinks = document.querySelectorAll('a[href*="entry.aspx"]');
            for (const link of allLinks) {
                const href = link.getAttribute('href') || '';
                const raceIdMatch = href.match(/raceid=(\\d+)/i);
                if (!raceIdMatch) continue;

                // Walk up to find the race block (table rows)
                let container = link.closest('table') || link.parentElement;
                let blockText = container ? container.innerText : '';

                // Parse race details from block text
                const dateMatch = blockText.match(/(\\d+\\/\\d+\\/\\d+)/);
                const trackMatch = blockText.match(/\\b([A-Z]{2,4})\\b.*Race #(\\d+)/);
                const distMatch = blockText.match(/(\\d+(?:\\s*\\d+\\/\\d+)?[fmFM]|\\d+\\s*(?:1\\/[248])?[mM])/);
                const surfMatch = blockText.match(/\\b(Dirt|Turf)\\b/i);
                const typeMatch = blockText.match(/\\b(Maiden Claiming|Claiming|Allowance\\/Claiming)\\b/i);
                const clmMatch = blockText.match(/Claiming Price \\$([\\.\\d,]+)/i);
                const purseMatch = blockText.match(/Purse \\$([\\.\\d,]+)/i);
                const ownersMatch = blockText.match(/Owners:\\s*(\\d+)/i);
                const fieldMatch = blockText.match(/Field Size:\\s*(\\d+)/i);
                const condMatch = blockText.match(/For\\s+(.+?)(?:Weight|Preference)/s);

                races.push({
                    race_id: raceIdMatch[1],
                    entry_url: href,
                    date: dateMatch ? dateMatch[1] : '',
                    track: trackMatch ? trackMatch[1] : '',
                    race_num: trackMatch ? trackMatch[2] : '',
                    distance: distMatch ? distMatch[1] : '',
                    surface: surfMatch ? surfMatch[1] : '',
                    race_type: typeMatch ? typeMatch[1] : '',
                    claim_price: clmMatch ? parseFloat(clmMatch[1].replace(',', '')) : 0,
                    purse: purseMatch ? parseFloat(purseMatch[1].replace(',', '')) : 0,
                    owners: ownersMatch ? parseInt(ownersMatch[1]) : 0,
                    field_size: fieldMatch ? parseInt(fieldMatch[1]) : 0,
                    conditions: condMatch ? condMatch[1].trim().substring(0, 200) : '',
                    block_text: blockText.substring(0, 400),
                });
            }

            return { races: races, total_claiming: total };
        }
    """)

    total = raw_races.get("total_claiming", 0)
    races = raw_races.get("races", [])
    print(f"  Total claiming races today: {total}")
    print(f"  Extracted from page 1: {len(races)} races")

    # Pagination: if there are more pages, fetch them
    max_pages = config.get("max_calendar_pages", 5)
    if total > len(races) and max_pages > 1:
        for page_num in range(2, max_pages + 1):
            print(f"  Fetching page {page_num}...")
            try:
                # Click the Next page link
                next_clicked = page.evaluate("""
                    () => {
                        const links = document.querySelectorAll('a');
                        for (const a of links) {
                            const text = a.innerText.trim();
                            if (text === 'Next' || text === '>' || text === '>>') {
                                a.click();
                                return true;
                            }
                        }
                        // Try page number link
                        for (const a of links) {
                            if (a.innerText.trim() === '""" + str(page_num) + """') {
                                a.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                if not next_clicked:
                    print(f"    No page {page_num} link found, stopping pagination.")
                    break
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                polite_delay(2)

                # Re-extract races from this page
                more = page.evaluate("""
                    () => {
                        const races = [];
                        const allLinks = document.querySelectorAll('a[href*="entry.aspx"]');
                        for (const link of allLinks) {
                            const href = link.getAttribute('href') || '';
                            const raceIdMatch = href.match(/raceid=(\\d+)/i);
                            if (!raceIdMatch) continue;
                            let container = link.closest('table') || link.parentElement;
                            let blockText = container ? container.innerText : '';
                            const trackMatch = blockText.match(/\\b([A-Z]{2,4})\\b.*Race #(\\d+)/);
                            const clmMatch = blockText.match(/Claiming Price \\$([\\.\\d,]+)/i);
                            const purseMatch = blockText.match(/Purse \\$([\\.\\d,]+)/i);
                            races.push({
                                race_id: raceIdMatch[1],
                                entry_url: href,
                                track: trackMatch ? trackMatch[1] : '',
                                race_num: trackMatch ? trackMatch[2] : '',
                                claim_price: clmMatch ? parseFloat(clmMatch[1].replace(',', '')) : 0,
                                purse: purseMatch ? parseFloat(purseMatch[1].replace(',', '')) : 0,
                                block_text: blockText.substring(0, 400),
                            });
                        }
                        return races;
                    }
                """)
                races.extend(more)
                print(f"    Page {page_num}: +{len(more)} races (total: {len(races)})")
            except Exception as e:
                print(f"    Pagination error on page {page_num}: {e}")
                break

    # Apply smart filters
    skip_tracks = set(config.get("track_tiers", {}).get("skip", []))
    min_price, max_price = config.get("claim_price_range", [5, 100])
    max_to_scout = config.get("max_races_to_scout", 50)

    # De-duplicate by race_id
    seen_ids = set()
    unique_races = []
    for race in races:
        rid = race.get("race_id", "")
        if rid and rid not in seen_ids:
            seen_ids.add(rid)
            unique_races.append(race)
    races = unique_races

    filtered = []
    for race in races:
        track = race.get("track", "").upper()
        price = race.get("claim_price", 0)

        if track in skip_tracks:
            continue
        if price and (price < min_price or price > max_price):
            continue

        race["track_tier"] = get_track_tier(track, config)
        filtered.append(race)

    # Sort by track tier priority (premium first), then by purse (higher first)
    tier_order = {"premium": 0, "good": 1, "fair": 2, "skip": 3}
    filtered.sort(key=lambda r: (
        tier_order.get(r.get("track_tier", "fair"), 2),
        -r.get("purse", 0),
    ))

    filtered = filtered[:max_to_scout]
    print(f"  After filtering: {len(filtered)} races to scout")

    return filtered


def scrape_entry_page(page, race: Dict) -> List[Dict]:
    """Scrape a race entry page and return horse entries."""
    race_id = race.get("race_id", "")
    url = f"{BASE_URL}/stables/entry.aspx?raceid={race_id}"
    safe_goto(page, url)
    polite_delay()

    entries = page.evaluate("""
        () => {
            const result = [];
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const rows = table.querySelectorAll('tr');
                if (rows.length < 2) continue;

                const headers = Array.from(rows[0].querySelectorAll('th, td'))
                    .map(c => c.innerText.trim().toUpperCase());
                const headerText = headers.join(' ');

                if (headerText.includes('HORSE') || headerText.includes('PP') ||
                    headerText.includes('ENTRY')) {

                    for (let i = 1; i < rows.length; i++) {
                        const cells = Array.from(rows[i].querySelectorAll('td'))
                            .map(c => c.innerText.trim());
                        const links = rows[i].querySelectorAll('a[href*="horsename"]');

                        let horse = {};
                        for (let j = 0; j < headers.length && j < cells.length; j++) {
                            if (headers[j].includes('HORSE') || headers[j].includes('NAME'))
                                horse.name = cells[j];
                            else if (headers[j].includes('OWNER'))
                                horse.stable = cells[j];
                            else if (headers[j].includes('JOCKEY'))
                                horse.jockey = cells[j];
                            else if (headers[j].includes('WT'))
                                horse.weight = cells[j];
                            else if (headers[j].includes('CLM'))
                                horse.clm_price = cells[j];
                        }

                        if (links.length > 0) {
                            horse.profile_link = links[0].getAttribute('href');
                            if (!horse.name) horse.name = links[0].innerText.trim();
                        }

                        // Skip scratches
                        const rowText = rows[i].innerText.toLowerCase();
                        if (rowText.includes('scratch')) {
                            horse.scratched = true;
                        }

                        if (horse.name && !horse.scratched) result.push(horse);
                    }
                    if (result.length > 0) break;
                }
            }
            return result;
        }
    """)

    return entries


def scrape_results_page(page, config: Dict) -> List[Dict]:
    """Use /stats/results.aspx to find claiming races -- more efficient than calendar.

    The results/racing page shows all races per track with direct form page links.
    User can filter by track and see all race types at a glance.
    """
    print("PHASE 1 (results mode): Scanning /stats/results.aspx for claiming races...")
    results_url = f"{BASE_URL}/stats/results.aspx"
    safe_goto(page, results_url)
    polite_delay()

    if not assert_logged_in(page):
        print("  ERROR: Not logged in. Run 01_login_save_state.py first.")
        return []

    # Extract all race listings from the results page
    raw = page.evaluate("""
        () => {
            const races = [];
            const body = document.body.innerText || '';

            // Look for all links to entry pages or race form pages
            const allLinks = document.querySelectorAll('a');
            for (const link of allLinks) {
                const href = link.getAttribute('href') || '';
                const text = link.innerText.trim();

                // Match entry links
                const entryMatch = href.match(/entry\\.aspx\\?raceid=(\\d+)/i);
                // Match form/chart links
                const formMatch = href.match(/(?:form|chart|results)\\.aspx.*raceid=(\\d+)/i);

                const raceId = entryMatch ? entryMatch[1] : (formMatch ? formMatch[1] : null);
                if (!raceId) continue;

                // Find context around this link (parent row or block)
                let container = link.closest('tr') || link.closest('td') || link.parentElement;
                let blockText = container ? container.innerText : text;

                // Look for claiming indicators
                const isClm = /\\b(CLM|Clm|Claiming|MCL|OClm)\\b/i.test(blockText);

                if (isClm) {
                    const trackMatch = blockText.match(/\\b([A-Z]{2,4})\\b/);
                    const raceNumMatch = blockText.match(/Race\\s*#?(\\d+)/i) ||
                                        blockText.match(/R(\\d+)/);
                    const clmMatch = blockText.match(/\\$([\\.\\d,]+)/);
                    const purseMatch = blockText.match(/Purse\\s*\\$([\\.\\d,]+)/i);

                    races.push({
                        race_id: raceId,
                        entry_url: entryMatch ? href : '/stables/entry.aspx?raceid=' + raceId,
                        form_url: formMatch ? href : '',
                        track: trackMatch ? trackMatch[1] : '',
                        race_num: raceNumMatch ? raceNumMatch[1] : '',
                        claim_price: clmMatch ? parseFloat(clmMatch[1].replace(',', '')) : 0,
                        purse: purseMatch ? parseFloat(purseMatch[1].replace(',', '')) : 0,
                        race_type: 'Claiming',
                        block_text: blockText.substring(0, 300),
                    });
                }
            }

            // Also extract from page text directly -- results page often has tabular data
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const rows = table.querySelectorAll('tr');
                for (const row of rows) {
                    const rowText = row.innerText || '';
                    if (!/\\b(CLM|Clm|Claiming|MCL|OClm)\\b/i.test(rowText)) continue;

                    const links = row.querySelectorAll('a[href*="raceid"]');
                    for (const link of links) {
                        const href = link.getAttribute('href') || '';
                        const idMatch = href.match(/raceid=(\\d+)/i);
                        if (!idMatch) continue;

                        // Avoid duplicates
                        const exists = races.some(r => r.race_id === idMatch[1]);
                        if (exists) continue;

                        const trackMatch = rowText.match(/\\b([A-Z]{2,4})\\b/);
                        const clmMatch = rowText.match(/\\$([\\.\\d,]+)/);

                        races.push({
                            race_id: idMatch[1],
                            entry_url: '/stables/entry.aspx?raceid=' + idMatch[1],
                            form_url: href,
                            track: trackMatch ? trackMatch[1] : '',
                            race_num: '',
                            claim_price: clmMatch ? parseFloat(clmMatch[1].replace(',', '')) : 0,
                            purse: 0,
                            race_type: 'Claiming',
                            block_text: rowText.substring(0, 300),
                        });
                    }
                }
            }

            return races;
        }
    """)

    print(f"  Found {len(raw)} claiming race entries from results page")

    # Apply same smart filters as calendar approach
    skip_tracks = set(config.get("track_tiers", {}).get("skip", []))
    min_price, max_price = config.get("claim_price_range", [5, 100])
    max_to_scout = config.get("max_races_to_scout", 50)

    # De-duplicate
    seen_ids = set()
    filtered = []
    for race in raw:
        rid = race.get("race_id", "")
        track = race.get("track", "").upper()
        price = race.get("claim_price", 0)

        if rid in seen_ids:
            continue
        seen_ids.add(rid)

        if track in skip_tracks:
            continue
        if price and (price < min_price or price > max_price):
            continue

        race["track_tier"] = get_track_tier(track, config)
        filtered.append(race)

    # Sort: premium tracks first, then by claiming price (higher = more interesting)
    tier_order = {"premium": 0, "good": 1, "fair": 2, "skip": 3}
    filtered.sort(key=lambda r: (
        tier_order.get(r.get("track_tier", "fair"), 2),
        -r.get("claim_price", 0),
    ))

    filtered = filtered[:max_to_scout]
    print(f"  After filtering: {len(filtered)} races to scout")

    return filtered


def scrape_horse_profile(page, horse_name: str) -> Dict[str, Any]:
    """Scrape a horse's full profile for value assessment."""
    encoded = quote_plus(horse_name)
    url = f"{BASE_URL}/stables/viewhorse.aspx?horsename={encoded}&AllRaces=Yes"
    safe_goto(page, url)
    polite_delay()

    data = page.evaluate("""
        () => {
            const body = document.body.innerText || '';
            const result = {
                full_text: body.substring(0, 12000),
                sire: '',
                dam: '',
                age: null,
                sex: '',
                record_text: '',
                earnings: '',
                recent_races: [],
                foaled_state: '',
            };

            // Try to extract from structured text
            const sireM = body.match(/Sire:\\s*(.+?)(?:\\n|\\r)/i);
            if (sireM) result.sire = sireM[1].trim();

            const damM = body.match(/Dam:\\s*(.+?)(?:\\n|\\r)/i);
            if (damM) result.dam = damM[1].trim();

            const stateM = body.match(/(?:Foaled|Born|Bred)\\s+(?:in\\s+)?([A-Z]{2})\\b/i);
            if (stateM) result.foaled_state = stateM[1].toUpperCase();

            // Look for race results table
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const text = table.innerText || '';
                if (text.includes('Finish') || text.includes('Pos') ||
                    text.includes('Race Date') || text.includes('Class')) {

                    const rows = table.querySelectorAll('tr');
                    const hdrs = rows.length > 0
                        ? Array.from(rows[0].querySelectorAll('th,td')).map(c => c.innerText.trim().toUpperCase())
                        : [];

                    for (let i = 1; i < Math.min(rows.length, 10); i++) {
                        const cells = Array.from(rows[i].querySelectorAll('td'))
                            .map(c => c.innerText.trim());
                        const race = {};
                        for (let j = 0; j < hdrs.length && j < cells.length; j++) {
                            if (hdrs[j].includes('FIN') || hdrs[j].includes('POS'))
                                race.finish = parseInt(cells[j]) || 0;
                            else if (hdrs[j].includes('SPEED') || hdrs[j].includes('SRF'))
                                race.speed = parseFloat(cells[j]) || 0;
                            else if (hdrs[j].includes('CLASS') || hdrs[j].includes('TYPE'))
                                race.class = cells[j];
                            else if (hdrs[j].includes('DIST'))
                                race.distance = cells[j];
                            else if (hdrs[j].includes('DATE'))
                                race.date = cells[j];
                            else if (hdrs[j].includes('TRACK'))
                                race.track = cells[j];
                        }
                        if (Object.keys(race).length > 0)
                            result.recent_races.push(race);
                    }
                    break;
                }
            }

            return result;
        }
    """)

    return data


#  Report Generation 

def generate_value_tags(horse: Dict) -> List[str]:
    """Generate human-readable value tags for a horse."""
    tags = []
    sex = horse.get("sex", "").lower()
    age = horse.get("age")
    scores = horse.get("scores", {})

    if sex in ("colt", "stallion"):
        tags.append("[STUD] INTACT COLT -- breeding potential")
    elif sex in ("filly", "mare"):
        tags.append("[BREED] BROODMARE PROSPECT")

    if age and age <= 4:
        tags.append(f" Young ({age}yo) -- room to develop")

    if scores.get("class_drop", 0) >= 70:
        tags.append(" CLASS DROPPER -- ran in higher company")

    if scores.get("form_trajectory", 0) >= 70:
        tags.append(" IMPROVING FORM (SRF trend up)")
    elif scores.get("form_trajectory", 0) <= 30:
        tags.append("[WARN] DECLINING FORM (SRF trend down)")

    if scores.get("pedigree", 0) >= 80:
        stud_fee = horse.get("stud_fee")
        if stud_fee and stud_fee >= 10:
            tags.append(f" PREMIUM SIRE (${stud_fee:.0f} stud fee)")
        else:
            tags.append(" TOP SIRE BLOODLINE")

    if scores.get("earnings_efficiency", 0) >= 80:
        tags.append(" HIGH EARNER for the price")

    bred_state = horse.get("bred_state", "")
    if bred_state and scores.get("statebred", 0) >= 60:
        tags.append(f" {bred_state}-BRED -- eligible for purse bonuses")

    claim_hist = horse.get("claim_history", [])
    if claim_hist:
        prev_prices = [c.get("price", 0) for c in claim_hist]
        tags.append(f" CLAIM HISTORY -- prev: ${max(prev_prices):.0f}")

    return tags


def generate_report(candidates: List[Dict], races_scouted: int, total_claiming: int, today: str):
    """Generate the claiming value report."""
    lines = [
        f"# [RACE] Claiming Scout v2.2 -- {today}",
        "",
        f"**{total_claiming} claiming races today** | {races_scouted} scouted | "
        f"**{len(candidates)} candidates scored  threshold**",
        "",
        "---",
        "",
    ]

    if not candidates:
        lines.append("> [!NOTE]")
        lines.append("> No candidates met the minimum score threshold today.")
        lines.append("> This means today's claiming pool doesn't have strong value plays.")
        lines.append("> Check back tomorrow -- some days are much better than others.")
    else:
        lines.append("## >> Top Value Candidates")
        lines.append("")

        for rank, horse in enumerate(candidates[:10], 1):
            scores = horse.get("scores", {})
            composite = scores.get("composite", 0)
            tags = generate_value_tags(horse)
            record = horse.get("record", {})
            rec_str = f"{record.get('starts',0)}-{record.get('wins',0)}-{record.get('places',0)}-{record.get('shows',0)}"
            profile_label = horse.get("profile_label", "")

            # Determine star rating
            if composite >= 75:
                stars = "*****"
            elif composite >= 60:
                stars = "****"
            elif composite >= 50:
                stars = "***"
            else:
                stars = "**"

            lines.append(f"### #{rank}. **{horse.get('name', '?')}** -- Score: {composite:.0f}/100 {stars}")
            lines.append(f"_{profile_label}_")
            lines.append("")
            lines.append(f"| Detail | Value |")
            lines.append(f"|--------|-------|")
            lines.append(f"| Race | {horse.get('track', '?')} R{horse.get('race_num', '?')} ({horse.get('race_type', '?')}) |")
            lines.append(f"| Claim Price | **${horse.get('claim_price', '?')}** |")
            lines.append(f"| Age/Sex | {horse.get('age', '?')}yo {horse.get('sex', '?')} |")
            lines.append(f"| Sire / Dam | {horse.get('sire', '?')} / {horse.get('dam', '?')} |")
            stud_fee = horse.get('stud_fee')
            if stud_fee:
                lines.append(f"| Stud Fee | **${stud_fee:.2f}** |")
            lines.append(f"| Record | {rec_str} |")
            lines.append(f"| Earnings | ${horse.get('earnings', 0):.2f} |")

            # WR conformation
            wr_data = horse.get("wr_data", {})
            if wr_data.get("rated"):
                wr_val = wr_data.get("wr", "?")
                meters = wr_data.get("meters", [])
                meters_str = ",".join(str(m) for m in meters) if meters else ""
                lines.append(f"| WR | **{wr_val}** ({meters_str}) |")
            else:
                lines.append(f"| WR | NR [WARN] |")

            best_srf = horse.get('best_srf', 0)
            if best_srf:
                lines.append(f"| Best SRF | **{best_srf}** |")

            # Works
            works = horse.get("works", [])
            if works:
                lines.append(f"| Works | {len(works)} timed works on file |")

            bred_state = horse.get('bred_state', '')
            if bred_state:
                sb_est = horse.get('sb_bonus_est', 0)
                lines.append(f"| State-Bred | {bred_state} (est. ${sb_est:.2f}/yr bonus) |")
            lines.append(f"| Owner | {horse.get('stable', '?')} |")
            claim_hist = horse.get('claim_history', [])
            if claim_hist:
                hist_str = ', '.join(f'${c["price"]:.0f}' for c in claim_hist)
                lines.append(f"| Claim History | Previously claimed at: {hist_str} |")
            lines.append("")

            # Risk flags
            risk_flags = horse.get("risk_flags", [])
            if risk_flags:
                for flag in risk_flags:
                    lines.append(f"- {flag}")
                lines.append("")

            if tags:
                for tag in tags:
                    lines.append(f"- {tag}")
                lines.append("")

            # ROI estimation
            roi = horse.get("roi", {})
            if roi and roi.get("total", 0) > 0:
                lines.append(f"> **12-Month ROI Estimate**: ${roi['total']:.2f} "
                             f"({roi['roi_pct']:+.0f}% vs ${horse.get('claim_price', 0)} claim)")
                lines.append(f"> Racing: ${roi['racing']:.2f} | "
                             f"Breeding: ${roi['breeding']:.2f} | "
                             f"State-Bred: ${roi['statebred']:.2f}")
                lines.append("")

            # Score breakdown with dynamic weights
            profile_key = horse.get("weight_profile", "broodmare_prospect")
            profile_weights = WEIGHT_PROFILES.get(profile_key, {})
            lines.append("<details><summary>Score Breakdown</summary>")
            lines.append("")
            lines.append(f"| Factor | Score | Weight |")
            lines.append(f"|--------|-------|--------|")
            dims = ["age_upside", "breeding_value", "form_trajectory",
                     "conformation", "works", "earnings_efficiency",
                     "class_drop", "pedigree", "statebred"]
            dim_labels = {
                "age_upside": "Age Upside",
                "breeding_value": "Breeding Value",
                "form_trajectory": "Form Trajectory (SRF)",
                "conformation": "Conformation (WR)",
                "works": "Timed Works",
                "earnings_efficiency": "Earnings Efficiency",
                "class_drop": "Class Drop",
                "pedigree": "Pedigree/Stud Fee",
                "statebred": "State-Bred Value",
            }
            for dim in dims:
                w = profile_weights.get(dim, 0)
                s = scores.get(dim, 0)
                label = dim_labels.get(dim, dim)
                lines.append(f"| {label} | {s:.0f} | {w*100:.0f}% |")
            claim_bonus = scores.get('claim_bonus', 0)
            if claim_bonus:
                lines.append(f"| Claim History Bonus | +{claim_bonus:.0f} | flat |")
            risk_p = scores.get('risk_penalty', 0)
            if risk_p:
                lines.append(f"| Risk Penalty | {risk_p:.0f} | flat |")
            lines.append("")
            lines.append("</details>")
            lines.append("")
            lines.append("---")
            lines.append("")

    report_path = OUTPUT_DIR / f"claiming_report_{today}.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport saved to: {report_path}")
    return report_path


#  Main Pipeline 

def parse_args():
    parser = argparse.ArgumentParser(description="Claiming Scout v2.1")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only filter races, don't scrape profiles")
    parser.add_argument("--source", choices=["calendar", "results"], default="calendar",
                        help="Data source: 'calendar' (/races/index.aspx) or "
                             "'results' (/stats/results.aspx) -- results page is "
                             "more efficient with form page links")
    parser.add_argument("--max-races", type=int, default=None,
                        help="Override max races to scout")
    parser.add_argument("--max-horses", type=int, default=None,
                        help="Override max horses to profile")
    parser.add_argument("--min-score", type=int, default=None,
                        help="Override minimum score threshold")
    return parser.parse_args()


def main():
    args = parse_args()
    today = date.today().isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config()

    # Apply CLI overrides
    if args.max_races:
        config["max_races_to_scout"] = args.max_races
    if args.max_horses:
        config["max_horses_to_profile"] = args.max_horses
    if args.min_score:
        config["min_score_threshold"] = args.min_score

    if not AUTH_PATH.exists():
        print("ERROR: auth.json not found. Run 01_login_save_state.py first.")
        return

    print(f"=== Claiming Scout v2.1 -- {today} ===")
    print(f"  Source: {args.source}")
    print(f"  Track tiers: {list(config['track_tiers'].keys())}")
    print(f"  Price range: ${config['claim_price_range'][0]}${config['claim_price_range'][1]}")
    print(f"  Max age: {config['max_age']}")
    print(f"  Score threshold: {config['min_score_threshold']}")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(AUTH_PATH))
        page = context.new_page()

        #  Phase 1: Filter races 
        if args.source == "results":
            races = scrape_results_page(page, config)
        else:
            races = scrape_filtered_races(page, config)
        if not races:
            print("\nNo claiming races found. Check auth or try again later.")
            context.close()
            browser.close()
            generate_report([], 0, 0, today)
            return

        if args.dry_run:
            print("\n=== DRY RUN -- Race Summary ===")
            for r in races:
                print(f"  {r.get('track', '?')} R{r.get('race_num', '?')} | "
                      f"CLM ${r.get('claim_price', '?')} | "
                      f"Purse ${r.get('purse', '?')} | "
                      f"{r.get('race_type', '?')} | "
                      f"Tier: {r.get('track_tier', '?')}")
            context.close()
            browser.close()
            return

        #  Phase 2: Scrape entry pages 
        print(f"\nPHASE 2: Scraping entry pages for {len(races)} races...")
        all_horses = []

        for i, race in enumerate(races, 1):
            track = race.get("track", "?")
            race_num = race.get("race_num", "?")
            claim_price = race.get("claim_price", 0)
            print(f"  [{i}/{len(races)}] {track} R{race_num} CLM ${claim_price}")

            try:
                entries = scrape_entry_page(page, race)
                for entry in entries:
                    entry["track"] = track
                    entry["race_num"] = race_num
                    entry["claim_price"] = claim_price
                    entry["purse"] = race.get("purse", 0)
                    entry["race_type"] = race.get("race_type", "")
                    entry["conditions"] = race.get("conditions", "")
                    entry["race_id"] = race.get("race_id", "")
                    entry["track_tier"] = race.get("track_tier", "fair")
                all_horses.extend(entries)
                print(f"     {len(entries)} entries")
            except Exception as e:
                print(f"    ERROR: {e}")

        print(f"\n  Total horses found: {len(all_horses)}")

        #  Phase 3: Profile deep dive 
        max_profiles = config.get("max_horses_to_profile", 30)
        horses_to_profile = all_horses[:max_profiles]
        print(f"\nPHASE 3: Deep-diving {len(horses_to_profile)} horse profiles...")

        for i, horse in enumerate(horses_to_profile, 1):
            name = horse.get("name", "?")
            print(f"  [{i}/{len(horses_to_profile)}] {name}")

            try:
                profile = scrape_horse_profile(page, name)

                # Parse profile data using v2.1 HRP-aware parsers
                full_text = profile.get("full_text", "")
                sire_line = ""
                sire_m = re.search(r"Sire:.*$", full_text, re.MULTILINE)
                if sire_m:
                    sire_line = sire_m.group(0)

                horse["sire"] = profile.get("sire") or parse_sire(full_text)
                horse["stud_fee"] = parse_stud_fee(sire_line)
                horse["dam"] = profile.get("dam", "")
                horse["age"] = parse_age_from_text(full_text)
                horse["sex"] = parse_sex_from_text(full_text)
                horse["record"] = parse_record(full_text)
                horse["earnings"] = parse_earnings(full_text)
                horse["bred_state"] = parse_bred_state(full_text)
                horse["claim_history"] = parse_claim_history(full_text)
                horse["gelded"] = is_gelded(full_text)
                horse["profile_text"] = full_text[:3000]

                # v2.2: Parse WR conformation meters
                horse["wr_data"] = parse_wr_meters(full_text)

                # v2.2: Parse timed works
                horse["works"] = parse_timed_works(full_text)

                # Parse SRF speed figures from past-performance lines
                pp_races = parse_hrp_pp_lines(full_text)
                # Merge with any table-based races, preferring PP-parsed data
                table_races = profile.get("recent_races", [])
                horse["recent_races"] = pp_races if pp_races else table_races

                # Extract best SRF from LIFE line
                life = parse_hrp_life_record(full_text)
                horse["best_srf"] = life.get("best_srf", 0) if life else 0

                # State-bred bonus estimate
                sb_bonus = estimate_statebred_bonus(horse.get("bred_state", ""))
                horse["sb_bonus_est"] = round(sb_bonus, 2)

                # Summary line
                wr_str = f"WR:{horse['wr_data']['wr']}" if horse['wr_data'].get('rated') else "WR:NR"
                srf_str = f"SRF:{horse['best_srf']}" if horse.get("best_srf") else "SRF:?"
                stud_str = f"stud ${horse['stud_fee']}" if horse.get("stud_fee") else ""
                sb_str = f"({horse['bred_state']}*)" if horse.get("bred_state") else ""
                works_str = f"works:{len(horse.get('works', []))}" if horse.get("works") else ""
                print(f"    {horse['age']}yo {horse['sex']} | "
                      f"Sire: {horse['sire'][:20]} {stud_str} | "
                      f"Rec: {horse['record']} | "
                      f"Earn: ${horse['earnings']:.2f} | "
                      f"{wr_str} {srf_str} {sb_str} {works_str}")

            except Exception as e:
                print(f"    ERROR: {e}")
                horse["age"] = None
                horse["sex"] = "unknown"
                horse["record"] = {"starts": 0, "wins": 0, "places": 0, "shows": 0}
                horse["earnings"] = 0
                horse["sire"] = ""
                horse["recent_races"] = []
                horse["profile_text"] = ""
                horse["stud_fee"] = None
                horse["bred_state"] = ""
                horse["claim_history"] = []
                horse["best_srf"] = 0
                horse["sb_bonus_est"] = 0
                horse["wr_data"] = {"wr": None, "meters": [], "rated": False}
                horse["works"] = []

        context.close()
        browser.close()

    #  Phase 4: Scoring 
    print(f"\nPHASE 4: Scoring {len(horses_to_profile)} candidates...")
    threshold = config.get("min_score_threshold", 40)

    for horse in horses_to_profile:
        score = compute_composite_score(horse, config)
        horse["composite_score"] = round(score, 1)

    # Sort by composite score, descending
    horses_to_profile.sort(key=lambda h: h.get("composite_score", 0), reverse=True)

    # Filter by threshold
    candidates = [h for h in horses_to_profile if h.get("composite_score", 0) >= threshold]
    print(f"  {len(candidates)} candidates scored  {threshold}")

    #  Phase 5: Report 
    print(f"\nPHASE 5: Generating report...")

    # Save raw data
    data_path = OUTPUT_DIR / f"claiming_data_{today}.json"
    # Clean non-serializable data
    export_data = []
    for h in horses_to_profile:
        clean = {k: v for k, v in h.items() if k != "profile_text"}
        export_data.append(clean)
    data_path.write_text(json.dumps(export_data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    total_claiming = len(all_horses)
    report_path = generate_report(candidates, len(races), total_claiming, today)

    print(f"\n{'='*50}")
    print(f"  Claiming Scout v2 Complete")
    print(f"  Races scouted: {len(races)}")
    print(f"  Horses profiled: {len(horses_to_profile)}")
    print(f"  Candidates above threshold: {len(candidates)}")
    print(f"  Report: {report_path}")
    print(f"  Data: {data_path}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
