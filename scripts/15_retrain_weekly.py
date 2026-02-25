"""15_retrain_weekly.py — Weekly ELO update + calibration.

Updates ELO ratings from outcomes and fits a simple calibration layer.
Saves updated model and model_card.md.

SAFETY: Read-only analytics. No in-game actions.
"""

import csv
import json
import math
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
MODEL_DIR = OUTPUTS / "model"


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def elo_update(rating: float, expected: float, actual: float, k: float = 16) -> float:
    """Update ELO rating given expected vs actual result."""
    return rating + k * (actual - expected)


def expected_score(rating_a: float, rating_b: float) -> float:
    """Expected win probability for A against B."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400))


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    # Load current ratings
    ratings_path = MODEL_DIR / "horse_ratings.json"
    if not ratings_path.exists():
        print("No horse_ratings.json. Run 10_fit_trainer_brain.py first.")
        return
    ratings = json.loads(ratings_path.read_text(encoding="utf-8"))

    # Load outcomes
    outcomes = load_csv(OUTPUTS / "outcomes_log.csv")
    print(f"Loaded {len(outcomes)} outcomes")

    if not outcomes:
        print("No outcomes yet. Run 13_ingest_outcomes.py first.")
        return

    # Update ELO from outcomes
    updates = 0
    for o in outcomes:
        horse = o.get("horse_name", "")
        h_norm = norm(horse)
        finish = o.get("finish_position", "")

        if not finish or not finish.isdigit():
            continue

        finish_int = int(finish)

        # Find this horse in ratings
        for name, model in ratings.items():
            if norm(name) == h_norm:
                old_elo = model["elo_rating"]
                base_rating = 1200  # Average field

                # Win = 1.0, top3 = 0.7, mid = 0.3, poor = 0.0
                if finish_int == 1:
                    actual = 1.0
                elif finish_int <= 3:
                    actual = 0.7
                elif finish_int <= 6:
                    actual = 0.3
                else:
                    actual = 0.0

                exp = expected_score(old_elo, base_rating)
                new_elo = elo_update(old_elo, exp, actual)
                model["elo_rating"] = round(new_elo, 1)
                updates += 1
                break

    print(f"ELO updates: {updates}")

    # Recalculate win%/top3%/ev from updated ELO
    elos = [m["elo_rating"] for m in ratings.values()]
    avg_elo = sum(elos) / len(elos) if elos else 1200

    for name, model in ratings.items():
        rel = model["elo_rating"] - avg_elo
        model["win_pct"] = round(max(0.1, min(30, 1.0 / (1 + 10 ** (-rel / 400)) * 10)), 1)
        model["top3_pct"] = round(model["win_pct"] * 3, 1)
        model["ev_score"] = round(model["win_pct"] + model["stamina"] / 20 + model["condition"] / 30 + model["consistency"], 1)

    # Simple calibration: compare predicted vs actual win rates
    predictions = load_csv(OUTPUTS / "predictions_log.csv")
    outcome_map = {}
    for o in outcomes:
        key = f"{norm(o.get('horse_name', ''))}_{o.get('date', '')}_{norm(o.get('track', ''))}"
        outcome_map[key] = o

    # Calibration buckets
    buckets = defaultdict(lambda: {"predicted": 0, "actual_wins": 0, "count": 0})
    for p in predictions:
        key = f"{norm(p.get('horse_name', ''))}_{p.get('date', '')}_{norm(p.get('track', ''))}"
        o = outcome_map.get(key)
        if not o:
            continue
        pred_win = float(p.get("predicted_win_prob", 0))
        bucket = int(pred_win // 2) * 2  # 0-2%, 2-4%, etc.
        finish = o.get("finish_position", "")
        is_win = finish == "1"
        buckets[bucket]["predicted"] += pred_win / 100
        buckets[bucket]["actual_wins"] += 1 if is_win else 0
        buckets[bucket]["count"] += 1

    calibration = {}
    for bucket, data in sorted(buckets.items()):
        if data["count"] > 0:
            predicted_avg = data["predicted"] / data["count"]
            actual_avg = data["actual_wins"] / data["count"]
            calibration[f"{bucket}-{bucket+2}%"] = {
                "predicted_avg": round(predicted_avg * 100, 2),
                "actual_win_rate": round(actual_avg * 100, 2),
                "sample_size": data["count"],
            }

    # Save updated ratings
    ratings_path.write_text(json.dumps(ratings, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save calibration
    cal_path = MODEL_DIR / "calibration.json"
    cal_path.write_text(json.dumps(calibration, indent=2), encoding="utf-8")

    # Save model card
    card_lines = [
        "# Trainer Brain Model Card v2",
        f"**Last Updated:** {today}",
        "",
        "## Model Description",
        "- **ELO Rating System**: Updated from race outcomes (K=16)",
        "- **Form Cycle**: PEAKING / READY / NEEDS_WORK / REST_REQUIRED",
        "- **Win% / Top3%**: Derived from relative ELO position",
        f"- **ELO Range**: {min(elos):.0f} - {max(elos):.0f} (avg {avg_elo:.0f})" if elos else "",
        "",
        "## Training Data",
        f"- Outcomes processed: {len(outcomes)}",
        f"- ELO updates: {updates}",
        f"- Predictions logged: {len(predictions)}",
        "",
        "## Calibration",
    ]
    if calibration:
        card_lines.append("| Predicted Win% | Actual Win Rate | Sample Size |")
        card_lines.append("|----------------|-----------------|-------------|")
        for bucket_name, data in calibration.items():
            card_lines.append(f"| {bucket_name} | {data['actual_win_rate']}% | {data['sample_size']} |")
    else:
        card_lines.append("*No calibration data yet — need matched predictions + outcomes.*")

    card_lines.extend([
        "",
        "## Limitations",
        "- ELO baseline is 1200; no opponent data incorporated yet",
        "- Win% is relative to stable average, not absolute field strength",
        "- Calibration requires more data for meaningful buckets",
        "- Form cycle is heuristic, not ML-trained",
        "",
        "---",
        f"*Model Card · {today}*",
    ])

    card = "\n".join(card_lines) + "\n"
    (MODEL_DIR / "model_card.md").write_text(card, encoding="utf-8")
    print(f"model_card.md updated")
    print(f"Calibration: {len(calibration)} buckets")


if __name__ == "__main__":
    main()
