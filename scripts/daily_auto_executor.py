"""daily_auto_executor.py -- Unified daily trainer for ALL horses.

Reads the peak_plan JSON (from 17_peak_planner.py) and auto-executes
today's WORK actions for every horse in the stable. Also handles
Scarlet Smoke's specific development schedule.

Runs daily via Task Scheduler. Zero human interaction.

Usage:
    python scripts/daily_auto_executor.py          # Auto-execute today's plan
    python scripts/daily_auto_executor.py --dry    # Preview only
    python scripts/daily_auto_executor.py --horse "Class A"  # Single horse only
"""

import json, sys, re, argparse, time
from pathlib import Path
from datetime import datetime, date
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "inputs" / "export" / "auth.json"
OUTPUTS = ROOT / "outputs"
LOG_FILE = OUTPUTS / "daily_executor_log.json"

# Default work settings for fitness maintenance works
DEFAULT_WORK = {
    "distance": "7",       # 5f
    "surface": "0",        # Dirt
    "effort": "Breezing",
    "weight": "120",
    "startpace": "2",      # Normal
    "pace": "TimeHorse",
}

# Scarlet Smoke has specific development settings by date
SCARLET_SMOKE_OVERRIDES = {
    "2026-03-02": {"distance": "3", "surface": "0", "effort": "Breezing", "phase": "1-Baseline-3f"},
    "2026-03-05": {"distance": "3", "surface": "0", "effort": "Breezing", "phase": "1-Baseline-3f"},
    "2026-03-08": {"distance": "3", "surface": "0", "effort": "Breezing", "phase": "1-Baseline-3f"},
    "2026-03-11": {"distance": "7", "surface": "0", "effort": "Breezing", "phase": "2-Dirt-5f"},
    "2026-03-14": {"distance": "7", "surface": "1", "effort": "Breezing", "phase": "2-Turf-5f"},
    "2026-03-17": {"distance": "7", "surface": "0", "effort": "Breezing", "phase": "3-Blinkers", "add_blinkers": True},
    "2026-03-20": {"distance": "7", "surface": "0", "effort": "Breezing", "phase": "4-Lasix", "add_lasix": True},
}

DIST_MAP = {
    "1": "2f", "2": "2.5f", "3": "3f", "4": "3.5f",
    "5": "4f", "6": "4.5f", "7": "5f", "8": "5.5f",
    "9": "6f", "10": "6.5f", "11": "7f", "12": "7.5f", "13": "1m"
}


def load_peak_plan(today_str):
    """Load the most recent peak_plan JSON."""
    exact = OUTPUTS / f"peak_plan_{today_str}.json"
    if exact.exists():
        return json.loads(exact.read_text(encoding="utf-8"))
    # Fallback to most recent
    plans = sorted(OUTPUTS.glob("peak_plan_*.json"), reverse=True)
    if plans:
        print(f"  Using fallback plan: {plans[0].name}")
        return json.loads(plans[0].read_text(encoding="utf-8"))
    return None


def load_log():
    if LOG_FILE.exists():
        return json.load(open(LOG_FILE, "r", encoding="utf-8"))
    return {"executions": []}


def save_log(log):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(log, open(LOG_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def check_meters(page, horse_name):
    """Read current meters for a horse."""
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

    for key in ("condition", "stamina"):
        raw = meters.get(key, "100%")
        try:
            meters[key + "_val"] = float(raw.replace("%", ""))
        except ValueError:
            meters[key + "_val"] = 100.0

    return meters


def add_accessory(page, horse_name, accessory):
    """Add blinkers or shadow roll."""
    url_name = horse_name.replace(" ", "+")
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


def add_medication(page, horse_name, medication):
    """Add lasix or bute."""
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
    """Submit a timed work for a horse."""
    url_name = horse_name.replace(" ", "+")
    url = f"https://www.horseracingpark.com/stables/trainhorse.aspx?horsename={url_name}"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)

    page.select_option("select[name='distance']", settings["distance"])
    page.select_option("select[name='surface']", settings["surface"])
    page.select_option("select[name='effort']", settings["effort"])
    page.select_option("select[name='weight']", settings["weight"])
    page.select_option("select[name='startpace']", settings["startpace"])

    pace_selects = page.query_selector_all("select[name='pace']")
    if len(pace_selects) >= 2:
        pace_selects[1].select_option(settings["pace"])

    dist_label = DIST_MAP.get(settings["distance"], settings["distance"])
    surface_label = "Dirt" if settings["surface"] == "0" else "Turf"

    if dry_run:
        print(f"    [DRY] Would submit: {dist_label} {surface_label} {settings['effort']}")
        return {"status": "dry_run", "distance": dist_label, "surface": surface_label}

    work_buttons = page.query_selector_all("input[name='submit1'][value='Work']")
    if work_buttons:
        work_buttons[0].click()
        page.wait_for_timeout(3000)

        result_html = page.content()
        result_soup = BeautifulSoup(result_html, "html.parser")
        result_text = result_soup.get_text("\n", strip=True)

        time_match = re.search(r"(\d+:\d+\.\d+|\d+\.\d+)[bBhH]?", result_text)
        work_time = time_match.group(0) if time_match else "unknown"

        return {"status": "submitted", "distance": dist_label, "surface": surface_label, "time": work_time}
    else:
        return {"status": "error", "message": "Work button not found"}


def get_work_settings(horse_name, today_str):
    """Get work settings for a horse. Uses overrides for Scarlet Smoke, defaults for others."""
    if horse_name == "Scarlet Smoke" and today_str in SCARLET_SMOKE_OVERRIDES:
        override = SCARLET_SMOKE_OVERRIDES[today_str].copy()
        phase = override.pop("phase", "")
        add_blinkers = override.pop("add_blinkers", False)
        add_lasix = override.pop("add_lasix", False)
        settings = {**DEFAULT_WORK, **override}
        return settings, phase, add_blinkers, add_lasix

    return DEFAULT_WORK.copy(), "fitness", False, False


def run(dry_run=False, single_horse=None):
    today_str = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"  Daily Auto-Executor -- {today_str}")
    print(f"{'='*60}")

    # Load peak plan
    plan = load_peak_plan(today_str)
    if not plan:
        print("  ERROR: No peak_plan found. Run the daily pipeline first.")
        print("  (scripts/RUN_DAILY.bat or python scripts/17_peak_planner.py)")
        return

    plan_date = plan.get("generated", "unknown")
    print(f"  Plan date: {plan_date} | Horses: {plan.get('total_horses', '?')}")

    # Find today's WORK actions
    work_horses = []
    rest_horses = []
    for horse_plan in plan.get("plans", []):
        name = horse_plan["horse_name"]
        if single_horse and name.lower() != single_horse.lower():
            continue

        # Find today's action in daily_plan
        today_action = None
        for day in horse_plan.get("daily_plan", []):
            if day["date"] == today_str:
                today_action = day
                break

        if not today_action:
            # Plan may be stale -- check date offset
            # If today isn't in the plan window, default to WORK/REST based on 3-day cycle
            plan_start = plan.get("window", {}).get("start", "")
            if plan_start and today_str > plan.get("window", {}).get("end", ""):
                # Plan expired -- use simple 3-day cycle (WRRWRR)
                days_since_start = (date.fromisoformat(today_str) - date.fromisoformat(plan_start)).days
                if days_since_start % 3 == 0:
                    today_action = {"action": "WORK", "work_type": "timed", "reason": "Cycle fallback"}
                else:
                    today_action = {"action": "REST", "reason": "Cycle fallback"}
            else:
                continue

        if today_action["action"] == "WORK":
            work_horses.append({
                "name": name,
                "reason": today_action.get("reason", ""),
                "stamina": horse_plan.get("stamina", 100),
                "condition": horse_plan.get("condition", 100),
                "sharpness": horse_plan.get("sharpness_index", 0),
                "readiness": horse_plan.get("readiness_index", 0),
                "form_cycle": horse_plan.get("form_cycle", "UNKNOWN"),
            })
        else:
            rest_horses.append(name)

    # Also add Scarlet Smoke if she has an override today and isn't in the plan
    if today_str in SCARLET_SMOKE_OVERRIDES:
        if not any(h["name"] == "Scarlet Smoke" for h in work_horses):
            work_horses.append({
                "name": "Scarlet Smoke",
                "reason": f"Dev schedule: {SCARLET_SMOKE_OVERRIDES[today_str].get('phase', '')}",
                "stamina": 100, "condition": 100,
                "sharpness": 0, "readiness": 0,
                "form_cycle": "DEVELOPMENT",
            })

    print(f"\n  Today: {len(work_horses)} horses to WORK, {len(rest_horses)} resting")
    if not work_horses:
        print("  No works needed today. Exiting.")
        return

    for h in work_horses:
        settings, phase, _, _ = get_work_settings(h["name"], today_str)
        dist = DIST_MAP.get(settings["distance"], settings["distance"])
        surf = "Dirt" if settings["surface"] == "0" else "Turf"
        print(f"    {h['name']:25s} | {dist} {surf} {settings['effort']:8s} | {h['reason']}")

    if not AUTH.exists():
        print("\n  ERROR: auth.json not found. Run 01_login_save_state.py first.")
        return

    # Execute
    log = load_log()
    today_log = {"date": today_str, "horses": []}

    # Check for duplicate execution today
    if any(e["date"] == today_str for e in log["executions"]):
        print("\n  WARNING: Already executed today. Skipping to prevent double-work.")
        print("  Remove today's entry from daily_executor_log.json to force re-run.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(AUTH))
        page = ctx.new_page()

        worked = 0
        skipped = 0

        for h in work_horses:
            name = h["name"]
            print(f"\n  --- {name} ---")

            # Check live meters
            meters = check_meters(page, name)
            cond = meters.get("condition_val", 100)
            stam = meters.get("stamina_val", 100)
            print(f"    Meters: Cond={cond:.0f}% Stam={stam:.0f}%")

            if stam < 50:
                print(f"    SKIP: Stamina {stam:.0f}% too low")
                today_log["horses"].append({"name": name, "status": "skipped", "reason": f"stamina {stam:.0f}%"})
                skipped += 1
                continue

            # Get work settings
            settings, phase, add_blinkers, add_lasix = get_work_settings(name, today_str)

            # Handle accessories/meds
            if add_blinkers and not dry_run:
                print(f"    Adding blinkers...")
                add_accessory(page, name, "blinkers")
            if add_lasix and not dry_run:
                print(f"    Adding lasix...")
                add_medication(page, name, "lasix")

            # Submit work
            result = submit_work(page, name, settings, dry_run=dry_run)
            result["name"] = name
            result["phase"] = phase
            result["pre_condition"] = cond
            result["pre_stamina"] = stam
            result["reason"] = h["reason"]
            today_log["horses"].append(result)

            print(f"    Result: {result['status']} {result.get('time', result.get('distance', ''))}")
            worked += 1

            # Polite delay between horses
            page.wait_for_timeout(1500)

        ctx.close()
        browser.close()

    # Save log
    log["executions"].append(today_log)
    save_log(log)

    print(f"\n{'='*60}")
    print(f"  Done: {worked} worked, {skipped} skipped")
    print(f"  Log: {LOG_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily Auto-Executor")
    parser.add_argument("--dry", action="store_true", help="Dry run -- preview only")
    parser.add_argument("--horse", type=str, help="Execute for single horse only")
    args = parser.parse_args()
    run(dry_run=args.dry, single_horse=args.horse)
