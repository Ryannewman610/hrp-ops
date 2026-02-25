"""14_trainer_scoreboard.py — Scorecard joining predictions to outcomes.

Joins predictions_log.csv to outcomes_log.csv by horse_name + date + track.
Produces reports/Trainer_Scoreboard.md with accuracy metrics.
"""

import csv
import json
import re
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    predictions = load_csv(OUTPUTS / "predictions_log.csv")
    outcomes = load_csv(OUTPUTS / "outcomes_log.csv")

    print(f"Predictions: {len(predictions)}")
    print(f"Outcomes: {len(outcomes)}")

    if not predictions:
        print("No predictions yet. Run 11_recommend first.")
        return

    # Build outcome lookup: norm(horse) + date + norm(track) → outcome
    outcome_map = {}
    for o in outcomes:
        key = f"{norm(o.get('horse_name', ''))}_{o.get('date', '')}_{norm(o.get('track', ''))}"
        if key not in outcome_map:
            outcome_map[key] = o

    # Join predictions to outcomes
    joined = []
    unmatched_preds = 0
    for p in predictions:
        key = f"{norm(p.get('horse_name', ''))}_{p.get('date', '')}_{norm(p.get('track', ''))}"
        outcome = outcome_map.get(key)
        if outcome:
            joined.append({
                "horse": p.get("horse_name", ""),
                "date": p.get("date", ""),
                "track": p.get("track", ""),
                "race_num": p.get("race_num", ""),
                "predicted_win": safe_float(p.get("predicted_win_prob")),
                "predicted_top3": safe_float(p.get("predicted_top3_prob")),
                "ev_score": safe_float(p.get("ev_score")),
                "fit_score": safe_float(p.get("fit_score")),
                "form_tag": p.get("form_tag", ""),
                "finish": outcome.get("finish_position", ""),
                "purse": outcome.get("purse_earned", ""),
                "field_size": outcome.get("field_size_final", ""),
            })
        else:
            unmatched_preds += 1

    print(f"Joined: {len(joined)}")
    print(f"Unmatched predictions: {unmatched_preds}")

    # Calculate metrics
    total = len(joined)
    wins = 0
    top3 = 0
    brier_sum = 0.0
    ev_realized = []

    by_track = defaultdict(lambda: {"total": 0, "wins": 0, "top3": 0})
    by_form = defaultdict(lambda: {"total": 0, "wins": 0, "top3": 0})

    biggest_wins = []
    biggest_misses = []

    for j in joined:
        finish = j["finish"]
        finish_int = None
        if finish and finish.isdigit():
            finish_int = int(finish)
        elif finish and finish.lower() in ("dnf", "scratched", "fell"):
            finish_int = 99

        is_win = finish_int == 1 if finish_int else False
        is_top3 = finish_int is not None and finish_int <= 3

        if is_win:
            wins += 1
        if is_top3:
            top3 += 1

        # Brier score for win prediction
        actual_win = 1.0 if is_win else 0.0
        pred_win = j["predicted_win"] / 100.0  # Convert from % to probability
        brier_sum += (pred_win - actual_win) ** 2

        # Track/form breakdown
        by_track[j["track"]]["total"] += 1
        if is_win:
            by_track[j["track"]]["wins"] += 1
        if is_top3:
            by_track[j["track"]]["top3"] += 1

        by_form[j["form_tag"]]["total"] += 1
        if is_win:
            by_form[j["form_tag"]]["wins"] += 1
        if is_top3:
            by_form[j["form_tag"]]["top3"] += 1

        # Biggest wins/misses
        if is_win:
            biggest_wins.append(j)
        if finish_int and finish_int > 6 and j["ev_score"] > 8:
            biggest_misses.append(j)

    biggest_wins.sort(key=lambda x: -x["ev_score"])
    biggest_misses.sort(key=lambda x: -x["ev_score"])

    # Generate Trainer_Scoreboard.md
    win_rate = (wins / total * 100) if total > 0 else 0
    top3_rate = (top3 / total * 100) if total > 0 else 0
    brier = (brier_sum / total) if total > 0 else 0

    lines = [
        "# 📊 Trainer Scoreboard",
        f"> **Generated:** {today} | **Predictions:** {len(predictions)} | **Outcomes:** {len(outcomes)} | **Joined:** {len(joined)}",
        "",
        "## Overall Performance",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total predictions matched | {total} |",
        f"| Win rate | {wins}/{total} ({win_rate:.1f}%) |",
        f"| Top-3 rate | {top3}/{total} ({top3_rate:.1f}%) |",
        f"| Brier score (win%) | {brier:.4f} |",
        f"| Unmatched predictions | {unmatched_preds} |",
        "",
    ]

    if by_track:
        lines.append("## By Track")
        lines.append("| Track | Races | Wins | Top3 | Win% |")
        lines.append("|-------|-------|------|------|------|")
        for t, d in sorted(by_track.items()):
            wr = d["wins"] / d["total"] * 100 if d["total"] > 0 else 0
            lines.append(f"| {t} | {d['total']} | {d['wins']} | {d['top3']} | {wr:.0f}% |")
        lines.append("")

    if by_form:
        lines.append("## By Form Tag")
        lines.append("| Form | Races | Wins | Top3 | Win% |")
        lines.append("|------|-------|------|------|------|")
        for f, d in sorted(by_form.items()):
            wr = d["wins"] / d["total"] * 100 if d["total"] > 0 else 0
            lines.append(f"| {f} | {d['total']} | {d['wins']} | {d['top3']} | {wr:.0f}% |")
        lines.append("")

    if biggest_wins:
        lines.append("## 🏆 Biggest Wins")
        for w in biggest_wins[:5]:
            lines.append(f"- **{w['horse']}** — {w['date']} {w['track']} R{w['race_num']} (EV {w['ev_score']}, predicted Win {w['predicted_win']}%)")
        lines.append("")

    if biggest_misses:
        lines.append("## ❌ Biggest Misses")
        for m in biggest_misses[:5]:
            lines.append(f"- **{m['horse']}** — {m['date']} {m['track']} R{m['race_num']} (EV {m['ev_score']}, finished {m['finish']})")
        lines.append("")

    if not joined:
        lines.append("## ⏳ No Matched Results Yet")
        lines.append("Predictions have been logged but no matching race outcomes found yet.")
        lines.append("Outcomes will match as races complete and results are exported.")
        lines.append("")

    lines.append("---")
    lines.append(f"*Trainer Scoreboard · {today}*")

    md = "\n".join(lines) + "\n"
    (REPORTS / "Trainer_Scoreboard.md").write_text(md, encoding="utf-8")
    print(f"Trainer_Scoreboard.md: {len(md)} chars")


if __name__ == "__main__":
    main()
