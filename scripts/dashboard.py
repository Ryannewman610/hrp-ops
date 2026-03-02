"""dashboard.py — HRP Command Center local dashboard.

Run: python scripts/dashboard.py
Open: http://localhost:5050
"""

import csv
import json
import subprocess
import sys
import threading
from datetime import date
from pathlib import Path

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"

app = Flask(__name__,
            template_folder=str(ROOT / "scripts" / "templates"),
            static_folder=str(ROOT / "scripts" / "static"))


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
    for d in sorted(ROOT.glob("inputs/20*-*-*/stable_snapshot.json"), reverse=True):
        return load_json(d)
    return {}


# ── Routes ───────────────────────────────────────────────

@app.route("/")
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
    return jsonify({
        "horses": sorted(horses, key=lambda x: -x["srf_power"]),
        "balance": snap.get("balance", "?"),
        "horse_count": len(snap.get("horses", [])),
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


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    def run_pipeline():
        scripts = [
            "scripts/09_build_model_dataset.py",
            "scripts/10_fit_trainer_brain.py",
            "scripts/deep_analysis.py",
            "scripts/stable_audit.py",
            "scripts/daily_decisions.py",
        ]
        for s in scripts:
            subprocess.run(
                [sys.executable, str(ROOT / s)],
                cwd=str(ROOT), capture_output=True, text=True
            )

    threading.Thread(target=run_pipeline, daemon=True).start()
    return jsonify({"status": "refreshing"})


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


if __name__ == "__main__":
    print("=" * 50)
    print("  HRP Command Center")
    print("  http://localhost:5050")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5050, debug=True)
