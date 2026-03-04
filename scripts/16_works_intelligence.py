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

    # ── Overracing Wall Detection (Stu's Experiment) ──
    # Horses hit a wall after 4+ races in ~60 days without intervening works.
    # Growth stops and performance collapses despite identical meters.
    races = snap_h.get("recent_races", [])
    race_dates = []
    for r in races:
        try:
            rd = r.get("date", "")
            if "/" in rd:
                parts = rd.split("/")
                rd = f"{parts[2]}-{int(parts[0]):02d}-{int(parts[1]):02d}"
            race_dates.append(datetime.strptime(rd, "%Y-%m-%d").date())
        except (ValueError, IndexError):
            continue
    d60 = today - timedelta(days=60)
    races_60d = [rd for rd in race_dates if rd >= d60]
    works_between_races = features["recent_works_28d"]  # proxy
    features["races_60d"] = len(races_60d)
    if len(races_60d) >= 4 and works_between_races < 2:
        features["overracing_risk"] = "HIGH"
        features["overracing_note"] = (
            f"{len(races_60d)} races in 60d with few works — wall risk (Stu's data: "
            f"performance collapses after 4 races without works)")
    elif len(races_60d) >= 3:
        features["overracing_risk"] = "WATCH"
        features["overracing_note"] = f"{len(races_60d)} races in 60d — schedule works between"
    else:
        features["overracing_risk"] = "OK"
        features["overracing_note"] = ""

    # ── Work Quality Tier — First-Ever Timed Work, Normalized to 5f-Fast ──
    # The tier is based STRICTLY on the horse's chronologically first timed work.
    # Normalized for distance and surface so every horse is compared equally.

    # ADDITIVE distance offset to 5f-equivalent:
    # The tier benchmarks define exact equivalences across distances:
    #   3f:35 = 4f:47 = 5f:60 = 6f:70 = 7f:82 (all ULTRA_RARE)
    #   3f:39 = 4f:51 = 5f:64 = 6f:74 = 7f:87 (all QUESTIONABLE)
    # So: 5f_equiv = raw_time + offset
    DIST_5F_OFFSET = {
        "3f": 25,    # 35 + 25 = 60 (ULTRA_RARE match)
        "4f": 13,    # 47 + 13 = 60
        "5f": 0,     # baseline
        "6f": -10,   # 70 - 10 = 60
        "7f": -22,   # 82 - 22 = 60
    }
    KNOWN_DISTS = set(DIST_5F_OFFSET.keys())

    # Surface penalty — TOTAL seconds added by off-track conditions.
    # Empirically measured from horses that worked same dist on fast AND sloppy/muddy:
    #   4f sloppy: avg +6.0s total (1.5s/f) — Iron Timekeeper, Crowds Ransom, etc
    #   5f sloppy: avg +3.5s total (0.7s/f) — Core N Light, Harsh Frontier, etc
    #   3f muddy:  avg +1.2s total (0.4s/f) — Class A, Strike King, etc
    # Using per-distance total penalties for accuracy:
    SURFACE_PENALTY = {
        # (surface, dist) → total seconds penalty
        "fst": {"3f": 0, "4f": 0, "5f": 0, "6f": 0, "7f": 0},
        "gd":  {"3f": 0.5, "4f": 1, "5f": 1.5, "6f": 2, "7f": 2.5},
        "fm":  {"3f": 0.5, "4f": 1, "5f": 1.5, "6f": 2, "7f": 2.5},
        "sly": {"3f": 1.5, "4f": 6, "5f": 3.5, "6f": 4, "7f": 5},
        "mdy": {"3f": 1.2, "4f": 3, "5f": 3, "6f": 3.5, "7f": 4},
        "sy":  {"3f": 2, "4f": 7, "5f": 4, "6f": 5, "7f": 6},
        "yl":  {"3f": 1, "4f": 2, "5f": 2.5, "6f": 3, "7f": 3.5},
        "wf":  {"3f": 0.5, "4f": 1, "5f": 1.5, "6f": 2, "7f": 2.5},
        "sf":  {"3f": 0.5, "4f": 1, "5f": 1.5, "6f": 2, "7f": 2.5},
    }

    # 5f tier thresholds (the universal comparison scale)
    TIER_5F = {"ULTRA_RARE": 60.0, "STAKES": 61.0, "PAY_SIDE": 62.0,
               "FREE_LEVEL": 63.0, "QUESTIONABLE": 64.0}

    def classify_5f_equiv(eq_time):
        """Classify a 5f-equivalent time."""
        if eq_time <= TIER_5F["ULTRA_RARE"]:
            return "ULTRA_RARE"
        elif eq_time <= TIER_5F["STAKES"]:
            return "STAKES"
        elif eq_time <= TIER_5F["PAY_SIDE"]:
            return "PAY_SIDE"
        elif eq_time <= TIER_5F["FREE_LEVEL"]:
            return "FREE_LEVEL"
        elif eq_time <= TIER_5F["QUESTIONABLE"]:
            return "QUESTIONABLE"
        else:
            return "NOT_USEFUL"

    def normalize_to_5f_fast(time_secs, dist, surface):
        """Convert any work time to a 5f-fast equivalent using additive offset."""
        offset = DIST_5F_OFFSET.get(dist, 0)
        srf = surface.lower().strip() if surface else "fst"
        penalty_table = SURFACE_PENALTY.get(srf, SURFACE_PENALTY["fst"])
        srf_penalty = penalty_table.get(dist, 0)
        # Step 1: Remove surface penalty to get "fast track" time
        fast_time = time_secs - srf_penalty
        # Step 2: Add offset to convert to 5f-equivalent
        equiv = fast_time + offset
        return round(equiv, 1)

    # dated_works is sorted most-recent-first, so reverse for chronological
    chrono_works = list(reversed(dated_works))

    # Find the FIRST-EVER timed work at any distance
    virgin_time = None
    virgin_dist = None
    virgin_date = None
    virgin_surface = ""
    for w in chrono_works:
        d = w.get("distance", "").strip().lower()
        if d not in KNOWN_DISTS:
            continue
        t = parse_time_seconds(w.get("time", ""))
        if t and t > 30.0:
            virgin_time = t
            virgin_dist = d
            virgin_date = w.get("date", "?")
            virgin_surface = w.get("surface", "fst")
            break

    # Also find first timed work at EACH distance + best at each
    first_at_dist = {}
    best_at_dist = {}
    for w in chrono_works:
        d = w.get("distance", "").strip().lower()
        if d not in KNOWN_DISTS:
            continue
        t = parse_time_seconds(w.get("time", ""))
        if t and t > 30.0:
            if d not in first_at_dist:
                first_at_dist[d] = {"time": t, "date": w.get("date", "?"),
                                    "surface": w.get("surface", "fst")}
            if d not in best_at_dist or t < best_at_dist[d]:
                best_at_dist[d] = t

    if virgin_time and virgin_dist:
        # Normalize first-ever work to 5f-fast equivalent
        equiv_5f = normalize_to_5f_fast(virgin_time, virgin_dist, virgin_surface)

        features["virgin_work_seconds"] = round(virgin_time, 2)
        features["virgin_work_distance"] = virgin_dist
        features["virgin_work_date"] = virgin_date
        features["virgin_work_surface"] = virgin_surface
        features["virgin_5f_equiv"] = equiv_5f
        features["work_quality_tier"] = classify_5f_equiv(equiv_5f)

        # Build per-distance breakdown (each distance's virgin also normalized)
        dist_summary = {}
        for d in sorted(first_at_dist.keys()):
            f = first_at_dist[d]
            b = best_at_dist.get(d)
            d_equiv = normalize_to_5f_fast(f["time"], d, f.get("surface", "fst"))
            dist_summary[d] = {
                "virgin": round(f["time"], 2),
                "virgin_date": f["date"],
                "virgin_surface": f.get("surface", "fst"),
                "virgin_5f_equiv": d_equiv,
                "virgin_tier": classify_5f_equiv(d_equiv),
                "best": round(b, 2) if b else None,
                "gain": round(f["time"] - b, 1) if b and b < f["time"] else 0.0,
            }
        features["distance_breakdown"] = dist_summary

        # Training gain: best time at virgin distance vs virgin time
        best_at_vd = best_at_dist.get(virgin_dist)
        features["best_work_seconds"] = round(best_at_vd, 2) if best_at_vd else None
        if best_at_vd and best_at_vd < virgin_time:
            features["training_gain"] = round(virgin_time - best_at_vd, 1)
        else:
            features["training_gain"] = 0.0
    else:
        features["virgin_work_seconds"] = None
        features["virgin_work_distance"] = None
        features["virgin_work_date"] = None
        features["virgin_work_surface"] = None
        features["virgin_5f_equiv"] = None
        features["work_quality_tier"] = "NO_DATA"
        features["distance_breakdown"] = {}
        features["best_work_seconds"] = None
        features["training_gain"] = None

    # Keep backward-compatible 5f field
    five_f_times = []
    for w in dated_works:
        dist = w.get("distance", "").strip().lower()
        if dist == "5f":
            t = parse_time_seconds(w.get("time", ""))
            if t and t > 30.0:
                five_f_times.append(t)
    features["best_5f_seconds"] = round(min(five_f_times), 2) if five_f_times else None

    # Readiness index (0-100): overall "ready to race" score
    readiness = (features["sharpness_index"] * 0.3 +
                 (100 - features["fatigue_proxy"]) * 0.3 +
                 features["fitness_index"] * 0.4)
    # Penalize readiness if overracing
    if features["overracing_risk"] == "HIGH":
        readiness -= 20
    features["readiness_index"] = round(max(0, min(100, readiness)))

    # Readiness tag
    if features["overracing_risk"] == "HIGH":
        features["readiness_tag"] = "OVERRACED"
    elif readiness >= 75:
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
        tier_tag = f" [{feat.get('work_quality_tier', '')}]" if feat.get("best_5f_seconds") else ""
        overrace = f" ⚠️{feat['overracing_risk']}" if feat.get("overracing_risk") != "OK" else ""
        print(f"  {name:25s} works={feat['total_works']:3d} "
              f"recency={feat.get('days_since_last_work', '?'):>4} "
              f"sharp={feat['sharpness_index']:3d} "
              f"fit={feat['fitness_index']:3d} "
              f"ready={feat['readiness_index']:3d} "
              f"tag={feat['readiness_tag']}{tier_tag}{overrace}")

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
        "overracing_risk", "overracing_note", "races_60d",
        "best_5f_seconds", "work_quality_tier",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_features)
    print(f"works_features.csv: {len(all_features)} rows")


if __name__ == "__main__":
    main()
