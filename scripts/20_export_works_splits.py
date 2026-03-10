"""20_export_works_splits.py — Export individual timed work rows with splits to JSON.

Reads works_all.html from each horse's export folder using proper HTML table cell
extraction (not regex text-flattening) to get accurate split times.

HRP works_all.html table structure per work row:
  Col 0: Date-Track (e.g. "18Feb26-TP")
  Col 1: empty spacer
  Col 2: Surface (e.g. "fst", "gd")
  Col 3: Distance (e.g. "3f", "5f")
  Col 4: empty spacer
  Col 5: Time for this distance (e.g. ":23", ":59")
  Col 6: 2nd fraction (empty or time)
  Col 7: 3rd fraction (empty or time)
  Col 8: Last fraction / final time for longer works
  Col 9: Rider type (e.g. "Trainer", jockey name)
  Col 10: Work type (B=Breeze, H=Handily)
  Col 11: Weight (e.g. "120")
  Col 12: Surface code
  Col 13: Condition %
  Col 14: Stamina %
  Col 15: Consistency delta
  Col 16: Distance delta
  Col 17-18: Codes
  Col 19: Rank (e.g. "1/3")

Output: outputs/works_splits.json
"""
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "inputs" / "export" / "raw"
OUTPUT = ROOT / "outputs" / "works_splits.json"


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_ddmmmyy(value: str) -> str:
    m = re.match(r"^(\d{1,2})([A-Z]{3})(\d{2})$", value.upper())
    if not m:
        return ""
    mon = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
    mo = mon.get(m.group(2))
    if not mo:
        return ""
    return f"{2000 + int(m.group(3)):04d}-{mo:02d}-{int(m.group(1)):02d}"


def time_to_seconds(t: str) -> float:
    """Convert :SS, :SS.f, M:SS, or M:SS.f to total seconds."""
    t = t.strip().rstrip(".")
    if not t:
        return 0.0
    # Handle superscript fractions like ":344" meaning :34.4
    if t.startswith(":"):
        inner = t[1:]
        # Check for fractional part encoded as extra digit (e.g. "344" = 34.4)
        if len(inner) > 2 and inner.isdigit():
            return float(inner[:-1]) + float(inner[-1]) / 10.0
        try:
            return float(inner)
        except ValueError:
            return 0.0
    parts = t.split(":")
    if len(parts) == 2:
        try:
            mins = float(parts[0])
            secs_str = parts[1]
            if len(secs_str) > 2 and secs_str.isdigit():
                secs = float(secs_str[:-1]) + float(secs_str[-1]) / 10.0
            else:
                secs = float(secs_str)
            return mins * 60 + secs
        except ValueError:
            return 0.0
    return 0.0


def extract_cell_text(td) -> str:
    """Extract clean text from a td cell, merging superscript into the value."""
    parts = []
    for child in td.descendants:
        if child.name == "sup":
            sup_text = child.get_text(strip=True)
            if sup_text and sup_text.strip():
                parts.append(sup_text.strip())
        elif child.string and child.parent.name != "sup":
            txt = child.string.strip()
            if txt and txt != "\xa0":
                parts.append(txt)
    return "".join(parts).strip()


def parse_works_from_html(html_path: Path) -> list:
    """Parse individual work entries from works_all.html using table cell extraction."""
    text = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(text, "html.parser")

    # Find the "Works:" label and the table that follows it
    works_label = None
    for b in soup.find_all("b"):
        if "Works:" in (b.get_text(strip=True) or ""):
            works_label = b
            break

    if not works_label:
        return []

    # The works table is the next table after the Works: label
    # Navigate up to find the containing element, then find the next table
    parent = works_label.parent
    while parent and parent.name != "td" and parent.name != "div":
        parent = parent.parent

    # Find the works table - it's a table with 740 width that follows Works:
    works_table = None
    if parent:
        # Look for the table right after the works label
        for sibling in works_label.find_all_next("table"):
            # Works rows have nested tables with date-track patterns
            first_text = norm(sibling.get_text(" ", strip=True)[:50])
            if re.search(r"\d{1,2}[A-Za-z]{3}\d{2}-[A-Z]{2,3}", first_text):
                works_table = sibling
                break

    if not works_table:
        return []

    works = []

    # Each work entry is a nested table row within the outer table
    # Find all inner tables that represent individual work rows
    work_rows = works_table.find_all("tr", recursive=True)

    for row in work_rows:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 10:
            continue

        # Extract cell values
        cell_texts = []
        for c in cells:
            cell_texts.append(extract_cell_text(c))

        # Look for the date-track pattern in first cell
        first = cell_texts[0] if cell_texts else ""
        dm = re.match(r"(\d{1,2}[A-Za-z]{3}\d{2})-([A-Z]{2,3})", first)
        if not dm:
            continue

        date = parse_ddmmmyy(dm.group(1))
        track = dm.group(2)
        if not date:
            continue

        # Extract surface (typically cell index 2)
        surface = ""
        distance = ""
        time_val = ""
        split_vals = []

        # Find surface, distance, and times from cell values
        for i, ct in enumerate(cell_texts):
            ct_clean = ct.strip()
            # Surface: fst, gd, sly, my, fm, yl, etc.
            if re.fullmatch(r"[a-z]{2,4}", ct_clean) and not surface:
                surface = ct_clean
            # Distance: 2f, 3f, 4f, 5f, 6f, 7f, 1m etc.
            elif re.fullmatch(r"\d+[fmFM]", ct_clean) and not distance:
                distance = ct_clean.upper()
            # Time values: :23, :234, :59, :592, 1:01, 1:012, etc.
            elif re.fullmatch(r":?\d{1,2}:?\d{2,3}", ct_clean):
                if not ct_clean.startswith(":") and ":" not in ct_clean:
                    continue
                split_vals.append(ct_clean)

        if not distance:
            continue

        # The FIRST time value is the time for the listed distance
        # Subsequent time values are cumulative times for longer distances
        if not split_vals:
            continue

        final_time = split_vals[0]
        remaining_splits = split_vals[1:] if len(split_vals) > 1 else []

        # Calculate seconds
        final_secs = time_to_seconds(final_time)
        if final_secs <= 0:
            continue

        # Parse distance as furlongs
        dist_num = int(re.match(r"(\d+)", distance).group(1))

        # Calculate per-furlong rate
        per_furlong = round(final_secs / max(dist_num, 1), 1) if dist_num > 0 else final_secs

        # Calculate furlong splits from cumulative times
        furlong_splits = []
        all_times = [final_secs]
        for rs in remaining_splits:
            rs_secs = time_to_seconds(rs)
            if rs_secs > final_secs:
                all_times.append(rs_secs)

        # If we have the base distance time and additional cumulative times,
        # compute differential splits
        if len(all_times) > 1:
            furlong_splits.append(round(all_times[0], 1))
            for j in range(1, len(all_times)):
                diff = round(all_times[j] - all_times[j-1], 1)
                if diff > 0:
                    furlong_splits.append(diff)
        else:
            # Single time - estimate per-furlong
            furlong_splits = [round(per_furlong, 1)] * dist_num

        # Determine running style from splits
        running_style = "unknown"
        if len(furlong_splits) >= 2:
            mid = len(furlong_splits) // 2
            avg_first = sum(furlong_splits[:mid]) / mid
            avg_second = sum(furlong_splits[mid:]) / len(furlong_splits[mid:])
            diff = avg_second - avg_first
            if diff > 0.5:
                running_style = "early_speed"
            elif diff < -0.5:
                running_style = "closer"
            else:
                running_style = "even_pace"

        # Extract work type, rider, weight, rank from remaining cells
        work_type = ""
        weight = ""
        rider = ""
        rank = ""
        cond_pct = ""
        stam_pct = ""

        for ct in cell_texts:
            ct_clean = ct.strip()
            if ct_clean in ("B", "H") and not work_type:
                work_type = ct_clean
            elif re.fullmatch(r"\d{2,3}", ct_clean) and not weight and ct_clean not in ("97", "98", "99", "100", "101", "102", "103", "104", "105", "106", "107", "108", "109", "110"):
                weight = ct_clean
            elif re.fullmatch(r"\d+/\d+", ct_clean):
                rank = ct_clean
            elif ct_clean in ("Trainer",) or (len(ct_clean) > 3 and ct_clean[0].isupper() and not re.match(r"\d", ct_clean) and ct_clean not in ("Trainer",)):
                if not rider and ct_clean not in (surface, distance):
                    rider = ct_clean
            elif re.fullmatch(r"\d{1,3}%", ct_clean):
                if not cond_pct:
                    cond_pct = ct_clean
                elif not stam_pct:
                    stam_pct = ct_clean

        works.append({
            "date": date,
            "track": track,
            "surface": surface,
            "distance": distance,
            "final_time": final_time,
            "final_secs": round(final_secs, 1),
            "per_furlong": per_furlong,
            "furlong_splits": furlong_splits,
            "running_style": running_style,
            "work_type": work_type,
            "rider": rider,
            "weight": weight,
            "rank": rank,
            "cond_pct": cond_pct,
            "stam_pct": stam_pct,
        })

    return works


def main():
    result = {}
    horse_dirs = sorted([p for p in RAW_ROOT.iterdir() if p.is_dir()])

    for hd in horse_dirs:
        works_file = hd / "works_all.html"
        if not works_file.exists():
            continue
        horse_name = hd.name.replace("_", " ").strip()
        works = parse_works_from_html(works_file)
        if works:
            works.sort(key=lambda w: w["date"], reverse=True)

            # Analyze improvement trends
            timed_5f = [w for w in works if "5F" in w["distance"]]
            timed_3f = [w for w in works if "3F" in w["distance"]]

            trend_5f = "no_data"
            if len(timed_5f) >= 2:
                recent = timed_5f[0]["final_secs"]
                older = timed_5f[-1]["final_secs"]
                if recent < older - 0.5:
                    trend_5f = "improving"
                elif recent > older + 0.5:
                    trend_5f = "declining"
                else:
                    trend_5f = "steady"

            trend_3f = "no_data"
            if len(timed_3f) >= 2:
                recent = timed_3f[0]["final_secs"]
                older = timed_3f[-1]["final_secs"]
                if recent < older - 0.3:
                    trend_3f = "improving"
                elif recent > older + 0.3:
                    trend_3f = "declining"
                else:
                    trend_3f = "steady"

            result[horse_name] = {
                "works": works,
                "total": len(works),
                "trend_5f": trend_5f,
                "trend_3f": trend_3f,
                "count_5f": len(timed_5f),
                "count_3f": len(timed_3f),
            }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"works_splits.json: {len(result)} horses with works data")
    total_works = sum(h["total"] for h in result.values())
    print(f"  Total individual work entries: {total_works}")

    # Verify a sample
    for name in ("Crypto King", "American Shorthair"):
        if name in result:
            ws = result[name]["works"][:3]
            print(f"\n  Sample - {name}:")
            for w in ws:
                print(f"    {w['date']} {w['track']} {w['distance']} time={w['final_time']} ({w['final_secs']}s) type={w['work_type']} rank={w['rank']}")


if __name__ == "__main__":
    main()
