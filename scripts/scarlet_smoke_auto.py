"""scarlet_smoke_auto.py -- Fully automated training for Scarlet Smoke.

Runs daily via Task Scheduler. Checks if today is a work day,
submits the timed work with zero human interaction.

Usage:
    python scripts/scarlet_smoke_auto.py          # Auto-run (scheduled)
    python scripts/scarlet_smoke_auto.py --dry    # Preview only
    python scripts/scarlet_smoke_auto.py --force  # Force work today
"""

import json, sys, re, argparse
from pathlib import Path
from datetime import datetime, date
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "inputs" / "export" / "auth.json"
LOG_FILE = ROOT / "outputs" / "scarlet_smoke_log.json"

HORSE_NAME = "Scarlet Smoke"

# ═══════════════════════════════════════════
# TRAINING SCHEDULE
# ═══════════════════════════════════════════
# Format: date -> {settings}
# Phase 1: 3f Baseline works (Conservative/Breezing/Horse Lead)
# Phase 2+: 5f Surface Discovery, Equipment, Medication tests

SCHEDULE = {
    # Phase 1: 3f Baselines (she did :36.2b on Feb 27)
    "2026-03-02": {"phase": "1-Baseline",   "distance": "3", "surface": "0", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse"},
    "2026-03-05": {"phase": "1-Baseline",   "distance": "3", "surface": "0", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse"},
    "2026-03-08": {"phase": "1-Baseline",   "distance": "3", "surface": "0", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse"},
    # Phase 2: 5f Surface Discovery (dirt then turf)
    "2026-03-11": {"phase": "2-Dirt5f",     "distance": "7", "surface": "0", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse"},
    "2026-03-14": {"phase": "2-Turf5f",     "distance": "7", "surface": "1", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse"},
    # Phase 3: Equipment Test (blinkers on best surface)
    "2026-03-17": {"phase": "3-Blinkers",   "distance": "7", "surface": "0", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_blinkers": True},
    # Phase 4: Medication Test (lasix)
    "2026-03-20": {"phase": "4-Lasix",      "distance": "7", "surface": "0", "effort": "Breezing", "weight": "120", "startpace": "2", "pace": "TimeHorse", "add_lasix": True},
}


def load_log():
    if LOG_FILE.exists():
        return json.load(open(LOG_FILE, "r", encoding="utf-8"))
    return {"works": [{"date": "2026-02-27", "phase": "1-Baseline", "time": ":36.2b", "distance": "3f", "surface": "Dirt", "status": "manual"}]}


def save_log(log):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(log, open(LOG_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def check_meters(page):
    """Read current meters."""
    url_name = HORSE_NAME.replace(" ", "+")
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

    for key in ("condition", "stamina"):
        raw = meters.get(key, "100%")
        try:
            meters[key + "_val"] = float(raw.replace("%", ""))
        except ValueError:
            meters[key + "_val"] = 100.0

    return meters


def add_accessory(page, accessory):
    """Add blinkers or shadow roll."""
    url_name = HORSE_NAME.replace(" ", "+")
    url = f"https://www.horseracingpark.com/stables/viewhorse.aspx?horsename={url_name}"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    links = page.query_selector_all("a")
    for link in links:
        text = link.inner_text()
        href = link.get_attribute("href") or ""
        if accessory.lower() in text.lower() or accessory.lower() in href.lower():
            link.click()
            page.wait_for_timeout(2000)
            return True
    return False


def add_medication(page, medication):
    """Add lasix or bute."""
    url_name = HORSE_NAME.replace(" ", "+")
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


def submit_work(page, settings, dry_run=False):
    """Submit a timed work."""
    url_name = HORSE_NAME.replace(" ", "+")
    url = f"https://www.horseracingpark.com/stables/trainhorse.aspx?horsename={url_name}"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)

    # Fill form
    page.select_option("select[name='distance']", settings["distance"])
    page.select_option("select[name='surface']", settings["surface"])
    page.select_option("select[name='effort']", settings["effort"])
    page.select_option("select[name='weight']", settings["weight"])
    page.select_option("select[name='startpace']", settings["startpace"])

    pace_selects = page.query_selector_all("select[name='pace']")
    if len(pace_selects) >= 2:
        pace_selects[1].select_option(settings["pace"])

    dist_map = {"3": "3f", "7": "5f", "9": "6f", "13": "1m"}
    dist_label = dist_map.get(settings["distance"], settings["distance"])
    surface_label = "Dirt" if settings["surface"] == "0" else "Turf"

    if dry_run:
        print(f"  [DRY RUN] Would submit: {dist_label} {surface_label} {settings['effort']}")
        return {"status": "dry_run", "distance": dist_label, "surface": surface_label}

    # Click Work button
    work_buttons = page.query_selector_all("input[name='submit1'][value='Work']")
    if work_buttons:
        work_buttons[0].click()
        page.wait_for_timeout(3000)

        result_html = page.content()
        result_soup = BeautifulSoup(result_html, "html.parser")
        result_text = result_soup.get_text("\n", strip=True)

        # Extract work time
        time_match = re.search(r"(\d+:\d+\.\d+|\d+\.\d+)[bBhH]?", result_text)
        work_time = time_match.group(0) if time_match else "unknown"

        return {"status": "submitted", "distance": dist_label, "surface": surface_label, "time": work_time}
    else:
        return {"status": "error", "message": "Work button not found"}


def run(dry_run=False, force=False):
    today_str = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*50}")
    print(f"Scarlet Smoke Auto-Trainer -- {today_str}")
    print(f"{'='*50}")

    # Check if today is a work day
    if today_str not in SCHEDULE and not force:
        print(f"  Not a work day. Next work days: ", end="")
        future = sorted(d for d in SCHEDULE if d > today_str)
        print(", ".join(future[:3]) if future else "none scheduled")
        print("  Exiting.")
        return

    if force and today_str not in SCHEDULE:
        # Force mode: use the next scheduled settings
        future = sorted(d for d in SCHEDULE if d >= today_str)
        if not future:
            print("  No future works scheduled. Exiting.")
            return
        settings = SCHEDULE[future[0]].copy()
        print(f"  [FORCE] Using settings from {future[0]}: {settings['phase']}")
    else:
        settings = SCHEDULE[today_str].copy()

    phase = settings.pop("phase", "unknown")
    do_blinkers = settings.pop("add_blinkers", False)
    do_lasix = settings.pop("add_lasix", False)
    do_shadowroll = settings.pop("add_shadowroll", False)

    print(f"  Phase: {phase}")
    print(f"  Settings: {settings['distance']}={'3f' if settings['distance']=='3' else '5f'} "
          f"{'Dirt' if settings['surface']=='0' else 'Turf'} {settings['effort']}")

    if not AUTH.exists():
        print("  ERROR: auth.json not found. Run 01_login_save_state.py first.")
        return

    log = load_log()

    # Check if already worked today
    if any(w.get("date") == today_str and w.get("status") in ("submitted", "manual") for w in log["works"]):
        print("  Already worked today. Skipping.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(AUTH))
        page = ctx.new_page()

        # Check meters
        meters = check_meters(page)
        cond = meters.get("condition_val", 100)
        stam = meters.get("stamina_val", 100)
        print(f"  Meters: Condition={cond:.0f}% Stamina={stam:.0f}%")

        if stam < 50:
            print(f"  SKIP: Stamina {stam:.0f}% too low (need >= 50)")
            log["works"].append({"date": today_str, "phase": phase, "status": "skipped", "reason": f"stamina {stam:.0f}%"})
            save_log(log)
            ctx.close()
            browser.close()
            return

        # Add accessories/meds if needed
        if do_blinkers and not dry_run:
            print("  Adding blinkers...")
            add_accessory(page, "blinkers")
        if do_shadowroll and not dry_run:
            print("  Adding shadow roll...")
            add_accessory(page, "shadowroll")
        if do_lasix and not dry_run:
            print("  Adding lasix...")
            add_medication(page, "lasix")

        # Submit work
        result = submit_work(page, settings, dry_run=dry_run)
        print(f"  Result: {result['status']} -- {result.get('time', result.get('distance', ''))}")

        # Post-work meters
        if not dry_run:
            page.wait_for_timeout(2000)
            post = check_meters(page)
            print(f"  Post-work: Condition={post.get('condition_val', '?'):.0f}% Stamina={post.get('stamina_val', '?'):.0f}%")
            result["post_condition"] = post.get("condition_val")
            result["post_stamina"] = post.get("stamina_val")

        ctx.close()
        browser.close()

    # Log it
    result["date"] = today_str
    result["phase"] = phase
    result["pre_condition"] = cond
    result["pre_stamina"] = stam
    log["works"].append(result)
    save_log(log)

    print(f"\n  Log saved to: {LOG_FILE}")
    print(f"{'='*50}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scarlet Smoke Auto-Trainer")
    parser.add_argument("--dry", action="store_true", help="Dry run -- preview only")
    parser.add_argument("--force", action="store_true", help="Force work today even if not scheduled")
    args = parser.parse_args()
    run(dry_run=args.dry, force=args.force)
