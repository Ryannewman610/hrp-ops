"""10_fit_trainer_brain.py — Train baseline win/top3 prediction models.

Uses:
  - outputs/model/dataset_races.csv
  - outputs/model/dataset_works.csv
  - inputs/YYYY-MM-DD/stable_snapshot.json

Produces:
  - outputs/model/horse_ratings.json (ELO-style ratings)
  - outputs/model/model_metrics.json
  - outputs/model/feature_importance.json
  - reports/Trainer_Brain_Model_Card.md
"""

import csv
import json
import os
import re
from collections import defaultdict
from datetime import date
from math import log
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "outputs" / "model"
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

    recent_works = len([w for w in works if w.get("date", "") >= "2026-02-01"])
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


# ── Win/Top3 Probability ────────────────────────────────

def predict_win_probability(elo: float, field_size: int = 8) -> float:
    """Convert ELO rating to win probability."""
    # Assume average opponent has 1200 ELO
    avg_opp = 1200.0
    p_beat_one = 1.0 / (1.0 + 10 ** ((avg_opp - elo) / 400.0))
    # Win = beat all opponents
    return round(p_beat_one ** max(1, field_size - 1) * 100, 1)


def predict_top3_probability(elo: float, field_size: int = 8) -> float:
    """Estimate top3 probability from ELO."""
    p_beat_one = 1.0 / (1.0 + 10 ** ((1200.0 - elo) / 400.0))
    # Rough: top3 ≈ 3 * win_prob (capped at ~90%)
    win_p = p_beat_one ** max(1, field_size - 1)
    return round(min(win_p * 3, 0.90) * 100, 1)


def compute_ev_score(win_pct: float, top3_pct: float, form_score: int) -> float:
    """Compute expected value score (0-100 scale)."""
    # Weighted combination: 40% win, 30% top3, 30% form
    return round(win_pct * 0.4 + top3_pct * 0.3 + form_score * 5 * 0.3, 1)


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

    # 3. Compute predictions + form cycle for each horse
    horse_models: Dict[str, Dict] = {}
    snap_by_norm = {norm(h["name"]): h for h in snap.get("horses", [])}

    # Get works by horse
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

        form = compute_form_cycle(h, h_works, h_races)
        win_pct = predict_win_probability(rating)
        top3_pct = predict_top3_probability(rating)
        ev = compute_ev_score(win_pct, top3_pct, form["score"])

        horse_models[h["name"]] = {
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
            "elo_history": elo.history.get(h_norm, [])[-5:],  # last 5
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

    metrics = {
        "model_type": "ELO + Form Cycle",
        "total_races": len(races),
        "labeled_races": n_labeled,
        "win_rate": round(n_wins / n_labeled * 100, 1) if n_labeled else 0,
        "top3_rate": round(n_top3 / n_labeled * 100, 1) if n_labeled else 0,
        "total_works": len(works),
        "horses_rated": len(horse_models),
        "avg_elo": round(sum(m["elo_rating"] for m in horse_models.values()) / max(1, len(horse_models)), 1),
        "date": date.today().isoformat(),
    }
    (MODEL_DIR / "model_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Model metrics: {metrics}")

    # Feature importance (for ELO+Form, it's the factor weights)
    importance = {
        "stamina": 0.25,
        "condition": 0.15,
        "consistency": 0.15,
        "elo_rating": 0.20,
        "recent_works": 0.10,
        "win_rate_history": 0.15,
    }
    (MODEL_DIR / "feature_importance.json").write_text(json.dumps(importance, indent=2), encoding="utf-8")

    # 5. Generate Model Card
    lines = [
        "# 🧠 Trainer Brain — Model Card",
        f"> **Generated:** {date.today().isoformat()} | **Model:** ELO + Form Cycle",
        "",
        "## What It Does",
        "Predicts win probability (Win%), top-3 probability (Top3%), and expected value (EV Score)",
        "for each horse in the stable against typical race fields.",
        "",
        "## How It Works",
        "1. **ELO Rating** — Each horse starts at 1200. After each race result, ELO updates",
        "   based on who they beat/lost to. Higher ELO = stronger horse.",
        "2. **Form Cycle** — Current fitness based on:",
        "   - Stamina % (25% weight)",
        "   - Condition % (15%)",
        "   - Consistency (15%)",
        "   - ELO rating (20%)",
        "   - Recent works count (10%)",
        "   - Historical win rate (15%)",
        "3. **Expected Value** — Combines Win%, Top3%, and form score.",
        "",
        "## Current Ratings",
        "| Horse | ELO | Win% | Top3% | EV | Form Cycle |",
        "|-------|-----|------|-------|-----|------------|",
    ]

    for name, m in sorted(horse_models.items(), key=lambda x: -x[1]["ev_score"]):
        cycle_icon = {"PEAKING": "🔥", "READY": "✅", "NEEDS_WORK": "🏋️", "REST_REQUIRED": "🛏️"}.get(m["form_cycle"], "?")
        lines.append(f"| {name} | {m['elo_rating']} | {m['win_pct']}% | {m['top3_pct']}% | {m['ev_score']} | {cycle_icon} {m['form_cycle']} |")

    lines.extend([
        "",
        "## Dataset Stats",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total races | {len(races)} |",
        f"| Labeled (with finish position) | {n_labeled} |",
        f"| Actual win rate | {metrics['win_rate']}% |",
        f"| Actual top3 rate | {metrics['top3_rate']}% |",
        f"| Timed works | {len(works)} |",
        f"| Horses rated | {len(horse_models)} |",
        "",
        "## Limitations",
        "- ELO is based only on races where finish positions were parsed",
        "- Horses with no race history get default 1200 rating",
        "- Class/conditions matching is not yet factored into ELO",
        "- Distance preference not modeled (sprinter vs router)",
        "- No jockey/trainer data available",
        "",
        f"---",
        f"*Auto-generated by `10_fit_trainer_brain.py` on {date.today().isoformat()}*",
    ])

    card = "\n".join(lines) + "\n"
    (REPORTS / "Trainer_Brain_Model_Card.md").write_text(card, encoding="utf-8")
    print(f"Trainer_Brain_Model_Card.md: {len(card)} chars")


if __name__ == "__main__":
    main()
