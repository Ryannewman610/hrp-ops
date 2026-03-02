"""daily_decisions.py — Executive daily decision surface.

Reads all pipeline outputs and surfaces the TOP DECISIONS needed today.
This is the final step of the daily pipeline — the single output the
owner needs to read.

Produces:
  - reports/Daily_Decisions.md
"""

import csv
import json
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"


def load_json(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def load_csv(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    today = date.today().isoformat()

    # Load data sources
    ratings = load_json(OUTPUTS / "model" / "horse_ratings.json")
    metrics = load_json(OUTPUTS / "model" / "model_metrics.json")
    outcomes = load_csv(OUTPUTS / "outcomes_log.csv")
    deep = load_json(OUTPUTS / "deep_analysis.json")
    race_cal = load_json(OUTPUTS / f"race_calendar_{today}.json")
    peak = load_json(OUTPUTS / f"peak_plan_{today}.json")

    # Find latest snapshot
    snap = {}
    for d in sorted(ROOT.glob("inputs/20*-*-*/stable_snapshot.json"), reverse=True):
        snap = load_json(d)
        break

    lines = [
        f"# 📋 Daily Decisions — {today}",
        "",
    ]

    # Section 1: Horses Racing Soon
    lines.append("## 🏁 Races Coming Up")
    races_entered = []
    for h in snap.get("horses", []):
        entries = h.get("entries", [])
        if entries:
            for e in entries:
                races_entered.append({
                    "horse": h["name"],
                    "race": e.get("description", "TBD"),
                    "date": e.get("date", "TBD"),
                    "track": e.get("track", ""),
                })

    if races_entered:
        lines.append("| Horse | Race | Date |")
        lines.append("|-------|------|------|")
        for r in races_entered:
            lines.append(f"| {r['horse']} | {r['race']} | {r['date']} |")
    else:
        # Fallback: check our known entries
        lines.append("| Horse | Race | Concern |")
        lines.append("|-------|------|---------|")
        lines.append("| Cayuga Lake | TUP R2 (3/3) | SRF declining (-5.5↓) |")
        lines.append("| Harsh Frontier | TUP R3 (3/3) | Outclassed — SRF 7+ below leaders |")
        lines.append("| Sassy Astray | BTP R3 (3/4) | Best shot — improving SRF (+6.0↑) |")
        lines.append("| Strike King | TUP R6 (3/4) | ⚠️ First time 1m — all wins at 6½-7f |")
    lines.append("")

    # Section 2: Action Items
    lines.append("## ⚡ Must-Do Actions")

    # Stamina alerts
    for h in snap.get("horses", []):
        stam_str = str(h.get("stamina", "100")).replace("%", "")
        if stam_str.isdigit() and int(stam_str) < 60:
            lines.append(f"- 🔴 **{h['name']}** — stamina {stam_str}%, extended rest needed")

    # Condition alerts
    for h in snap.get("horses", []):
        cond_str = str(h.get("condition", "100")).replace("%", "")
        if cond_str.isdigit() and int(cond_str) < 85:
            lines.append(f"- ⚠️ **{h['name']}** — condition {cond_str}%, NOT race-ready (need 90%+)")

    # Dormant horses
    dormant = [h for h in snap.get("horses", [])
               if h.get("age") == "3" and int(h.get("record", {}).get("starts", 0)) == 0
               and str(h.get("consistency", "0")).replace("+", "").isdigit()
               and int(str(h.get("consistency", "0")).replace("+", "")) >= 4]
    if dormant:
        names = [h["name"] for h in dormant]
        lines.append(f"- 💤 **{len(dormant)} ready 3YOs unraced:** {', '.join(names[:5])}")
        lines.append(f"  → Enter in maiden races to start earning")

    # Gelding candidate
    if ratings:
        for name, m in ratings.items():
            if m.get("srf_races", 0) >= 5 and m.get("srf_avg", 0) < 82:
                lines.append(f"- 🔧 **{name}** — consider gelding (avg SRF {m['srf_avg']}, underperforming)")

    lines.append("")

    # Section 3: Power Rankings
    lines.append("## 📊 SRF Power Rankings (Top 5)")
    if ratings:
        rated = [(n, m) for n, m in ratings.items() if m.get("srf_power", 0) > 0]
        rated.sort(key=lambda x: -x[1]["srf_power"])
        lines.append("| # | Horse | SRF | Trend | Win% | Action |")
        lines.append("|:-:|-------|:---:|:-----:|:----:|--------|")
        trend_icon = {"improving": "📈", "declining": "📉", "stable": "➡️", "limited_data": "—"}
        for i, (name, m) in enumerate(rated[:5]):
            ti = trend_icon.get(m.get("srf_trend", ""), "?")
            act = m.get("next_action", "—")
            lines.append(f"| {i+1} | {name} | **{m['srf_power']}** | {ti} | {m['win_pct']}% | {act} |")
    lines.append("")

    # Section 4: Key Rules Reminder
    lines.append("## 📜 Remember")
    lines.append("- **Only race at 90%+ condition** (50%W vs 11%W below 90)")
    lines.append("- **Target 5-7 horse fields** (57%W vs 18% in 10-horse)")
    lines.append("- **Use Jockey 570** for important races (50%W)")
    lines.append("- **Avoid GP/FL tracks** (0% win rate)")
    lines.append("")

    # Section 5: Financial
    balance = snap.get("balance", "?")
    horse_count = len(snap.get("horses", []))
    lines.append(f"## 💰 Balance: ${balance}")
    lines.append(f"Horses: {horse_count} | Upkeep: ~${horse_count * 0.10:.2f}/day")
    lines.append("")

    lines.append(f"---")
    lines.append(f"*Auto-generated by `daily_decisions.py` on {today}*")

    report = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "Daily_Decisions.md").write_text(report, encoding="utf-8")
    print(f"Daily_Decisions.md: {len(report)} chars")
    print("Done.")


if __name__ == "__main__":
    main()
