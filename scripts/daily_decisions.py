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

    # Load works intelligence (new)
    wf_path = OUTPUTS / f"works_features_{today}.json"
    if not wf_path.exists():
        wf_matches = sorted(OUTPUTS.glob("works_features_*.json"), reverse=True)
        if wf_matches:
            wf_path = wf_matches[0]
    works_features = load_json(wf_path) if wf_path.exists() else []
    wf_by_name = {}
    if isinstance(works_features, list):
        wf_by_name = {h.get("horse_name", ""): h for h in works_features}

    # Load approval queue (new)
    queue = load_json(OUTPUTS / "approval_queue.json")
    if not isinstance(queue, list):
        queue = []

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
        lines.append("*No live entries detected — check nominations in Race_Opportunities.md*")
    lines.append("")

    # Section 2: Action Items
    lines.append("## ⚡ Must-Do Actions")

    # Overracing wall alerts (NEW — from Stu's experiment)
    for name, wf in wf_by_name.items():
        if wf.get("overracing_risk") == "HIGH":
            lines.append(f"- 🚨 **{name}** — OVERRACING WALL ({wf.get('races_60d', '?')} races in 60d, few works)")
            lines.append(f"  → STOP racing immediately. Schedule works between races (Stu's data)")
        elif wf.get("overracing_risk") == "WATCH":
            lines.append(f"- ⚠️ **{name}** — overracing watch ({wf.get('races_60d', '?')} races in 60d)")

    # Stamina alerts
    for h in snap.get("horses", []):
        stam_str = str(h.get("stamina", "100")).replace("%", "")
        try:
            stam_val = float(stam_str)
        except ValueError:
            continue
        if stam_val < 75:
            lines.append(f"- 🔴 **{h['name']}** — stamina {stam_val:.0f}%, SCRATCH RISK (<75 = auto-scratch)")
        elif stam_val < 85:
            lines.append(f"- ⚠️ **{h['name']}** — stamina {stam_val:.0f}%, extended rest needed")

    # Condition alerts
    for h in snap.get("horses", []):
        cond_str = str(h.get("condition", "100")).replace("%", "")
        try:
            cond_val = float(cond_str)
        except ValueError:
            continue
        if cond_val < 75:
            lines.append(f"- 🔴 **{h['name']}** — condition {cond_val:.0f}%, SCRATCH RISK (<75 = auto-scratch)")
        elif cond_val < 90:
            lines.append(f"- ⚠️ **{h['name']}** — condition {cond_val:.0f}%, NOT race-ready (need 95%+)")

    # Race placement intelligence (NEW)
    for q in queue:
        if q.get("action") == "enter_race" and q.get("placement_note"):
            lines.append(f"- 🎯 **{q['horse']}** — {q['placement_note']}")
            if q.get("sb_eligible"):
                lines.append(f"  → {q.get('sb_note', 'Check SB races first!')}")

    # Dormant horses
    dormant = [h for h in snap.get("horses", [])
               if h.get("age") == "3" and int(h.get("record", {}).get("starts", 0)) == 0
               and str(h.get("consistency", "0")).replace("+", "").isdigit()
               and int(str(h.get("consistency", "0")).replace("+", "")) >= 4]
    if dormant:
        names = [h["name"] for h in dormant]
        lines.append(f"- 💤 **{len(dormant)} ready 3YOs unraced:** {', '.join(names[:5])}")
        lines.append(f"  → Enter in MSW or maiden claimer races")

    # Gelding candidate
    if ratings:
        for name, m in ratings.items():
            if m.get("srf_races", 0) >= 5 and m.get("srf_avg", 0) < 82:
                lines.append(f"- 🔧 **{name}** — consider gelding (avg SRF {m['srf_avg']}, underperforming)")

    lines.append("")

    # Section 3: 5f Quality Tiers (NEW — Maximum Cool benchmarks)
    lines.append("## 🏅 5f Work Quality Tiers")
    tier_order = ["ULTRA_RARE", "STAKES", "PAY_SIDE", "FREE_LEVEL", "QUESTIONABLE", "NOT_USEFUL"]
    tier_emoji = {"ULTRA_RARE": "💎", "STAKES": "🏆", "PAY_SIDE": "💰", "FREE_LEVEL": "🆓",
                  "QUESTIONABLE": "❓", "NOT_USEFUL": "⛔"}
    tier_desc = {"ULTRA_RARE": "sub-1:03", "STAKES": "sub-1:04", "PAY_SIDE": "sub-1:05",
                 "FREE_LEVEL": "1:05-1:06", "QUESTIONABLE": "1:06-1:07", "NOT_USEFUL": "1:07+"}
    has_tiers = False
    for tier in tier_order:
        horses_in_tier = [n for n, wf in wf_by_name.items()
                          if wf.get("work_quality_tier") == tier]
        if horses_in_tier:
            has_tiers = True
            emoji = tier_emoji.get(tier, "")
            desc = tier_desc.get(tier, "")
            lines.append(f"- {emoji} **{tier}** ({desc}): {', '.join(sorted(horses_in_tier)[:8])}")
    if not has_tiers:
        lines.append("*Run works intelligence first*")
    lines.append("")

    # Section 4: Power Rankings
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

    # Section 5: Key Rules (UPDATED with expert knowledge)
    lines.append("## 📜 Expert Rules (SimRacingForm + Forums)")
    lines.append("- **Race at 95%+ condition** (high > low — 106% beats 94% every time)")
    lines.append("- **Target 5-7 horse fields** (57%W vs 18% in 10-horse)")
    lines.append("- **3 breezes : 1 handily** ratio for work schedule (Maximum Cool)")
    lines.append("- **Check SB races FIRST** (SB wins don't burn NW conditions)")
    lines.append("- **Max 3 races per 60 days** without works between (Stu's overracing wall)")
    lines.append("- **Ship day-of** is viable — no consistency penalty (La Canada Option 4)")
    lines.append("- **Consistency needs 2-4 works+races per 30 days** to climb")
    lines.append("")

    # Section 6: Financial
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
