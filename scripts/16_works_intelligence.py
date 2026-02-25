"""16_works_intelligence.py — Compute work-derived features per horse.

Input:  outputs/model/dataset_works.csv  +  stable_snapshot.json
Output: outputs/works_features_YYYY-MM-DD.json
        outputs/works_features.csv

Features per horse:
  - total_works, recent_works_14d, recent_works_28d
  - days_since_last_work, days_since_last_race
  - work_trend (improving/declining/steady)
  - sharpness_index (0-100), fatigue_proxy (0-100)
  - fitness_index (0-100), readiness_index (0-100)
"""

import csv
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "outputs" / "model"
OUTPUTS = ROOT / "outputs"
INACTIVE = {"shebasbriar", "averyspluck", "hiptag793004736512"}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_time_seconds(t: str) -> Optional[float]:
    """Convert work time '1:00.2' or '59.4' to seconds."""
    if not t:
        return None
    try:
        if ":" in t:
            parts = t.split(":")
            return float(parts[0]) * 60 + float(parts[1])
        return float(t)
    except (ValueError, IndexError):
        return None


def load_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def compute_features(horse_name: str, works: List[Dict], snap_h: Dict, today: date) -> Dict:
    """Compute work intelligence features for a single horse."""
    features: Dict[str, Any] = {
        "horse_name": horse_name,
        "total_works": len(works),
    }

    # Sort works by date (most recent first)
    dated_works = []
    for w in works:
        try:
            d = datetime.strptime(w.get("date", ""), "%Y-%m-%d").date()
            dated_works.append({**w, "_date": d})
        except ValueError:
            continue

    dated_works.sort(key=lambda x: x["_date"], reverse=True)

    # Recency
    if dated_works:
        last_work_date = dated_works[0]["_date"]
        features["days_since_last_work"] = (today - last_work_date).days
        features["last_work_date"] = last_work_date.isoformat()
        features["last_work_track"] = dated_works[0].get("track", "")
        features["last_work_distance"] = dated_works[0].get("distance", "")
    else:
        features["days_since_last_work"] = None
        features["last_work_date"] = None

    # Recent works counts
    d14 = today - timedelta(days=14)
    d28 = today - timedelta(days=28)
    features["recent_works_14d"] = sum(1 for w in dated_works if w["_date"] >= d14)
    features["recent_works_28d"] = sum(1 for w in dated_works if w["_date"] >= d28)

    # Work trend (compare last 3 work times at same distance)
    timed_works = [(w["_date"], parse_time_seconds(w.get("time", "")), w.get("distance", ""))
                   for w in dated_works if parse_time_seconds(w.get("time", ""))]

    features["work_trend"] = "unknown"
    if len(timed_works) >= 3:
        # Group by distance and use most common
        dist_groups: Dict[str, List] = {}
        for d, t, dist in timed_works:
            dist_groups.setdefault(dist, []).append((d, t))

        # Use the distance with most works
        best_dist = max(dist_groups.keys(), key=lambda k: len(dist_groups[k])) if dist_groups else ""
        if best_dist and len(dist_groups[best_dist]) >= 3:
            # Compare last 3 times (lower = faster = improving)
            recent = dist_groups[best_dist][:3]
            times = [t for _, t in recent]
            if times[0] < times[-1] - 0.5:
                features["work_trend"] = "improving"
            elif times[0] > times[-1] + 0.5:
                features["work_trend"] = "declining"
            else:
                features["work_trend"] = "steady"

    # Sharpness index (0-100): high when recently worked + fast times
    sharpness = 50.0
    days_since = features.get("days_since_last_work")
    if days_since is not None:
        if days_since <= 5:
            sharpness += 20
        elif days_since <= 10:
            sharpness += 10
        elif days_since <= 14:
            sharpness += 0
        elif days_since <= 21:
            sharpness -= 10
        else:
            sharpness -= 25

    if features["recent_works_14d"] >= 2:
        sharpness += 10
    elif features["recent_works_14d"] == 0:
        sharpness -= 15

    if features["work_trend"] == "improving":
        sharpness += 10
    elif features["work_trend"] == "declining":
        sharpness -= 10

    features["sharpness_index"] = round(max(0, min(100, sharpness)))

    # Fatigue proxy (0-100): high = more fatigued
    fatigue = 30.0  # baseline
    stam_raw = snap_h.get("stamina", "100%").replace("%", "")
    try:
        stam = float(stam_raw)
    except ValueError:
        stam = 100.0

    if stam < 70:
        fatigue += 30
    elif stam < 80:
        fatigue += 15
    elif stam < 90:
        fatigue += 5

    if features["recent_works_14d"] >= 3:
        fatigue += 15
    if days_since is not None and days_since <= 2:
        fatigue += 10

    features["fatigue_proxy"] = round(max(0, min(100, fatigue)))

    # Fitness index (0-100): combination of recent activity + condition
    fitness = 40.0
    cond_raw = snap_h.get("condition", "100%").replace("%", "")
    try:
        cond = float(cond_raw)
    except ValueError:
        cond = 100.0

    if cond >= 100:
        fitness += 20
    elif cond >= 95:
        fitness += 10
    elif cond < 85:
        fitness -= 10

    if features["recent_works_28d"] >= 2:
        fitness += 15
    if stam >= 90:
        fitness += 10
    elif stam < 70:
        fitness -= 20

    if features["work_trend"] == "improving":
        fitness += 5

    features["fitness_index"] = round(max(0, min(100, fitness)))

    # Readiness index (0-100): overall "ready to race" score
    readiness = (features["sharpness_index"] * 0.3 +
                 (100 - features["fatigue_proxy"]) * 0.3 +
                 features["fitness_index"] * 0.4)
    features["readiness_index"] = round(max(0, min(100, readiness)))

    # Readiness tag
    if readiness >= 75:
        features["readiness_tag"] = "RACE_READY"
    elif readiness >= 55:
        features["readiness_tag"] = "WORK_MORE"
    elif readiness >= 35:
        features["readiness_tag"] = "BUILDING"
    else:
        features["readiness_tag"] = "REST_NEEDED"

    return features


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    today = date.today()
    today_s = today.isoformat()

    # Load works dataset
    works_all = load_csv(MODEL_DIR / "dataset_works.csv")
    print(f"Loaded {len(works_all)} total works")

    # Group by horse
    works_by_horse: Dict[str, List[Dict]] = {}
    for w in works_all:
        name = w.get("horse_name", "")
        if norm(name) in INACTIVE:
            continue
        works_by_horse.setdefault(name, []).append(w)

    # Load snapshot
    snap_path = ROOT / "inputs" / today_s / "stable_snapshot.json"
    if not snap_path.exists():
        dirs = sorted((ROOT / "inputs").glob("20*-*-*"), reverse=True)
        for d in dirs:
            sp = d / "stable_snapshot.json"
            if sp.exists():
                snap_path = sp
                break
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    snap_by_norm = {norm(h["name"]): h for h in snap.get("horses", [])}

    # Compute features for each horse
    all_features = []
    for name, works in sorted(works_by_horse.items()):
        snap_h = snap_by_norm.get(norm(name), {})
        feat = compute_features(name, works, snap_h, today)
        all_features.append(feat)
        print(f"  {name:25s} works={feat['total_works']:3d} "
              f"recency={feat.get('days_since_last_work', '?'):>4} "
              f"sharp={feat['sharpness_index']:3d} "
              f"fit={feat['fitness_index']:3d} "
              f"ready={feat['readiness_index']:3d} "
              f"tag={feat['readiness_tag']}")

    # Also include horses with no works
    for h in snap.get("horses", []):
        if norm(h["name"]) in INACTIVE:
            continue
        if h["name"] not in works_by_horse:
            feat = compute_features(h["name"], [], snap_by_norm.get(norm(h["name"]), {}), today)
            all_features.append(feat)
            print(f"  {h['name']:25s} NO WORKS  ready={feat['readiness_index']:3d} tag={feat['readiness_tag']}")

    # Save JSON
    json_path = OUTPUTS / f"works_features_{today_s}.json"
    json_path.write_text(json.dumps(all_features, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nworks_features_{today_s}.json: {len(all_features)} horses")

    # Save CSV
    csv_path = OUTPUTS / "works_features.csv"
    fieldnames = [
        "horse_name", "total_works", "recent_works_14d", "recent_works_28d",
        "days_since_last_work", "last_work_date", "last_work_track", "last_work_distance",
        "work_trend", "sharpness_index", "fatigue_proxy", "fitness_index",
        "readiness_index", "readiness_tag",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_features)
    print(f"works_features.csv: {len(all_features)} rows")


if __name__ == "__main__":
    main()
