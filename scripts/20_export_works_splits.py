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
    if t.startswith(":"):
        inner = t[1:]
        try:
            return float(inner)
        except ValueError:
            return 0.0
    parts = t.split(":")
    if len(parts) == 2:
        try:
            mins = float(parts[0])
            secs = float(parts[1])
            return mins * 60 + secs
        except ValueError:
            return 0.0
    return 0.0


def extract_cell_text(td) -> str:
    """Extract clean text from a td cell, converting superscript digits to decimals.

    HRP uses <sup>3</sup> after a time like :24 to mean :24.3 (tenths of a second).
    This function converts that notation to proper decimal format.

    Uses recursive child walking (not .descendants) to avoid double-capturing
    text inside <sup> tags.
    """
    from bs4 import NavigableString, Tag

    def _walk(node):
        parts = []
        for child in node.children:
            if isinstance(child, NavigableString):
                txt = child.strip()
                if txt and txt != "\xa0":
                    parts.append(txt)
            elif isinstance(child, Tag):
                if child.name == "sup":
                    digit = child.get_text(strip=True)
                    if len(digit) == 1 and digit.isdigit():
                        parts.append("." + digit)
                    # Skip empty/space sups
                else:
                    # Recurse into font, b, a, etc.
                    parts.extend(_walk(child))
        return parts

    return "".join(_walk(td)).strip()


def _generate_work_comment(final_secs, per_furlong, distance, running_style,
                           work_type, rank, furlong_splits):
    """Generate an intelligent one-liner about a work."""
    notes = []
    dist_upper = distance.upper()

    # Pace quality based on HRP benchmarks
    if "5F" in dist_upper:
        if final_secs <= 59.0:
            notes.append("Bullet work")
        elif final_secs <= 60.0:
            notes.append("Sharp")
        elif final_secs <= 61.0:
            notes.append("Solid")
        elif final_secs <= 62.0:
            notes.append("Steady")
        else:
            notes.append("Easy maintenance")
    elif "6F" in dist_upper:
        if final_secs <= 70.0:
            notes.append("Sharp 6f drill")
        elif final_secs <= 71.0:
            notes.append("Good pace")
        elif final_secs <= 72.0:
            notes.append("Steady")
        else:
            notes.append("Easy gallop")
    elif "3F" in dist_upper:
        if final_secs <= 35.0:
            notes.append("Quick blowout")
        elif final_secs <= 36.5:
            notes.append("Crisp move")
        else:
            notes.append("Maintenance drill")
    elif "4F" in dist_upper:
        if final_secs <= 47.0:
            notes.append("Strong half")
        elif final_secs <= 49.0:
            notes.append("Good pace")
        else:
            notes.append("Easy")

    # Rank analysis
    if rank and "/" in rank:
        parts = rank.split("/")
        try:
            pos = int(parts[0])
            total = int(parts[1])
            if total >= 3:
                pct = pos / total
                if pct <= 0.10:
                    notes.append(f"tops field ({rank})")
                elif pct <= 0.25:
                    notes.append(f"top quarter ({rank})")
                elif pct >= 0.85:
                    notes.append(f"bottom of tab ({rank})")
        except (ValueError, ZeroDivisionError):
            pass

    # Running style note
    if running_style == "closer" and len(furlong_splits) >= 2:
        notes.append("strong close")
    elif running_style == "early_speed" and len(furlong_splits) >= 2:
        notes.append("pressed early")

    # Work type
    if work_type == "B":
        notes.append("breezing")
    elif work_type == "H":
        notes.append("handily")

    return "; ".join(notes) if notes else ""


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

    # Collect ALL text from leaf <td> elements after the Works: label.
    # HRP uses varying nesting depths, so instead of matching specific
    # row structures, we gather a flat stream of cell values and split
    # them into work entries at each date-track pattern.
    all_leaf_texts = []
    for td in works_label.find_all_next("td"):
        # Only leaf tds (no child tds)
        if td.find("td"):
            continue
        all_leaf_texts.append(extract_cell_text(td))

    if not all_leaf_texts:
        return []

    # Split the flat list into work entries at each date-track pattern
    # Each date like "5Mar26-AQU" starts a new work entry
    work_chunks = []
    current_chunk = None
    for val in all_leaf_texts:
        if re.match(r"\d{1,2}[A-Za-z]{3}\d{2}-[A-Za-z]{2,6}$", val.strip()):
            if current_chunk and len(current_chunk) >= 10:
                work_chunks.append(current_chunk)
            current_chunk = [val]
        elif current_chunk is not None:
            current_chunk.append(val)
    if current_chunk and len(current_chunk) >= 10:
        work_chunks.append(current_chunk)

    works = []

    for cell_texts in work_chunks:

        # Look for the date-track pattern in first cell
        first = cell_texts[0] if cell_texts else ""
        dm = re.match(r"(\d{1,2}[A-Za-z]{3}\d{2})-([A-Za-z]{2,6})", first)
        if not dm:
            continue

        date = parse_ddmmmyy(dm.group(1))
        track = dm.group(2)
        if not date:
            continue

        # Extract surface (typically cell index 2)
        surface = ""
        distance = ""

        # Find surface and distance from cell values
        for i, ct in enumerate(cell_texts):
            ct_clean = ct.strip()
            # Surface: fst, gd, sly, my, fm, yl, etc.
            if re.fullmatch(r"[a-z]{2,4}", ct_clean) and not surface:
                surface = ct_clean
            # Distance: 2f, 3f, 4f, 5f, 6f, 7f, 1m etc.
            elif re.fullmatch(r"\d+[fmFM]", ct_clean) and not distance:
                distance = ct_clean.upper()

        if not distance:
            continue

        # ── HRP time columns (cells 5-8) ──────────────────────────
        # HRP puts cumulative fractional times in cells 5-8, ordered
        # from earliest fraction to final time. Examples:
        #   3f work: [5]=:36.2  (final only)
        #   4f work: [5]=:24    [6]=:48.1   (3f split, 4f final)
        #   5f work: [5]=:24    [6]=:47     [8]=:59.2   (3f, 4/5f, final)
        #   6f work: [5]=:24    [6]=:47     [7]=1:00    [8]=1:12
        # The LAST non-empty time is always the FINAL time.
        # Preceding times are intermediate cumulative splits.
        time_cells = []
        for ci in (5, 6, 7, 8):
            if ci < len(cell_texts):
                ct_clean = cell_texts[ci].strip()
                if re.fullmatch(r":?\d{1,2}:?\d{2}(?:\.\d)?", ct_clean):
                    if ct_clean.startswith(":") or ":" in ct_clean:
                        time_cells.append(ct_clean)

        if not time_cells:
            continue

        # Last time is the final time for the listed distance
        final_time = time_cells[-1]
        intermediate_splits = time_cells[:-1]  # all preceding are cumulative splits

        # Calculate seconds
        final_secs = time_to_seconds(final_time)
        if final_secs <= 0:
            continue

        # Parse distance as furlongs
        dist_num = int(re.match(r"(\d+)", distance).group(1))

        # Calculate per-furlong rate
        per_furlong = round(final_secs / max(dist_num, 1), 1) if dist_num > 0 else final_secs

        # ── Build differential splits from cumulative times ───────
        # Convert all cumulative times to seconds, then compute diffs
        cumulative_secs = []
        for sp in intermediate_splits:
            sp_secs = time_to_seconds(sp)
            if sp_secs > 0:
                cumulative_secs.append(sp_secs)
        cumulative_secs.append(final_secs)  # add final time at end

        furlong_splits = []
        if len(cumulative_secs) >= 2:
            # First split is the first cumulative time (e.g. 3f in :24)
            furlong_splits.append(round(cumulative_secs[0], 1))
            # Subsequent splits are differences between consecutive times
            for j in range(1, len(cumulative_secs)):
                diff = round(cumulative_secs[j] - cumulative_secs[j-1], 1)
                if diff > 0:
                    furlong_splits.append(diff)

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

        # Generate intelligent commentary
        comment = _generate_work_comment(
            final_secs, per_furlong, distance, running_style,
            work_type, rank, furlong_splits
        )

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
            "comment": comment,
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
