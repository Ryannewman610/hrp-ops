"""seed_cloud_data.py — Bundle current data into a git-committed seed for Railway deploys.

When Railway rebuilds from git, all runtime-written data files are lost.
This script:
1. Reads all current data files (snapshot, ratings, works, etc.)
2. Bundles them into a single compressed JSON file at scripts/cloud_seed.json.gz
3. This file is committed to git and included in every deploy

The dashboard.py startup code calls restore_seed_data() which:
1. Checks if data directories/files exist
2. If empty, restores from the seed bundle
3. This ensures the site always has data even right after a fresh deploy
"""
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"
SEED_PATH = ROOT / "scripts" / "cloud_seed.json.gz"


def bundle():
    """Create a compressed seed data bundle from current data files."""
    bundle_data = {}

    # Stable snapshot (find latest)
    for snap_path in sorted(ROOT.glob("inputs/20*-*-*/stable_snapshot.json"), reverse=True):
        bundle_data["stable_snapshot"] = json.loads(snap_path.read_text(encoding="utf-8"))
        bundle_data["snapshot_date"] = snap_path.parent.name
        print(f"  → stable_snapshot: {len(bundle_data['stable_snapshot'].get('horses', []))} horses from {snap_path.parent.name}")
        break

    # All JSON model outputs
    json_files = {
        "horse_ratings": OUTPUTS / "model" / "horse_ratings.json",
        "deep_analysis": OUTPUTS / "deep_analysis.json",
        "model_metrics": OUTPUTS / "model" / "model_metrics.json",
        "works_splits": OUTPUTS / "works_splits.json",
    }
    for key, path in json_files.items():
        if path.exists():
            bundle_data[key] = json.loads(path.read_text(encoding="utf-8"))
            print(f"  → {key}: ✓")

    # Peak plans (latest)
    peak_plans = sorted(OUTPUTS.glob("peak_plan_*.json"), reverse=True)
    if peak_plans:
        bundle_data["peak_plans"] = json.loads(peak_plans[0].read_text(encoding="utf-8"))
        bundle_data["peak_plans_date"] = peak_plans[0].stem.replace("peak_plan_", "")
        print(f"  → peak_plans: ✓")

    # CSV files as text
    csv_files = {
        "works_features": OUTPUTS / "works_features.csv",
        "outcomes_log": OUTPUTS / "outcomes_log.csv",
    }
    for key, path in csv_files.items():
        if path.exists():
            bundle_data[key] = path.read_text(encoding="utf-8")
            print(f"  → {key}: ✓")

    # Markdown reports
    md_files = {
        "decisions": REPORTS / "Daily_Decisions.md",
        "training_plan": REPORTS / "Training_Plan.md",
    }
    for key, path in md_files.items():
        if path.exists():
            bundle_data[key] = path.read_text(encoding="utf-8")
            print(f"  → {key}: ✓")

    # Write compressed bundle
    raw = json.dumps(bundle_data).encode("utf-8")
    with gzip.open(SEED_PATH, "wb") as f:
        f.write(raw)

    size_kb = SEED_PATH.stat().st_size / 1024
    print(f"\nSeed bundle: {SEED_PATH}")
    print(f"  Size: {size_kb:.0f} KB compressed (from {len(raw)/1024:.0f} KB raw)")
    print(f"  Keys: {list(bundle_data.keys())}")


def restore():
    """Restore data from seed bundle if data directories are empty."""
    if not SEED_PATH.exists():
        print("No seed bundle found — skipping restore")
        return False

    # Check if we already have data
    snap_exists = any(ROOT.glob("inputs/20*-*-*/stable_snapshot.json"))
    ratings_exist = (OUTPUTS / "model" / "horse_ratings.json").exists()

    if snap_exists and ratings_exist:
        return False  # Data already present, no need to restore

    print("Restoring from seed bundle...")
    with gzip.open(SEED_PATH, "rb") as f:
        bundle_data = json.loads(f.read().decode("utf-8"))

    # Restore stable snapshot
    if "stable_snapshot" in bundle_data:
        snap_date = bundle_data.get("snapshot_date", "2026-01-01")
        snap_dir = ROOT / "inputs" / snap_date
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "stable_snapshot.json").write_text(
            json.dumps(bundle_data["stable_snapshot"], indent=2), encoding="utf-8")
        print(f"  → snapshot: {snap_date}")

    # Restore JSON outputs
    json_files = {
        "horse_ratings": OUTPUTS / "model" / "horse_ratings.json",
        "deep_analysis": OUTPUTS / "deep_analysis.json",
        "model_metrics": OUTPUTS / "model" / "model_metrics.json",
        "works_splits": OUTPUTS / "works_splits.json",
    }
    for key, path in json_files.items():
        if key in bundle_data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(bundle_data[key], indent=2), encoding="utf-8")
            print(f"  → {key}: restored")

    # Restore peak plans
    if "peak_plans" in bundle_data:
        pp_date = bundle_data.get("peak_plans_date", "2026-01-01")
        pp_path = OUTPUTS / f"peak_plan_{pp_date}.json"
        pp_path.parent.mkdir(parents=True, exist_ok=True)
        pp_path.write_text(json.dumps(bundle_data["peak_plans"], indent=2), encoding="utf-8")
        print(f"  → peak_plans: restored")

    # Restore CSVs
    csv_files = {
        "works_features": OUTPUTS / "works_features.csv",
        "outcomes_log": OUTPUTS / "outcomes_log.csv",
    }
    for key, path in csv_files.items():
        if key in bundle_data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(bundle_data[key], encoding="utf-8")
            print(f"  → {key}: restored")

    # Restore markdown reports
    md_files = {
        "decisions": REPORTS / "Daily_Decisions.md",
        "training_plan": REPORTS / "Training_Plan.md",
    }
    for key, path in md_files.items():
        if key in bundle_data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(bundle_data[key], encoding="utf-8")
            print(f"  → {key}: restored")

    print("Seed data restore complete!")
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        restore()
    else:
        print("Bundling seed data...")
        bundle()
