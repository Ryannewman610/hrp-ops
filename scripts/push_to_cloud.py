"""push_to_cloud.py — Sync local data to the cloud dashboard.

Run after the daily pipeline to push fresh data to your Railway-hosted
dashboard so it's accessible from anywhere.

Usage:
    python scripts/push_to_cloud.py

Environment variables:
    CLOUD_URL  — Dashboard URL (e.g. https://hrp.cynfulnature.com)
    API_KEY    — Must match the API_KEY set on the cloud server
"""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"

CLOUD_URL = os.environ.get("CLOUD_URL", "").rstrip("/")
API_KEY = os.environ.get("API_KEY", "local-dev-key")


def find_latest_snapshot():
    for d in sorted(ROOT.glob("inputs/20*-*-*/stable_snapshot.json"), reverse=True):
        return json.loads(d.read_text(encoding="utf-8"))
    return {}


def load_json(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def main():
    if not CLOUD_URL:
        print("ERROR: Set CLOUD_URL environment variable")
        print("  e.g. set CLOUD_URL=https://hrp.cynfulnature.com")
        sys.exit(1)

    print(f"Pushing data to {CLOUD_URL}...")

    payload = {}

    # Stable snapshot
    snap = find_latest_snapshot()
    if snap:
        payload["stable_snapshot"] = snap
        print(f"  → stable_snapshot: {len(snap.get('horses', []))} horses")

    # Horse ratings
    ratings = load_json(OUTPUTS / "model" / "horse_ratings.json")
    if ratings:
        payload["horse_ratings"] = ratings
        print(f"  → horse_ratings: {len(ratings)} horses")

    # Deep analysis
    analysis = load_json(OUTPUTS / "deep_analysis.json")
    if analysis:
        payload["deep_analysis"] = analysis
        print(f"  → deep_analysis: {len(analysis)} keys")

    # Model metrics
    metrics = load_json(OUTPUTS / "model" / "model_metrics.json")
    if metrics:
        payload["model_metrics"] = metrics
        print(f"  → model_metrics: ✓")

    # Daily decisions
    decisions_path = REPORTS / "Daily_Decisions.md"
    if decisions_path.exists():
        payload["decisions"] = decisions_path.read_text(encoding="utf-8")
        print(f"  → decisions: ✓")

    # Peak plans (latest)
    peak_plans = sorted(OUTPUTS.glob("peak_plan_*.json"), reverse=True)
    if peak_plans:
        payload["peak_plans"] = load_json(peak_plans[0])
        print(f"  → peak_plans: ✓")

    # Push
    data = json.dumps(payload).encode("utf-8")
    print(f"\n  Total payload: {len(data) / 1024:.0f} KB")

    req = urllib.request.Request(
        f"{CLOUD_URL}/api/push",
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"\n✅ Push successful! Keys received: {result.get('received_keys', [])}")
    except urllib.error.HTTPError as e:
        print(f"\n❌ Push failed: HTTP {e.code}")
        print(f"   {e.read().decode()[:200]}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Push failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
