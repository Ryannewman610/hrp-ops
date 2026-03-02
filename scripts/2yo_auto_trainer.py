"""2YO Auto-Trainer — Execute the approved training plan phases.

Usage:
    python scripts/2yo_auto_trainer.py                  # Check status, recommend action
    python scripts/2yo_auto_trainer.py --phase 2        # Execute Phase 2 works
    python scripts/2yo_auto_trainer.py --phase 2 --dry  # Dry run (show what would happen)

Each phase is defined in the PLAN dict below. The script:
  1. Checks each horse's current meters (condition/stamina)
  2. Verifies readiness (stamina >= 50 for works)
  3. Submits the timed work via Playwright
  4. Records the result
  5. Saves a log to outputs/2yo_training_log.json
"""

import json, sys, re, argparse
from pathlib import Path
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "inputs" / "export" / "auth.json"
LOG_FILE = ROOT / "outputs" / "2yo_training_log.json"

# ═══════════════════════════════════════════
# PLAN CONFIGURATION
# ═══════════════════════════════════════════

# Distance mapping: value -> label
DIST_MAP = {
    "1": "2f", "2": "2.5f", "3": "3f", "4": "3.5f",
    "5": "4f", "6": "4.5f", "7": "5f", "8": "5.5f",
    "9": "6f", "10": "6.5f", "11": "7f", "12": "7.5f", "13": "1m"
}

PLAN = {
    1: {
        "name": "Scarlet Smoke — Baseline 3f Works",
        "earliest": "2026-03-02",
        "description": "Baseline 3f farm works for new foal. First work done 2/27 (:36.2b). Rest 2 days between works.",
        "horses": {
            "Scarlet Smoke":        {"distance": "3", "surface": "0", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse"},
        }
    },
    # Scarlet Smoke Phase 1 schedule: Run phase 1 on Mar 2, 5, 8 (re-run 3x)
    # Then she joins Phase 2+ with the other horses for 5f works
    2: {
        "name": "Surface Discovery",
        "earliest": "2026-03-01",
        "description": "Test turf aptitude. Colts go handily, fillies breeze.",
        "horses": {
            "Neon Reflection":      {"distance": "7", "surface": "1", "effort": "Handily",  "weight": "120", "startpace": "2", "pace": "TimeHorse"},
            "Looks Like Nicholas":  {"distance": "7", "surface": "1", "effort": "Handily",  "weight": "120", "startpace": "2", "pace": "TimeHorse"},
            "Film The Scene":       {"distance": "7", "surface": "1", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse"},
            "Blank Sunset":         {"distance": "7", "surface": "1", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse"},
            "Gen Xpress":           {"distance": "7", "surface": "1", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse"},
            "Scarlet Smoke":        {"distance": "7", "surface": "1", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse"},
        }
    },
    3: {
        "name": "Equipment Test (Blinkers)",
        "earliest": "2026-03-08",
        "description": "Test blinkers on all horses. Use each horse's best surface from Phase 2.",
        "horses": {
            "Neon Reflection":      {"distance": "7", "surface": "TBD", "effort": "Handily",  "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_blinkers": True},
            "Looks Like Nicholas":  {"distance": "7", "surface": "TBD", "effort": "Handily",  "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_blinkers": True},
            "Film The Scene":       {"distance": "7", "surface": "TBD", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_blinkers": True},
            "Blank Sunset":         {"distance": "7", "surface": "0",   "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_blinkers": True},
            "Gen Xpress":           {"distance": "7", "surface": "0",   "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_blinkers": True},
            "Scarlet Smoke":        {"distance": "7", "surface": "0",   "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_blinkers": True},
        }
    },
    4: {
        "name": "Medication Test (Lasix)",
        "earliest": "2026-03-15",
        "description": "Test lasix on all horses. Confirm best equipment + medication.",
        "horses": {
            "Neon Reflection":      {"distance": "7", "surface": "TBD", "effort": "Handily",  "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_lasix": True},
            "Looks Like Nicholas":  {"distance": "7", "surface": "TBD", "effort": "Handily",  "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_lasix": True},
            "Film The Scene":       {"distance": "7", "surface": "TBD", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_lasix": True},
            "Blank Sunset":         {"distance": "3", "surface": "0",   "effort": "Handily",  "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_lasix": True},
            "Gen Xpress":           {"distance": "7", "surface": "0",   "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_shadowroll": True},
            "Scarlet Smoke":        {"distance": "7", "surface": "0",   "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_lasix": True},
        }
    },
}


def load_log():
    if LOG_FILE.exists():
        return json.load(open(LOG_FILE, "r", encoding="utf-8"))
    return {"phases_completed": [], "works": []}


def save_log(log):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(log, open(LOG_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def check_meters(page, horse_name):
    """Read current meters for a horse from the viewmeters page."""
    url_name = horse_name.replace(" ", "+")
    url = f"https://www.horseracingpark.com/stables/viewmeters.aspx?horsename={url_name}&details=1"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    
    meters = {}
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "Condition:" in line and i + 1 < len(lines):
            meters["condition"] = lines[i + 1].strip()
        elif "Stamina:" in line and i + 1 < len(lines):
            meters["stamina"] = lines[i + 1].strip()
        elif "Consistency:" in line and i + 1 < len(lines):
            meters["consistency"] = lines[i + 1].strip()
    
    # Parse numeric values
    for key in ("condition", "stamina"):
        raw = meters.get(key, "100%")
        try:
            meters[key + "_val"] = float(raw.replace("%", ""))
        except ValueError:
            meters[key + "_val"] = 100.0
    
    return meters


def add_accessory(page, horse_name, accessory):
    """Add an accessory (blinkers/shadowroll) to a horse."""
    url_name = horse_name.replace(" ", "+")
    url = f"https://www.horseracingpark.com/stables/viewhorse.aspx?horsename={url_name}"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    # Look for accessory links
    html = page.content()
    if accessory.lower() == "blinkers":
        # Find and click the blinkers add link
        links = page.query_selector_all("a")
        for link in links:
            text = link.inner_text()
            href = link.get_attribute("href") or ""
            if "blinker" in text.lower() or "blinker" in href.lower():
                link.click()
                page.wait_for_timeout(2000)
                return True
    elif accessory.lower() == "shadowroll":
        links = page.query_selector_all("a")
        for link in links:
            text = link.inner_text()
            href = link.get_attribute("href") or ""
            if "shadow" in text.lower() or "shadow" in href.lower():
                link.click()
                page.wait_for_timeout(2000)
                return True
    return False


def add_medication(page, horse_name, medication):
    """Add medication (lasix/bute) to a horse."""
    url_name = horse_name.replace(" ", "+")
    url = f"https://www.horseracingpark.com/stables/viewhorse.aspx?horsename={url_name}"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    links = page.query_selector_all("a")
    for link in links:
        text = link.inner_text()
        href = link.get_attribute("href") or ""
        if medication.lower() in text.lower() or medication.lower() in href.lower():
            link.click()
            page.wait_for_timeout(2000)
            return True
    return False


def submit_work(page, horse_name, settings, dry_run=False):
    """Submit a timed work for a horse via the trainhorse.aspx form."""
    url_name = horse_name.replace(" ", "+")
    url = f"https://www.horseracingpark.com/stables/trainhorse.aspx?horsename={url_name}"
    
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    
    # Select distance
    page.select_option("select[name='distance']", settings["distance"])
    # Select surface
    page.select_option("select[name='surface']", settings["surface"])
    # Select effort
    page.select_option("select[name='effort']", settings["effort"])
    # Select weight
    page.select_option("select[name='weight']", settings["weight"])
    # Select start pace
    page.select_option("select[name='startpace']", settings["startpace"])
    # Select pace (the second 'pace' select)
    pace_selects = page.query_selector_all("select[name='pace']")
    if len(pace_selects) >= 2:
        pace_selects[1].select_option(settings["pace"])
    
    dist_label = DIST_MAP.get(settings["distance"], settings["distance"])
    surface_label = "Dirt" if settings["surface"] == "0" else "Turf"
    
    if dry_run:
        print(f"  [DRY RUN] Would submit: {dist_label} {surface_label} {settings['effort']} {settings['weight']}lbs")
        return {"status": "dry_run", "settings": f"{dist_label} {surface_label} {settings['effort']}"}
    
    # Click the "Work" submit button (second submit1)
    work_buttons = page.query_selector_all("input[name='submit1'][value='Work']")
    if work_buttons:
        work_buttons[0].click()
        page.wait_for_timeout(3000)
        
        # Read the result page
        result_html = page.content()
        result_soup = BeautifulSoup(result_html, "html.parser")
        result_text = result_soup.get_text("\n", strip=True)
        
        # Extract work time from result
        time_match = re.search(r"(\d+:\d+\.\d+|\d+\.\d+)[bBhH]?", result_text)
        
        return {
            "status": "submitted",
            "settings": f"{dist_label} {surface_label} {settings['effort']}",
            "result_snippet": result_text[:500]
        }
    else:
        return {"status": "error", "message": "Work button not found"}


def execute_phase(phase_num, dry_run=False):
    """Execute a specific phase of the training plan."""
    if phase_num not in PLAN:
        print(f"ERROR: Phase {phase_num} not found in plan")
        return
    
    phase = PLAN[phase_num]
    log = load_log()
    
    print(f"\n{'='*60}")
    print(f"PHASE {phase_num}: {phase['name']}")
    print(f"Description: {phase['description']}")
    print(f"Earliest date: {phase['earliest']}")
    print(f"{'='*60}")
    
    today = datetime.now().strftime("%Y-%m-%d")
    if today < phase["earliest"] and not dry_run:
        print(f"\nWARNING: Today ({today}) is before earliest date ({phase['earliest']})")
        resp = input("Continue anyway? (y/n): ").strip().lower()
        if resp != "y":
            print("Aborted.")
            return
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(AUTH)) if AUTH.exists() else browser.new_context()
        page = ctx.new_page()
        
        results = []
        
        for horse_name, settings in phase["horses"].items():
            print(f"\n--- {horse_name} ---")
            
            # Check meters first
            meters = check_meters(page, horse_name)
            cond = meters.get("condition_val", 100)
            stam = meters.get("stamina_val", 100)
            cons = meters.get("consistency", "?")
            print(f"  Meters: Cond={cond:.0f}% Stam={stam:.0f}% Cons={cons}")
            
            # Check readiness
            if stam < 50:
                print(f"  SKIP: Stamina {stam:.0f}% too low (need >= 50)")
                results.append({"horse": horse_name, "status": "skipped", "reason": f"stamina {stam:.0f}%"})
                continue
            
            if cond < 50:
                print(f"  WARNING: Condition {cond:.0f}% is in degradation zone!")
            
            # Handle TBD surface (use best from previous phase)
            if settings.get("surface") == "TBD":
                # Default to dirt until Phase 2 results are analyzed
                settings["surface"] = "0"
                # Check log for Phase 2 results to determine best surface
                for work in log.get("works", []):
                    if work.get("horse") == horse_name and work.get("phase") == 2:
                        # If turf time was good, keep turf
                        settings["surface"] = work.get("best_surface", "0")
                        break
                print(f"  Surface resolved to: {'Dirt' if settings['surface'] == '0' else 'Turf'}")
            
            # Add accessories if specified
            if settings.get("add_blinkers") and not dry_run:
                print(f"  Adding blinkers...")
                add_accessory(page, horse_name, "blinkers")
            
            if settings.get("add_shadowroll") and not dry_run:
                print(f"  Adding shadow roll...")
                add_accessory(page, horse_name, "shadowroll")
            
            if settings.get("add_lasix") and not dry_run:
                print(f"  Adding lasix...")
                add_medication(page, horse_name, "lasix")
            
            # Submit the work
            result = submit_work(page, horse_name, settings, dry_run=dry_run)
            result["horse"] = horse_name
            result["phase"] = phase_num
            result["date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            result["pre_condition"] = cond
            result["pre_stamina"] = stam
            results.append(result)
            
            print(f"  Result: {result['status']} - {result.get('settings', '')}")
            
            page.wait_for_timeout(2000)
        
        # Read post-work meters
        if not dry_run:
            print(f"\n--- Post-Work Meter Check ---")
            for horse_name in phase["horses"]:
                meters = check_meters(page, horse_name)
                print(f"  {horse_name}: Cond={meters.get('condition_val', '?'):.0f}% Stam={meters.get('stamina_val', '?'):.0f}%")
        
        ctx.close()
        browser.close()
    
    # Save results to log
    log["works"].extend(results)
    if not dry_run:
        log["phases_completed"].append({"phase": phase_num, "date": today, "count": len(results)})
    save_log(log)
    
    print(f"\n{'='*60}")
    print(f"Phase {phase_num} {'DRY RUN' if dry_run else 'COMPLETE'}. {len(results)} works processed.")
    print(f"Log saved to: {LOG_FILE}")


def show_status():
    """Show current plan status and recommendations."""
    log = load_log()
    completed = {p["phase"] for p in log.get("phases_completed", [])}
    today = datetime.now()
    
    print("\n2YO TRAINING PLAN STATUS")
    print("=" * 50)
    
    for phase_num, phase in sorted(PLAN.items()):
        earliest = datetime.strptime(phase["earliest"], "%Y-%m-%d")
        status = "DONE" if phase_num in completed else ("READY" if today >= earliest else f"WAIT until {phase['earliest']}")
        marker = "[x]" if phase_num in completed else ("[ ]" if today < earliest else "[>]")
        print(f"  {marker} Phase {phase_num}: {phase['name']} — {status}")
    
    # Next action
    for phase_num in sorted(PLAN.keys()):
        if phase_num not in completed:
            earliest = datetime.strptime(PLAN[phase_num]["earliest"], "%Y-%m-%d")
            days_until = (earliest - today).days
            if days_until <= 0:
                print(f"\n  >> READY: Run `python scripts/2yo_auto_trainer.py --phase {phase_num}`")
            else:
                print(f"\n  >> NEXT: Phase {phase_num} in {days_until} days ({PLAN[phase_num]['earliest']})")
            break
    
    # Show recent works
    recent = log.get("works", [])[-5:]
    if recent:
        print(f"\nRecent works:")
        for w in recent:
            print(f"  {w.get('date', '?')} | {w.get('horse', '?')} | {w.get('settings', '?')} | {w.get('status', '?')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="2YO Auto-Trainer")
    parser.add_argument("--phase", type=int, help="Phase number to execute (2-4)")
    parser.add_argument("--dry", action="store_true", help="Dry run — show what would happen")
    args = parser.parse_args()
    
    if args.phase:
        execute_phase(args.phase, dry_run=args.dry)
    else:
        show_status()
