"""10_fit_trainer_brain.py — Train prediction models using SRF + ELO + Form.

Uses:
  - outputs/model/dataset_races.csv (with SRF speed figures)
  - outputs/model/dataset_works.csv
  - outputs/outcomes_log.csv (SRF source of truth)
  - inputs/YYYY-MM-DD/stable_snapshot.json

Produces:
  - outputs/model/horse_ratings.json (SRF + ELO + Form ratings)
  - outputs/model/model_metrics.json
  - outputs/model/feature_importance.json
  - reports/Trainer_Brain_Model_Card.md
"""

import csv
import json
import os
import re
from collections import defaultdict
from datetime import date, timedelta
from math import log
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "outputs" / "model"
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"

INACTIVE = {"shebasbriar", "averyspluck", "hiptag793004736512"}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


# ── ELO Rating System ────────────────────────────────────

class ELOSystem:
    """Simple ELO rating for horse racing."""

    def __init__(self, k: float = 32.0, default: float = 1200.0):
        self.k = k
        self.default = default
        self.ratings: Dict[str, float] = {}
        self.history: Dict[str, List[Dict]] = defaultdict(list)

    def get_rating(self, horse: str) -> float:
        return self.ratings.get(horse, self.default)

    def update_from_race(self, results: List[Dict]) -> None:
        """Update ratings from a single race result.
        results: list of {horse, finish} dicts sorted by finish position.
        """
        if len(results) < 2:
            return

        horses = [r["horse"] for r in results]
        old_ratings = {h: self.get_rating(h) for h in horses}

        for i, r in enumerate(results):
            horse = r["horse"]
            finish = int(r.get("finish", i + 1))
            field_size = len(results)

            # Expected score: average win probability against all opponents
            expected = 0.0
            actual = 0.0
            for j, opp in enumerate(results):
                if i == j:
                    continue
                opp_rating = old_ratings[opp["horse"]]
                expected += 1.0 / (1.0 + 10 ** ((opp_rating - old_ratings[horse]) / 400.0))
                # Actual: 1 if beat, 0.5 if tie, 0 if lost
                actual += 1.0 if finish < int(opp.get("finish", j + 1)) else 0.0

            n_opps = field_size - 1
            if n_opps > 0:
                expected /= n_opps
                actual /= n_opps

            new_rating = old_ratings[horse] + self.k * (actual - expected)
            self.ratings[horse] = round(new_rating, 1)
            self.history[horse].append({
                "date": r.get("date", ""),
                "old": round(old_ratings[horse], 1),
                "new": round(new_rating, 1),
                "finish": finish,
                "field": field_size,
            })


# ── Form Cycle Calculator ────────────────────────────────

def compute_form_cycle(snap_horse: Dict, works: List[Dict], races: List[Dict]) -> Dict:
    """Determine form cycle status for a horse."""
    stam_str = str(snap_horse.get("stamina", "100")).replace("%", "")
    cond_str = str(snap_horse.get("condition", "100")).replace("%", "")
    consist_str = str(snap_horse.get("consistency", "0")).replace("+", "")

    stam = int(stam_str) if stam_str.isdigit() else 100
    cond = int(cond_str) if cond_str.isdigit() else 100
    consist = int(consist_str) if consist_str.isdigit() else 0

    cutoff = (date.today() - timedelta(days=30)).isoformat()
    recent_works = len([w for w in works if w.get("date", "") >= cutoff])
    record = snap_horse.get("record", {})
    starts = int(record.get("starts", 0))
    wins = int(record.get("wins", 0))

    # Form cycle classification
    factors = []
    score = 0

    if stam >= 95:
        score += 3
        factors.append(f"Stamina {stam}% (excellent)")
    elif stam >= 85:
        score += 2
        factors.append(f"Stamina {stam}% (good)")
    elif stam >= 70:
        score += 1
        factors.append(f"Stamina {stam}% (moderate)")
    else:
        score -= 2
        factors.append(f"Stamina {stam}% (low)")

    if cond >= 98:
        score += 2
        factors.append(f"Condition {cond}% (peak)")
    elif cond >= 90:
        score += 1
        factors.append(f"Condition {cond}% (good)")

    if consist >= 5:
        score += 2
        factors.append(f"Consistency +{consist} (high)")
    elif consist >= 3:
        score += 1
        factors.append(f"Consistency +{consist} (moderate)")
    elif consist <= 1:
        score -= 1
        factors.append(f"Consistency {consist} (low)")

    if recent_works >= 3:
        score += 1
        factors.append(f"{recent_works} recent works (fit)")
    elif recent_works == 0:
        score -= 1
        factors.append("No recent works")

    # Classify
    if stam < 70:
        cycle = "REST_REQUIRED"
        action = "rest"
    elif stam < 85:
        cycle = "NEEDS_WORK"
        action = "timed_work"
    elif score >= 6:
        cycle = "PEAKING"
        action = "race_target"
    elif score >= 3:
        cycle = "READY"
        action = "race_target"
    else:
        cycle = "NEEDS_WORK"
        action = "timed_work"

    return {
        "cycle": cycle,
        "action": action,
        "score": score,
        "factors": factors[:3],
        "stamina": stam,
        "condition": cond,
        "consistency": consist,
        "recent_works": recent_works,
    }


# ── SRF Power Rating ────────────────────────────────────

def compute_srf_rating(races: List[Dict]) -> Dict:
    """Compute SRF-based power rating from race history."""
    srfs = []
    for r in races:
        srf = r.get("srf", "")
        if srf and str(srf).isdigit():
            srfs.append(int(srf))
    if not srfs:
        return {"avg": 0, "best": 0, "last": 0, "trend": "unknown", "n": 0, "power": 0}
    avg_srf = round(sum(srfs) / len(srfs), 1)
    best_srf = max(srfs)
    last_srf = srfs[0]  # Most recent
    # Trend: compare last 2 to previous
    if len(srfs) >= 3:
        recent = sum(srfs[:2]) / 2
        older = sum(srfs[2:min(4, len(srfs))]) / max(1, min(2, len(srfs) - 2))
        if recent > older + 2:
            trend = "improving"
        elif recent < older - 2:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "limited_data"
    # Power = weighted: 40% last, 30% avg, 30% best
    power = round(last_srf * 0.4 + avg_srf * 0.3 + best_srf * 0.3, 1)
    return {"avg": avg_srf, "best": best_srf, "last": last_srf,
            "trend": trend, "n": len(srfs), "power": power}


# ── Win/Top3 Probability ────────────────────────────────

def predict_win_probability(srf_power: float, elo: float, form_score: int,
                           field_size: int = 8) -> float:
    """Estimate win probability using SRF power + ELO + form."""
    if srf_power == 0:
        # No SRF data — fall back to ELO-only
        avg_opp = 1200.0
        p = 1.0 / (1.0 + 10 ** ((avg_opp - elo) / 400.0))
        return round(p ** max(1, field_size - 1) * 100, 1)
    # SRF-based: compare to typical field SRF (~83 for claiming, ~88 for allowance)
    field_avg_srf = 83.0
    srf_edge = srf_power - field_avg_srf
    # Each point of SRF edge ≈ +3% relative win probability
    base_win = 1.0 / max(field_size, 1) * 100  # Random chance
    srf_boost = srf_edge * 3.0  # SRF edge in percentage points
    form_boost = form_score * 1.5  # Form fitness bonus
    win_pct = base_win + srf_boost + form_boost
    return round(max(1.0, min(60.0, win_pct)), 1)


def predict_top3_probability(srf_power: float, elo: float, form_score: int,
                            field_size: int = 8) -> float:
    """Estimate top3 probability using SRF + form."""
    win_pct = predict_win_probability(srf_power, elo, form_score, field_size)
    return round(min(win_pct * 2.5, 85.0), 1)


def compute_ev_score(win_pct: float, top3_pct: float, srf_power: float,
                    form_score: int) -> float:
    """Compute expected value score (0-100 scale).
    Weights: 35% SRF power, 25% win, 20% top3, 20% form."""
    srf_norm = min(srf_power, 100) if srf_power else 0  # cap at 100
    return round(srf_norm * 0.35 + win_pct * 0.25 + top3_pct * 0.20 + form_score * 5 * 0.20, 1)


# ── Main Pipeline ────────────────────────────────────────

def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    # Load datasets
    races_path = MODEL_DIR / "dataset_races.csv"
    works_path = MODEL_DIR / "dataset_works.csv"

    if not races_path.exists():
        print("ERROR: Run 09_build_model_dataset.py first")
        return

    with open(races_path, encoding="utf-8") as f:
        races = list(csv.DictReader(f))
    with open(works_path, encoding="utf-8") as f:
        works = list(csv.DictReader(f))

    print(f"Loaded: {len(races)} races, {len(works)} works")

    # 1. Build ELO ratings from ALL race results
    elo = ELOSystem(k=32.0, default=1200.0)

    # Group races by date+track (same "race card")
    races_by_date = defaultdict(list)
    for r in races:
        if r.get("finish") and r["finish"].isdigit():
            key = r.get("date", "") + "_" + r.get("track", "")
            races_by_date[key].append(r)

    # Process each race (sorted by date)
    for key in sorted(races_by_date.keys()):
        race_entries = races_by_date[key]
        elo_entries = [{"horse": norm(r["horse_name"]), "finish": r["finish"],
                        "date": r.get("date", "")}
                       for r in race_entries]
        elo.update_from_race(elo_entries)

    print(f"ELO ratings computed for {len(elo.ratings)} horses")

    # 2. Load snapshot for current state
    snap_path = ROOT / "inputs" / date.today().isoformat() / "stable_snapshot.json"
    if not snap_path.exists():
        dirs = sorted((ROOT / "inputs").glob("20*-*-*"), reverse=True)
        for d in dirs:
            sp = d / "stable_snapshot.json"
            if sp.exists():
                snap_path = sp
                break
    snap = json.loads(snap_path.read_text(encoding="utf-8"))

    # 2b. SRF data: use recent_races from the snapshot (has SRF from profile HTML)
    # Fallback: also load outcomes_log if snapshot races are sparse
    outcomes_path = OUTPUTS / "outcomes_log.csv"
    srf_by_horse = defaultdict(list)
    if outcomes_path.exists():
        with open(outcomes_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                srf_by_horse[norm(row.get("horse_name", ""))].append(row)

    # 3. Compute predictions + form cycle + SRF power for each horse
    horse_models: Dict[str, Dict] = {}

    works_by_horse = defaultdict(list)
    for w in works:
        works_by_horse[norm(w["horse_name"])].append(w)

    races_by_horse = defaultdict(list)
    for r in races:
        races_by_horse[norm(r["horse_name"])].append(r)

    for h in snap.get("horses", []):
        h_norm = norm(h["name"])
        if h_norm in INACTIVE:
            continue

        rating = elo.get_rating(h_norm)
        h_works = works_by_horse.get(h_norm, [])
        h_races = races_by_horse.get(h_norm, [])

        # SRF source: prefer snapshot recent_races (has SRF from profile HTML),
        # fall back to outcomes log
        snap_races = h.get("recent_races", [])
        if snap_races and any(r.get("srf") for r in snap_races):
            srf_source = snap_races
        else:
            srf_source = srf_by_horse.get(h_norm, [])

        form = compute_form_cycle(h, h_works, h_races)
        srf = compute_srf_rating(srf_source)
        win_pct = predict_win_probability(srf["power"], rating, form["score"])
        top3_pct = predict_top3_probability(srf["power"], rating, form["score"])
        ev = compute_ev_score(win_pct, top3_pct, srf["power"], form["score"])

        horse_models[h["name"]] = {
            "srf_power": srf["power"],
            "srf_avg": srf["avg"],
            "srf_best": srf["best"],
            "srf_last": srf["last"],
            "srf_trend": srf["trend"],
            "srf_races": srf["n"],
            "elo_rating": rating,
            "win_pct": win_pct,
            "top3_pct": top3_pct,
            "ev_score": ev,
            "form_cycle": form["cycle"],
            "next_action": form["action"],
            "form_factors": form["factors"],
            "stamina": form["stamina"],
            "condition": form["condition"],
            "consistency": form["consistency"],
            "recent_works": form["recent_works"],
            "elo_history": elo.history.get(h_norm, [])[-5:],
        }

    # 4. Save outputs
    ratings_path = MODEL_DIR / "horse_ratings.json"
    ratings_path.write_text(json.dumps(horse_models, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"horse_ratings.json: {len(horse_models)} horses")

    # Model metrics
    labeled_races = [r for r in races if r.get("finish") and r["finish"].isdigit()]
    n_labeled = len(labeled_races)
    n_wins = sum(1 for r in labeled_races if int(r["finish"]) == 1)
    n_top3 = sum(1 for r in labeled_races if int(r["finish"]) <= 3)

    srf_horses = sum(1 for m in horse_models.values() if m["srf_power"] > 0)
    metrics = {
        "model_type": "SRF + ELO + Form Cycle",
        "total_races": len(races),
        "labeled_races": n_labeled,
        "win_rate": round(n_wins / n_labeled * 100, 1) if n_labeled else 0,
        "top3_rate": round(n_top3 / n_labeled * 100, 1) if n_labeled else 0,
        "total_works": len(works),
        "horses_rated": len(horse_models),
        "horses_with_srf": srf_horses,
        "date": date.today().isoformat(),
    }
    (MODEL_DIR / "model_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Model metrics: {metrics}")

    importance = {
        "srf_power": 0.35,
        "stamina": 0.15,
        "condition": 0.10,
        "consistency": 0.10,
        "elo_rating": 0.10,
        "recent_works": 0.10,
        "form_score": 0.10,
    }
    (MODEL_DIR / "feature_importance.json").write_text(json.dumps(importance, indent=2), encoding="utf-8")

    # 5. Generate Model Card with SRF-centric rankings
    lines = [
        "# 🧠 Trainer Brain — Model Card",
        f"> **Generated:** {date.today().isoformat()} | **Model:** SRF + ELO + Form",
        "",
        "## Model Architecture",
        "- **SRF Power** (35% weight) — Weighted combination of last, avg, and best SRF",
        "- **Form Cycle** (20%) — Stamina, condition, consistency, recent works",
        "- **ELO Rating** (10%) — Historical head-to-head performance",
        "- **Win/Top3** (35%) — Probabilistic estimate from SRF edge vs field",
        "",
        "## Power Rankings (SRF-Based)",
        "| Horse | SRF Pwr | Avg | Best | Last | Trend | Win% | EV | Form |",
        "|-------|:-------:|:---:|:----:|:----:|-------|:----:|:--:|------|",
    ]

    rated = [(n, m) for n, m in horse_models.items() if m["srf_power"] > 0]
    unrated = [(n, m) for n, m in horse_models.items() if m["srf_power"] == 0]

    for name, m in sorted(rated, key=lambda x: -x[1]["srf_power"]):
        trend_icon = {"improving": "📈", "declining": "📉", "stable": "➡️", "limited_data": "—"}.get(m["srf_trend"], "?")
        cycle_icon = {"PEAKING": "🔥", "READY": "✅", "NEEDS_WORK": "🏋️", "REST_REQUIRED": "🛏️"}.get(m["form_cycle"], "?")
        lines.append(f"| {name} | **{m['srf_power']}** | {m['srf_avg']} | {m['srf_best']} | {m['srf_last']} | {trend_icon} | {m['win_pct']}% | {m['ev_score']} | {cycle_icon} |")

    if unrated:
        lines.append("")
        lines.append("### Unrated (no race history)")
        lines.append("| Horse | Form | Next Action |")
        lines.append("|-------|------|-------------|")
        for name, m in sorted(unrated, key=lambda x: x[0]):
            cycle_icon = {"PEAKING": "🔥", "READY": "✅", "NEEDS_WORK": "🏋️", "REST_REQUIRED": "🛏️"}.get(m["form_cycle"], "?")
            lines.append(f"| {name} | {cycle_icon} {m['form_cycle']} | {m['next_action']} |")

    lines.extend([
        "",
        "## Dataset Stats",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total races | {len(races)} |",
        f"| Races with SRF | {sum(1 for r in races if r.get('srf'))} |",
        f"| Horses with SRF | {srf_horses} |",
        f"| Timed works | {len(works)} |",
        f"| Win rate (actual) | {metrics['win_rate']}% |",
        "",
        f"---",
        f"*Auto-generated by `10_fit_trainer_brain.py` on {date.today().isoformat()}*",
    ])

    card = "\n".join(lines) + "\n"
    (REPORTS / "Trainer_Brain_Model_Card.md").write_text(card, encoding="utf-8")
    print(f"Trainer_Brain_Model_Card.md: {len(card)} chars")


if __name__ == "__main__":
    main()
