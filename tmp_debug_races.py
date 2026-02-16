import sys
import re
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(r"C:\hrp-ops")
RAW = ROOT / "inputs" / "export" / "raw"

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def table_preview(table, max_rows=6):
    rows = table.find_all("tr")
    out = []
    for r in rows[:max_rows]:
        cells = [norm(c.get_text(" ", strip=True)) for c in r.find_all(["th","td"])]
        if cells:
            out.append(cells)
    return out

def find_candidate_tables(soup):
    candidates = []
    for t in soup.find_all("table"):
        rows = t.find_all("tr")
        if not rows:
            continue
        hdr = [norm(c.get_text(" ", strip=True)).upper() for c in rows[0].find_all(["th","td"])]
        hdr_join = " | ".join(hdr)
        # Look for anything that *looks* like a race table header
        if ("DATE" in hdr_join and ("DIST" in hdr_join or "DISTANCE" in hdr_join or "SURF" in hdr_join or "TRACK" in hdr_join or "TIME" in hdr_join)):
            candidates.append((hdr_join, t))
    return candidates

def scan_file(path: Path):
    if not path.exists():
        print(f"  MISSING: {path.name}")
        return
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.stripped_strings)

    print(f"\nFILE: {path.name}")
    # quick “do we even have race-like dates in table rows?”
    has_mmddyyyy = bool(re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", text))
    print(f"  Contains any mm/dd/yyyy anywhere: {has_mmddyyyy}")

    # show candidate tables
    cands = find_candidate_tables(soup)
    print(f"  Candidate tables by header: {len(cands)}")
    for i, (hdr, tbl) in enumerate(cands[:5], start=1):
        print(f"  -- Candidate #{i} header: {hdr}")
        prev = table_preview(tbl, max_rows=8)
        for row in prev:
            print("     ", row)

    # search for UI hints
    for needle in ["Last 10 Races", "All Races", "View:", "Printable Version"]:
        if needle.lower() in text.lower():
            print(f"  Found text token: {needle}")

def main():
    if len(sys.argv) < 2:
        print("Usage: py tmp_debug_races.py <Horse_Folder_Name>")
        sys.exit(1)
    horse = sys.argv[1]
    d = RAW / horse
    if not d.exists():
        print(f"Horse folder not found: {d}")
        sys.exit(2)

    print(f"HORSE: {horse}")
    scan_file(d / "profile_allraces.html")
    scan_file(d / "profile_printable.html")

if __name__ == "__main__":
    main()
