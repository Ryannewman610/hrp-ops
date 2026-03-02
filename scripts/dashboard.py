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

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"

app = Flask(__name__,
            template_folder=str(ROOT / "scripts" / "templates"),
            static_folder=str(ROOT / "scripts" / "static"))

# ── Auth Config ──────────────────────────────────────────
# Set via environment variable or defaults for local dev
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "hrp2026")
API_KEY = os.environ.get("API_KEY", "local-dev-key")


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


refresh_status = {"running": False, "step": "", "error": ""}


@app.route("/api/refresh-status")
def api_refresh_status():
    return jsonify(refresh_status)


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Full refresh: execute queued actions → export from HRP → analyze."""
    if refresh_status["running"]:
        return jsonify({"status": "already_running"})

    def run_full_pipeline():
        refresh_status["running"] = True
        refresh_status["error"] = ""
        try:
            # Step 1: Execute pending actions on HRP
            queue_path = OUTPUTS / "action_queue.json"
            if queue_path.exists():
                queue = json.loads(queue_path.read_text(encoding="utf-8"))
                pending = [a for a in queue if a.get("status") == "pending"]
                if pending:
                    refresh_status["step"] = f"Executing {len(pending)} queued actions..."
                    # TODO: Wire Playwright automation for each action type
                    # For now, mark actions as "ready" (need manual HRP execution)
                    for a in queue:
                        if a.get("status") == "pending":
                            a["status"] = "ready_for_execution"
                    queue_path.write_text(json.dumps(queue, indent=2), encoding="utf-8")

            # Step 2: Login + Export fresh data from HRP
            refresh_status["step"] = "Logging into HRP..."
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "01_login_save_state.py")],
                cwd=str(ROOT), capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                refresh_status["error"] = f"Login failed: {result.stderr[:200]}"
                return

            refresh_status["step"] = "Exporting stable data from HRP..."
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "02_export_stable.py"), "--mode", "daily"],
                cwd=str(ROOT), capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                refresh_status["error"] = f"Export failed: {result.stderr[:200]}"
                return

            # Step 3: Run analysis pipeline
            analysis_scripts = [
                ("Building model dataset...", "scripts/09_build_model_dataset.py"),
                ("Fitting Trainer Brain...", "scripts/10_fit_trainer_brain.py"),
                ("Running deep analysis...", "scripts/deep_analysis.py"),
                ("Auditing stable...", "scripts/stable_audit.py"),
                ("Generating daily decisions...", "scripts/daily_decisions.py"),
            ]
            for step_msg, script in analysis_scripts:
                refresh_status["step"] = step_msg
                subprocess.run(
                    [sys.executable, str(ROOT / script)],
                    cwd=str(ROOT), capture_output=True, text=True, timeout=60
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
