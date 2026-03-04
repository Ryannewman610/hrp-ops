"""dashboard.py — HRP Command Center dashboard.

Local:  python scripts/dashboard.py  →  http://localhost:5050
Cloud:  gunicorn scripts.dashboard:app  (Railway/Render)
"""

import csv
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import (Flask, jsonify, redirect, render_template, request,
                   session, url_for)

# Ensure playbook_engine is importable regardless of CWD
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "playbook_engine",
    str(Path(__file__).resolve().parent / "playbook_engine.py"))
_pe = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_pe)
decay_for_age = _pe.decay_for_age
is_farm = _pe.is_farm
find_optimal_schedule = _pe.find_optimal_schedule
simulate_daily = _pe.simulate_daily
assess_consistency = _pe.assess_consistency
ALL_ACTIONS = _pe.ALL_ACTIONS
REST_KEY = _pe.REST_KEY

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"

# Horses to exclude from all dashboard views
INACTIVE = {"shebasbriar", "averyspluck", "hiptag793004736512"}

import re as _re
def _norm(name):
    return _re.sub(r"[^a-z0-9]", "", name.lower())

app = Flask(__name__,
            template_folder=str(ROOT / "scripts" / "templates"),
            static_folder=str(ROOT / "scripts" / "static"))

# ── Auth Config ──────────────────────────────────────────
# Set via environment variable or defaults for local dev
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "hrp2026").strip()
API_KEY = os.environ.get("API_KEY", "local-dev-key").strip()


def login_required(f):
    """Decorator: redirect to login if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Helpers ──────────────────────────────────────────────

def load_json(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def load_csv_rows(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_latest_snapshot():
    """Find latest snapshot and return data with metadata."""
    for d in sorted(ROOT.glob("inputs/20*-*-*/stable_snapshot.json"), reverse=True):
        data = load_json(d)
        # Add snapshot metadata
        mod_time = datetime.fromtimestamp(d.stat().st_mtime)
        data["_snapshot_date"] = d.parent.name  # e.g., "2026-03-01"
        data["_snapshot_age"] = (datetime.now() - mod_time).total_seconds() / 3600  # hours
        data["_snapshot_path"] = str(d)
        return data
    return {}


# ── Routes ───────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == DASHBOARD_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        return render_template("login.html", error="Wrong password")
    if session.get("logged_in"):
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("dashboard.html")


@app.route("/api/stable")
def api_stable():
    snap = find_latest_snapshot()
    ratings = load_json(OUTPUTS / "model" / "horse_ratings.json")
    horses = []
    for h in snap.get("horses", []):
        name = h.get("name", "")
        if _norm(name) in INACTIVE:
            continue
        rating = ratings.get(name, {})
        horses.append({
            "name": name,
            "sex": h.get("sex", "?"),
            "age": h.get("age", "?"),
            "track": h.get("track", "?"),
            "sire": h.get("sire", "?"),
            "condition": h.get("condition", "?"),
            "stamina": h.get("stamina", "?"),
            "consistency": h.get("consistency", "?"),
            "record": h.get("record", {}),
            "srf_power": rating.get("srf_power", 0),
            "srf_avg": rating.get("srf_avg", 0),
            "srf_best": rating.get("srf_best", 0),
            "srf_last": rating.get("srf_last", 0),
            "srf_trend": rating.get("srf_trend", ""),
            "win_pct": rating.get("win_pct", 0),
            "top3_pct": rating.get("top3_pct", 0),
            "ev_score": rating.get("ev_score", 0),
            "form_status": rating.get("form_status", ""),
            "next_action": rating.get("next_action", ""),
            "elo": rating.get("elo", 1200),
        })
    # Snapshot metadata
    snap_date = snap.get("_snapshot_date", "unknown")
    snap_age_hrs = snap.get("_snapshot_age", 0)
    age_str = f"{snap_age_hrs:.0f}h ago" if snap_age_hrs < 48 else f"{snap_age_hrs/24:.0f}d ago"
    return jsonify({
        "horses": sorted(horses, key=lambda x: -x["srf_power"]),
        "balance": snap.get("balance", "?"),
        "horse_count": len(snap.get("horses", [])),
        "snapshot_date": snap_date,
        "snapshot_age": age_str,
    })


@app.route("/api/rankings")
def api_rankings():
    ratings = load_json(OUTPUTS / "model" / "horse_ratings.json")
    ranked = []
    for name, m in ratings.items():
        if m.get("srf_power", 0) > 0:
            ranked.append({"name": name, **m})
    ranked.sort(key=lambda x: -x["srf_power"])
    return jsonify(ranked)


@app.route("/api/decisions")
def api_decisions():
    path = REPORTS / "Daily_Decisions.md"
    if path.exists():
        return jsonify({"content": path.read_text(encoding="utf-8")})
    return jsonify({"content": "No daily decisions generated yet."})


@app.route("/api/nominations")
def api_nominations():
    """All horses with active nominations, enriched with fitness data."""
    snap = find_latest_snapshot()
    ratings = load_json(OUTPUTS / "model" / "horse_ratings.json")
    # Load peak plans for readiness
    plans = sorted(OUTPUTS.glob("peak_plan_*.json"), reverse=True)
    peak_data = json.loads(plans[0].read_text(encoding="utf-8")) if plans else {}
    readiness_map = {}
    for p in peak_data.get("plans", []):
        readiness_map[p["horse_name"]] = {
            "readiness": p.get("readiness_index", 0),
            "sharpness": p.get("sharpness_index", 0),
            "fatigue": p.get("fatigue_proxy", 0),
        }

    entries = []
    for h in snap.get("horses", []):
        if _norm(h.get("name", "")) in INACTIVE:
            continue
        noms = h.get("nominations", [])
        if not isinstance(noms, list) or not noms:
            continue
        field = noms[0].get("field", "")
        if not field or field == "No nominations.":
            continue
        name = h.get("name", "")
        rating = ratings.get(name, {})
        rdx = readiness_map.get(name, {})
        stam_raw = h.get("stamina", "100%").replace("%", "")
        cond_raw = h.get("condition", "100%").replace("%", "")
        try:
            stam = float(stam_raw)
        except ValueError:
            stam = 0
        try:
            cond = float(cond_raw)
        except ValueError:
            cond = 0
        # Determine fitness status
        if stam < 70:
            status = "REST_NEEDED"
            status_color = "red"
        elif cond < 90:
            status = "LOW_CONDITION"
            status_color = "yellow"
        elif rdx.get("readiness", 0) >= 70:
            status = "RACE_READY"
            status_color = "green"
        else:
            status = "BUILDING"
            status_color = "blue"
        entries.append({
            "name": name,
            "race_class": field,
            "track": h.get("track", "?"),
            "condition": cond,
            "stamina": stam,
            "consistency": h.get("consistency", "?"),
            "srf_power": rating.get("srf_power", 0),
            "win_pct": rating.get("win_pct", 0),
            "readiness": rdx.get("readiness", 0),
            "sharpness": rdx.get("sharpness", 0),
            "fatigue": rdx.get("fatigue", 0),
            "status": status,
            "status_color": status_color,
            "record": h.get("record", {}),
        })
    entries.sort(key=lambda x: -x["readiness"])
    return jsonify(entries)


@app.route("/api/stable-stats")
def api_stable_stats():
    """Aggregate stable performance stats."""
    snap = find_latest_snapshot()
    total_starts = total_wins = total_places = total_shows = 0
    horses_raced = 0
    for h in snap.get("horses", []):
        if _norm(h.get("name", "")) in INACTIVE:
            continue
        rec = h.get("record", {})
        s = int(rec.get("starts", 0))
        w = int(rec.get("wins", 0))
        p = int(rec.get("places", 0))
        sh = int(rec.get("shows", 0))
        if s > 0:
            horses_raced += 1
        total_starts += s
        total_wins += w
        total_places += p
        total_shows += sh
    win_pct = (total_wins / total_starts * 100) if total_starts else 0
    itm_pct = ((total_wins + total_places + total_shows) / total_starts * 100) if total_starts else 0
    return jsonify({
        "balance": snap.get("balance", "?"),
        "total_horses": len(snap.get("horses", [])),
        "horses_raced": horses_raced,
        "total_starts": total_starts,
        "total_wins": total_wins,
        "total_places": total_places,
        "total_shows": total_shows,
        "win_pct": round(win_pct, 1),
        "itm_pct": round(itm_pct, 1),
        "record_str": f"{total_starts}-{total_wins}-{total_places}-{total_shows}",
    })


@app.route("/api/playbook")
def api_playbook():
    """Race Day Playbook — exact daily actions to reach 95-105% C&S on race day.

    Uses official HRP mechanics via playbook_engine module:
    - All training types (standard/heavy, short/long variants)
    - All work types (3f-1m, breezing & handily)
    - Racing stamina drain by distance
    - Farm vs track location awareness
    - Consistency tracking (2-4 works+races in 30 days)
    """
    snap = find_latest_snapshot()
    ratings = load_json(OUTPUTS / "model" / "horse_ratings.json")

    # Load peak plans for race day info
    plans_files = sorted(OUTPUTS.glob("peak_plan_*.json"), reverse=True)
    peak_data = json.loads(plans_files[0].read_text(encoding="utf-8")) if plans_files else {}
    race_day_map = {}
    for p in peak_data.get("plans", []):
        hname = p.get("horse_name", "")
        for action in p.get("daily_plan", []):
            if action.get("action") in ("RACE", "RACE_TARGET"):
                race_day_map[hname] = action.get("day_offset", 7)
                break

    # Build playbook for each nominated horse
    playbook = []
    for h in snap.get("horses", []):
        if _norm(h.get("name", "")) in INACTIVE:
            continue
        noms = h.get("nominations", [])
        if not isinstance(noms, list) or not noms:
            continue
        field = noms[0].get("field", "")
        if not field or field == "No nominations.":
            continue

        name = h.get("name", "")
        age = h.get("age", "3")
        track = h.get("track", "")
        decay = decay_for_age(age)

        stam_raw = str(h.get("stamina", "100")).replace("%", "")
        cond_raw = str(h.get("condition", "100")).replace("%", "")
        try:
            stam = float(stam_raw)
        except ValueError:
            stam = 100.0
        try:
            cond = float(cond_raw)
        except ValueError:
            cond = 100.0

        days_to_race = race_day_map.get(name, 5)

        # Use engine to find optimal schedule
        schedule, proj_c, proj_s = find_optimal_schedule(
            cond, stam, decay, days_to_race, track
        )

        # Get per-day snapshots
        daily = simulate_daily(cond, stam, decay, days_to_race, schedule)

        # Today's action
        today_key = schedule.get(0, REST_KEY)
        if today_key in ALL_ACTIONS:
            today_label = ALL_ACTIONS[today_key]["label"]
        else:
            today_label = "Rest"

        # Verdict
        c_ok = 95 <= proj_c <= 105
        s_ok = 95 <= proj_s <= 105
        if c_ok and s_ok:
            verdict = "ON_TRACK"
        elif proj_c < 75 or proj_s < 75:
            verdict = "SCRATCH_RISK"
        else:
            verdict = "NEEDS_ATTENTION"

        # Consistency assessment
        works_30d = max(0, min(h.get("works_count", 0), 6))
        active_days = len(schedule)
        total_consist, consist_note = assess_consistency(works_30d, active_days)

        # Location info
        at_farm = is_farm(track)
        location_type = "Farm" if at_farm else "Track"

        rat = ratings.get(name, {})
        playbook.append({
            "name": name,
            "race_class": field,
            "age": age,
            "track": track,
            "location_type": location_type,
            "current_cond": cond,
            "current_stam": stam,
            "days_to_race": days_to_race,
            "today_action": today_key,
            "today_label": today_label,
            "schedule": {str(k): v for k, v in schedule.items()},
            "total_works": active_days,
            "proj_cond": proj_c,
            "proj_stam": proj_s,
            "verdict": verdict,
            "consist_note": consist_note,
            "consist_count": total_consist,
            "srf_power": rat.get("srf_power", 0),
            "daily": daily,
        })

    playbook.sort(key=lambda x: (
        0 if x["verdict"] == "ON_TRACK" else 1 if x["verdict"] == "NEEDS_ATTENTION" else 2,
        x["days_to_race"]
    ))
    return jsonify(playbook)


@app.route("/api/deep-analysis")
def api_deep_analysis():
    return jsonify(load_json(OUTPUTS / "deep_analysis.json"))


@app.route("/api/metrics")
def api_metrics():
    return jsonify(load_json(OUTPUTS / "model" / "model_metrics.json"))


@app.route("/api/outcomes")
def api_outcomes():
    rows = load_csv_rows(OUTPUTS / "outcomes_log.csv")
    return jsonify(rows[-50:])  # Last 50 races


# ── 2YO Development Center ──────────────────────────────

def classify_2yo_stage(works, consistency, has_raced):
    """Classify a 2YO's development stage."""
    con = 0
    try:
        con = int(consistency) if consistency not in ("?", "", None) else 0
    except (ValueError, TypeError):
        con = 0

    if has_raced:
        return "race_active", "🏁 Race Active"
    if works >= 100 and con >= 4:
        return "race_ready", "🎯 Race Ready"
    if works >= 50:
        return "speed_prep", "⚡ Speed Prep"
    if works >= 1:
        return "foundation", "🏋️ Foundation"
    return "pre_training", "🥚 Pre-Training"


def generate_2yo_plan(horse, stage, works, con_val, cond_val, stam_val, at_farm):
    """Generate AI development plan actions for a 2YO."""
    actions = []
    milestones = {
        "first_work": works >= 1,
        "fifty_works": works >= 50,
        "hundred_works": works >= 100,
        "consistency_4": con_val >= 4,
        "first_race": int(horse.get("record", {}).get("starts", "0")) > 0,
        "first_win": int(horse.get("record", {}).get("wins", "0")) > 0,
    }

    sex = horse.get("sex", "").lower()
    is_colt = "colt" in sex or "stallion" in sex

    if stage == "pre_training":
        actions.append({"priority": "high", "action": "Begin daily training to build base fitness",
                        "detail": f"Currently at {works} works — need to build foundation"})
        if at_farm:
            actions.append({"priority": "info", "action": "Keep at farm for early development",
                            "detail": "Farm training is cost-effective for initial conditioning"})

    elif stage == "foundation":
        remaining = 50 - works
        actions.append({"priority": "medium", "action": f"{remaining} more works to reach Speed Prep",
                        "detail": f"Building fundamentals — {works}/50 works completed"})
        if cond_val < 90:
            actions.append({"priority": "high", "action": "Condition is low — focus on light training",
                            "detail": f"Current condition: {cond_val}%. Target: 95%+"})
        if stam_val < 80:
            actions.append({"priority": "high", "action": "Rest needed — stamina is depleted",
                            "detail": f"Current stamina: {stam_val}%. Min for training: 80%"})

    elif stage == "speed_prep":
        remaining = 100 - works
        actions.append({"priority": "medium", "action": f"{remaining} more works to Race Ready",
                        "detail": f"Introducing speed work — {works}/100 works completed"})
        if at_farm:
            actions.append({"priority": "high", "action": "Consider shipping to track",
                            "detail": "Track training needed for gate works and timed breezes"})
        if con_val < 3:
            actions.append({"priority": "medium", "action": f"Build consistency: currently {con_val}/4+",
                            "detail": "Need consistency 4+ before maiden entry"})
        if con_val >= 4 and works >= 80:
            actions.append({"priority": "high", "action": "Near Race Ready — start scouting maiden races",
                            "detail": "Look for MSW with small field sizes (5-7 entries)"})

    elif stage == "race_ready":
        actions.append({"priority": "high", "action": "Ready for maiden entry!",
                        "detail": "Nominate for next available Maiden Special Weight"})
        if cond_val < 95:
            actions.append({"priority": "warning", "action": f"Get condition to 95%+ before racing",
                            "detail": f"Current: {cond_val}%. Need 2-3 more training days"})
        if at_farm:
            actions.append({"priority": "high", "action": "Ship to track immediately",
                            "detail": "Must be at track for race entry"})

    elif stage == "race_active":
        starts = int(horse.get("record", {}).get("starts", "0"))
        wins = int(horse.get("record", {}).get("wins", "0"))
        if starts > 0 and wins == 0 and starts >= 3:
            actions.append({"priority": "warning", "action": "No wins in 3+ starts — evaluate",
                            "detail": "Consider class drop or training adjustment"})
        if cond_val < 90:
            actions.append({"priority": "high", "action": "Rest before next entry",
                            "detail": f"Condition at {cond_val}% — below race threshold"})

    # Gelding check for colts
    if is_colt and con_val < 2 and works > 50:
        actions.append({"priority": "info", "action": "Consider gelding",
                        "detail": f"Low consistency ({con_val}) — gelding may improve focus"})

    return actions, milestones


@app.route("/api/twoyo")
@login_required
def api_twoyo():
    """2YO Development Center data."""
    snap = find_latest_snapshot()
    ratings = load_json(OUTPUTS / "model" / "horse_ratings.json")

    horses_2yo = []
    stage_counts = {"pre_training": 0, "foundation": 0, "speed_prep": 0,
                    "race_ready": 0, "race_active": 0}

    for h in snap.get("horses", []):
        if h.get("age") != "2":
            continue
        name = h.get("name", "")
        if _norm(name) in INACTIVE:
            continue

        works = h.get("works_count", 0)
        try:
            works = int(works)
        except (ValueError, TypeError):
            works = 0

        con_str = h.get("consistency", "0")
        try:
            con_val = int(con_str) if con_str not in ("?", "", None) else 0
        except (ValueError, TypeError):
            con_val = 0

        cond_str = h.get("condition", "100%").replace("%", "")
        try:
            cond_val = float(cond_str)
        except (ValueError, TypeError):
            cond_val = 100

        stam_str = h.get("stamina", "100%").replace("%", "")
        try:
            stam_val = float(stam_str)
        except (ValueError, TypeError):
            stam_val = 100

        has_raced = int(h.get("record", {}).get("starts", "0")) > 0
        track = h.get("track", "")
        at_farm = is_farm(track)

        stage_key, stage_label = classify_2yo_stage(works, con_str, has_raced)
        stage_counts[stage_key] = stage_counts.get(stage_key, 0) + 1

        actions, milestones = generate_2yo_plan(
            h, stage_key, works, con_val, cond_val, stam_val, at_farm)

        rat = ratings.get(name, {})
        horses_2yo.append({
            "name": name,
            "sex": h.get("sex", "?"),
            "color": h.get("color", "?"),
            "sire": h.get("sire", "?"),
            "dam": h.get("dam", "?"),
            "location": track,
            "location_type": "Farm" if at_farm else "Track",
            "condition": cond_val,
            "stamina": stam_val,
            "consistency": con_val,
            "works_count": works,
            "distance_meter": h.get("distance_meter", "?"),
            "height": h.get("height", "?"),
            "weight": h.get("weight", "?"),
            "record": h.get("record", {}),
            "stage_key": stage_key,
            "stage_label": stage_label,
            "progress_pct": min(100, round(works / 100 * 100)),
            "actions": actions,
            "milestones": milestones,
            "srf_power": rat.get("srf_power", 0),
        })

    # Sort: race_ready first, then by works desc
    stage_order = {"race_active": 0, "race_ready": 1, "speed_prep": 2,
                   "foundation": 3, "pre_training": 4}
    horses_2yo.sort(key=lambda x: (stage_order.get(x["stage_key"], 9), -x["works_count"]))

    # Financial summary
    total_horses = len(snap.get("horses", []))
    daily_cost = total_horses * 3  # $3/horse/day
    monthly_cost = daily_cost * 30
    balance_str = snap.get("balance", "$0")
    try:
        balance_val = float(balance_str.replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        balance_val = 0
    runway_months = balance_val / monthly_cost if monthly_cost > 0 else 999

    return jsonify({
        "horses": horses_2yo,
        "stage_counts": stage_counts,
        "total_2yo": len(horses_2yo),
        "financial": {
            "balance": balance_str,
            "balance_val": balance_val,
            "daily_cost": daily_cost,
            "monthly_cost": monthly_cost,
            "runway_months": round(runway_months, 1),
            "total_horses": total_horses,
        }
    })


@app.route("/api/calendar")
@login_required
def api_calendar():
    """Upcoming race calendar from nominations."""
    snap = find_latest_snapshot()
    ratings = load_json(OUTPUTS / "model" / "horse_ratings.json")
    upcoming = []

    for h in snap.get("horses", []):
        name = h.get("name", "")
        if _norm(name) in INACTIVE:
            continue
        noms = h.get("nominations", [])
        if not isinstance(noms, list):
            continue
        for nom in noms:
            field = nom.get("field", "")
            if not field or "No nominations" in field:
                continue
            # Parse race date if available
            race_date = nom.get("date", "")
            track = nom.get("track", h.get("track", "?"))
            cond_str = h.get("condition", "100%").replace("%", "")
            stam_str = h.get("stamina", "100%").replace("%", "")
            try:
                cond_val = float(cond_str)
            except (ValueError, TypeError):
                cond_val = 100
            try:
                stam_val = float(stam_str)
            except (ValueError, TypeError):
                stam_val = 100

            rat = ratings.get(name, {})
            # Determine readiness
            readiness = "ready"
            if cond_val < 90 or stam_val < 70:
                readiness = "danger"
            elif cond_val < 95:
                readiness = "caution"

            upcoming.append({
                "horse": name,
                "race_class": field[:60],
                "track": track,
                "date": race_date,
                "condition": cond_val,
                "stamina": stam_val,
                "srf_power": rat.get("srf_power", 0),
                "readiness": readiness,
            })

    upcoming.sort(key=lambda x: x.get("date", ""))
    return jsonify(upcoming)


refresh_status = {"running": False, "step": "", "error": ""}


@app.route("/api/refresh-status")
def api_refresh_status():
    return jsonify(refresh_status)


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Full refresh: detect cloud vs local, run appropriate pipeline."""
    if refresh_status["running"]:
        return jsonify({"status": "already_running"})

    # Detect if we're on cloud (no Playwright available)
    is_cloud = not (ROOT / "inputs" / "export" / "auth.json").exists()

    if is_cloud:
        # Cloud mode — can't run Playwright, tell frontend
        return jsonify({
            "status": "cloud_mode",
            "message": "Run sync from local machine: python scripts/sync.py"
        })

    def run_full_pipeline():
        refresh_status["running"] = True
        refresh_status["error"] = ""
        try:
            # Step 1: Login (auto-reuses saved session)
            refresh_status["step"] = "Logging into HRP..."
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "01_login_save_state.py")],
                cwd=str(ROOT), capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                refresh_status["error"] = f"Login failed: {result.stderr[:200]}"
                return

            # Step 2: Export fresh data
            refresh_status["step"] = "Exporting stable data from HRP..."
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "02_export_stable.py"), "--mode", "daily"],
                cwd=str(ROOT), capture_output=True, text=True, timeout=600
            )
            if result.returncode != 0:
                refresh_status["error"] = f"Export failed: {result.stderr[:200]}"
                return

            # Step 3: Build snapshot
            snap_script = ROOT / "scripts" / "03_build_snapshot.py"
            if snap_script.exists():
                refresh_status["step"] = "Building snapshot..."
                subprocess.run(
                    [sys.executable, str(snap_script)],
                    cwd=str(ROOT), capture_output=True, text=True, timeout=60
                )

            # Step 4: Analysis pipeline
            analysis_scripts = [
                ("Building model dataset...", "scripts/09_build_model_dataset.py"),
                ("Fitting Trainer Brain...", "scripts/10_fit_trainer_brain.py"),
                ("Running deep analysis...", "scripts/deep_analysis.py"),
                ("Auditing stable...", "scripts/stable_audit.py"),
                ("Generating daily decisions...", "scripts/daily_decisions.py"),
            ]
            for step_msg, script in analysis_scripts:
                script_path = ROOT / script
                if script_path.exists():
                    refresh_status["step"] = step_msg
                    subprocess.run(
                        [sys.executable, str(script_path)],
                        cwd=str(ROOT), capture_output=True, text=True, timeout=120
                    )

            refresh_status["step"] = "Done!"
        except Exception as e:
            refresh_status["error"] = str(e)[:200]
        finally:
            refresh_status["running"] = False

    threading.Thread(target=run_full_pipeline, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/action", methods=["POST"])
def api_action():
    action = request.json
    queue_path = OUTPUTS / "action_queue.json"
    queue = []
    if queue_path.exists():
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
    action["queued_at"] = date.today().isoformat()
    action["status"] = "pending"
    queue.append(action)
    queue_path.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    return jsonify({"status": "queued", "action": action})


@app.route("/api/actions")
def api_actions():
    queue_path = OUTPUTS / "action_queue.json"
    if queue_path.exists():
        return jsonify(json.loads(queue_path.read_text(encoding="utf-8")))
    return jsonify([])


@app.route("/api/peak-plans")
def api_peak_plans():
    """Return latest peak plan (14-day per-horse training plan)."""
    plans = sorted(OUTPUTS.glob("peak_plan_*.json"), reverse=True)
    if plans:
        return jsonify(json.loads(plans[0].read_text(encoding="utf-8")))
    return jsonify({"plans": [], "peaking_soon": [], "at_risk": []})


# ── Data Push (for cloud sync from local machine) ───────

@app.route("/api/push", methods=["POST"])
def api_push():
    """Accept data pushed from local machine.
    
    Usage: POST /api/push with header X-API-Key and JSON body with
    keys: stable_snapshot, horse_ratings, deep_analysis, decisions, metrics
    """
    key = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(key, API_KEY):
        return jsonify({"error": "unauthorized"}), 401

    data = request.json or {}

    # Write snapshot
    if "stable_snapshot" in data:
        snap_dir = ROOT / "inputs" / date.today().isoformat()
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "stable_snapshot.json").write_text(
            json.dumps(data["stable_snapshot"], indent=2), encoding="utf-8")

    # Write analysis outputs
    for key_name, out_path in [
        ("horse_ratings", OUTPUTS / "model" / "horse_ratings.json"),
        ("deep_analysis", OUTPUTS / "deep_analysis.json"),
        ("model_metrics", OUTPUTS / "model" / "model_metrics.json"),
    ]:
        if key_name in data:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(data[key_name], indent=2), encoding="utf-8")

    # Write peak plans (dated file)
    if "peak_plans" in data:
        pp_path = OUTPUTS / f"peak_plan_{date.today().isoformat()}.json"
        pp_path.write_text(json.dumps(data["peak_plans"], indent=2), encoding="utf-8")

    # Write decisions markdown
    if "decisions" in data:
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "Daily_Decisions.md").write_text(data["decisions"], encoding="utf-8")

    return jsonify({"status": "ok", "received_keys": list(data.keys())})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print("=" * 50)
    print("  HRP Command Center")
    print(f"  http://localhost:{port}")
    print("=" * 50)
    app.run(host="0.0.0.0", port=port, debug=True)
