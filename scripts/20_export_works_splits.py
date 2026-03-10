"""20_export_works_splits.py — Export individual timed work rows with splits to JSON.

Reads works_all.html from each horse's export folder and extracts all individual
timed work entries with dates, times, splits, distance, surface, and running style
analysis (early speed vs closer).

Output: outputs/works_splits.json — a dict keyed by horse name with a list of work entries.
"""
import json
import re
from pathlib import Path

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
    return f"{2000 + int(m.group(3)):04d}-{mon.get(m.group(2), 0):02d}-{int(m.group(1)):02d}"


def time_to_seconds(t: str) -> float:
    """Convert :SS or M:SS to total seconds."""
    t = t.strip()
    if t.startswith(":"):
        return float(t[1:])
    parts = t.split(":")
    if len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    return 0.0


def parse_works_from_html(html_path: Path) -> list:
    """Parse individual work entries from works_all.html."""
    from bs4 import BeautifulSoup
    text = html_path.read_text(encoding="utf-8", errors="ignore")
    s = BeautifulSoup(text, "html.parser")
    raw = norm(" ".join(s.stripped_strings)).upper()

    m = re.search(r"\bWORKS:\s*(.*?)\s*(?:NOMINATIONS|ENTRIES|HORSE NOTES|$)", raw)
    if not m:
        return []

    chunks = [x.strip() for x in re.split(r"(?=\b\d{1,2}[A-Z]{3}\d{2}(?:-|\s))", m.group(1)) if x.strip()]
    works = []

    for ch in chunks:
        dm = re.match(r"^(\d{1,2}[A-Z]{3}\d{2})(?:-|\s+)([A-Z0-9]+)\s*(.*)$", ch)
        if not dm:
            continue
        date = parse_ddmmmyy(dm.group(1))
        track = dm.group(2)
        rest = dm.group(3)

        # Extract distance and surface
        dist, surf = "", ""
        toks = rest.split()
        for i, tok in enumerate(toks):
            if re.fullmatch(r"\d+F(?:\(T\))?", tok):
                dist = tok
                if i > 0 and re.fullmatch(r"[A-Z]{2,4}", toks[i - 1]):
                    surf = toks[i - 1]
                elif i + 1 < len(toks) and re.fullmatch(r"[A-Z]{1,4}", toks[i + 1]):
                    surf = toks[i + 1]
                break

        # Extract times: find all :SS or M:SS followed by a number
        tp = re.findall(r"(\d{1,2}:\d{2}|:\d{2})\s+(\d+)", ch)
        if not tp:
            continue

        # All time entries except last are splits, last is final time + rank
        all_times = [x for x, _ in tp]
        splits = all_times[:-1]
        final_time = all_times[-1]
        rank = tp[-1][1]

        # Calculate split seconds for analysis
        split_secs = [time_to_seconds(t) for t in splits]
        final_secs = time_to_seconds(final_time)

        # Calculate individual furlong splits (differential)
        furlong_splits = []
        if split_secs:
            furlong_splits.append(split_secs[0])
            for i in range(1, len(split_secs)):
                furlong_splits.append(split_secs[i] - split_secs[i - 1])
            if final_secs > split_secs[-1]:
                furlong_splits.append(final_secs - split_secs[-1])
        elif final_secs > 0:
            furlong_splits = [final_secs]

        # Determine running style from splits
        running_style = "unknown"
        if len(furlong_splits) >= 2:
            first_half = furlong_splits[:len(furlong_splits) // 2]
            second_half = furlong_splits[len(furlong_splits) // 2:]
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            diff = avg_second - avg_first
            if diff > 0.5:
                running_style = "early_speed"  # Faster early, slowing
            elif diff < -0.5:
                running_style = "closer"  # Slower early, finishing strong
            else:
                running_style = "even_pace"

        # Extract rider and work type codes
        rm = re.search(r"(?:\d{1,2}:\d{2}|:\d{2})\s+\d+\s+([A-Z][A-Z0-9'._-]+)\s+(\d{2,3})\b", ch)
        rider, weight = (rm.group(1), rm.group(2)) if rm else ("", "")

        # Extract effort codes
        sc, pc, ec = "", "", ""
        if weight and f" {weight} " in ch:
            tail = ch.split(f" {weight} ", 1)[1].split()
            codes = [z for z in tail if re.fullmatch(r"[A-Z]{1,3}", z)]
            if len(codes) >= 3:
                sc, pc, ec = codes[0], codes[1], codes[2]

        if not date:
            continue

        works.append({
            "date": date,
            "track": track,
            "surface": surf.lower() if surf else "",
            "distance": dist,
            "splits": splits,
            "split_secs": split_secs,
            "final_time": final_time,
            "final_secs": round(final_secs, 1),
            "furlong_splits": [round(x, 1) for x in furlong_splits],
            "running_style": running_style,
            "rank": rank,
            "rider": rider,
            "weight": weight,
            "start_code": sc,
            "pace_code": pc,
            "effort_code": ec,
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
            # Sort by date descending
            works.sort(key=lambda w: w["date"], reverse=True)

            # Analyze improvement trend
            timed_5f = [w for w in works if "5F" in w["distance"]]
            timed_3f = [w for w in works if "3F" in w["distance"]]

            # 5f trend
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

            # 3f trend
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


if __name__ == "__main__":
    main()
