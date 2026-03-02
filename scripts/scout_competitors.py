"""Quick competitor field scraper for upcoming races.

Navigates to race entry pages, extracts full field including:
- Horse name, jockey, weight, SRF, PP history
- Uses existing auth.json for authentication

SAFETY: Read-only.
"""

import json
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = ROOT / "inputs" / "export" / "auth.json"
OUTPUT = ROOT / "outputs"

# Races to scout
RACES = [
    {"track": "TUP", "date": "3/3/2026", "race": 2, "our_horse": "Cayuga Lake",
     "class": "4+Clm6.25N4L", "dist": "5½f Dirt"},
    {"track": "BTP", "date": "3/4/2026", "race": 3, "our_horse": "Sassy Astray",
     "class": "fMdSpWt8.00", "dist": "1m Dirt"},
    {"track": "TUP", "date": "3/4/2026", "race": 6, "our_horse": "Strike King",
     "class": "OClm10/N2X-N", "dist": "1m Dirt"},
]

def scrape_race_field(page, track, race_num):
    """Navigate to entries page and scrape a specific race field."""
    url = f"https://www.horseracingpark.com/races/entries.aspx?track={track}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)
    
    text = page.inner_text("body")
    
    # Find the race section
    result = {"raw_text": "", "entries": []}
    
    # Look for race links/buttons
    race_links = page.query_selector_all("a, button")
    for link in race_links:
        link_text = link.inner_text().strip()
        if f"Race #{race_num}" in link_text or f"R{race_num}" in link_text:
            link.click()
            time.sleep(3)
            break
    
    # Get the page text after clicking
    text = page.inner_text("body")
    result["raw_text"] = text[:5000]
    
    return result


def scrape_horse_pp(page, horse_name):
    """Quick scrape of a horse's PP page for SRF and record."""
    url = f"https://www.horseracingpark.com/stables/viewhorse.aspx?horsename={horse_name.replace(' ', '+')}&AllRaces=Yes"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        text = page.inner_text("body")
        
        info = {"name": horse_name}
        
        # Extract LIFE record
        life_m = re.search(r'LIFE\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+(\d+)', text)
        if life_m:
            info["starts"] = int(life_m.group(1))
            info["wins"] = int(life_m.group(2))
            info["places"] = int(life_m.group(3))
            info["shows"] = int(life_m.group(4))
            info["earnings"] = float(life_m.group(5))
            info["best_srf"] = int(life_m.group(6))
            info["record"] = f"{life_m.group(1)}-{life_m.group(2)}-{life_m.group(3)}-{life_m.group(4)}"
        
        # Extract age/sex
        header_m = re.search(r'(?:B\.|Ch\.|Dk B\.|Br\.|Bl\.|Gr\.|Ro\.)\s*([fmgch])\.\s*(\d+)', text, re.IGNORECASE)
        if header_m:
            sex_map = {"f": "F", "m": "M", "g": "G", "c": "C", "h": "H"}
            info["sex"] = sex_map.get(header_m.group(1).lower(), "?")
            info["age"] = int(header_m.group(2))
        
        # Extract recent SRFs from PP lines
        lines = text.split('\n')
        srfs = []
        for i, line in enumerate(lines):
            if re.match(r'^\d{1,2}[A-Z][a-z]{2}\d{2}-\d+[A-Z]', line.strip()):
                # Found PP line, look for SRF after class
                # Scan forward for class line then SRF
                for j in range(i+1, min(i+20, len(lines))):
                    cl = lines[j].strip()
                    if re.match(r'^(?:f)?(?:Clm|OClm|Alw|MdSpWt|MdClm|Md|Stk|Stakes|HCap)', cl):
                        # Next line should be SRF
                        if j+1 < len(lines):
                            srf_line = lines[j+1].strip()
                            if re.match(r'^\d{2,3}$', srf_line):
                                val = int(srf_line)
                                if 50 <= val <= 120:
                                    srfs.append(val)
                        break
        
        if srfs:
            info["recent_srfs"] = srfs[:5]
            info["avg_srf"] = round(sum(srfs[:5]) / len(srfs[:5]), 1)
            info["last_srf"] = srfs[0]
        
        return info
    except Exception as e:
        return {"name": horse_name, "error": str(e)[:100]}


def main():
    print("=" * 60)
    print("COMPETITIVE INTELLIGENCE — RACE FIELD ANALYSIS")
    print("=" * 60)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(AUTH_PATH)) if AUTH_PATH.exists() else browser.new_context()
        page = context.new_page()
        
        all_results = []
        
        for race in RACES:
            print(f"\n{'='*60}")
            print(f"RACE: {race['track']} R{race['race']} ({race['date']}) — {race['class']} {race['dist']}")
            print(f"OUR HORSE: {race['our_horse']}")
            print(f"{'='*60}")
            
            # Navigate to entries page for this track
            url = f"https://www.horseracingpark.com/races/entries.aspx?track={race['track']}"
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            
            body_text = page.inner_text("body")
            
            # Find horse names from the entries page
            # HRP entries pages list horses with links to their profiles
            horse_links = page.query_selector_all("a[href*='viewhorse'], a[href*='horsename']")
            
            # Also try to find the specific race section
            # Look for Race # heading then extract entries below it
            race_header = f"Race #{race['race']}"
            
            # Try clicking into the specific race
            all_links = page.query_selector_all("a")
            clicked = False
            for link in all_links:
                try:
                    lt = link.inner_text().strip()
                    if race_header in lt or (f"#{race['race']}" in lt and "Race" in lt):
                        link.click()
                        time.sleep(3)
                        clicked = True
                        break
                except:
                    pass
            
            if not clicked:
                # Try finding race by number in the page
                for link in all_links:
                    try:
                        href = link.get_attribute("href") or ""
                        if f"race={race['race']}" in href.lower() or f"racenum={race['race']}" in href.lower():
                            link.click()
                            time.sleep(3)
                            clicked = True
                            break
                    except:
                        pass
            
            # Get updated page text
            body_text = page.inner_text("body")
            
            # Extract horse names from the page
            # Look for links to horse profiles
            horse_links = page.query_selector_all("a[href*='viewhorse'], a[href*='horsename']")
            horse_names = []
            for hl in horse_links:
                try:
                    name = hl.inner_text().strip()
                    href = hl.get_attribute("href") or ""
                    if name and len(name) > 2 and "horsename" in href.lower():
                        if name not in horse_names and name not in ("View", "Profile", "All Races"):
                            horse_names.append(name)
                except:
                    pass
            
            print(f"  Found {len(horse_names)} horses in field: {horse_names}")
            
            # Now scrape each competitor's PP
            race_result = {
                "race": race,
                "field": [],
            }
            
            for hname in horse_names:
                print(f"  Scouting: {hname}...", end=" ")
                info = scrape_horse_pp(page, hname)
                race_result["field"].append(info)
                
                if "error" in info:
                    print(f"ERROR: {info['error']}")
                elif info.get("record"):
                    srf_str = f"SRF: {info.get('avg_srf', '?')}" if info.get('avg_srf') else "No SRF"
                    print(f"{info['record']} ${info.get('earnings',0):.2f} {srf_str}")
                else:
                    print("No data")
                
                time.sleep(2)  # Be polite
            
            all_results.append(race_result)
            
            # Go back to entries page for next race
            time.sleep(2)
        
        browser.close()
    
    # Save results
    output_path = OUTPUT / "competitive_intel.json"
    output_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
    
    # Print summary report
    print("\n\n" + "=" * 60)
    print("COMPETITIVE ANALYSIS SUMMARY")
    print("=" * 60)
    
    for race_data in all_results:
        race = race_data["race"]
        field = race_data["field"]
        our_horse = race["our_horse"]
        
        print(f"\n{race['track']} R{race['race']} ({race['date']}) — {race['class']} {race['dist']}")
        print(f"  Field size: {len(field)}")
        print(f"  {'Horse':25s} {'Record':12s} {'Earn':>8s} {'AvgSRF':>7s} {'BestSRF':>8s}")
        print(f"  {'-'*65}")
        
        for h in sorted(field, key=lambda x: x.get("avg_srf", 0), reverse=True):
            marker = " ★" if h["name"] == our_horse else ""
            record = h.get("record", "?")
            earnings = f"${h.get('earnings', 0):.2f}" if h.get("earnings") is not None else "?"
            avg_srf = f"{h.get('avg_srf', '?')}" if h.get("avg_srf") else "---"
            best_srf = f"{h.get('best_srf', '?')}" if h.get("best_srf") else "---"
            print(f"  {h['name']:25s} {record:12s} {earnings:>8s} {avg_srf:>7s} {best_srf:>8s}{marker}")
    
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
