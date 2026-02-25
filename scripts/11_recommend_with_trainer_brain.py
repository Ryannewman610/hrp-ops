"""11_recommend_with_trainer_brain.py — Model-driven race recommendations.

Uses Trainer Brain model outputs to produce:
  - reports/Race_Opportunities.md (Win%/Top3%/EV Score per race)
  - outputs/approval_queue.json
  - Updates Stable_Dashboard.md with Form Cycle tags
"""

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "outputs" / "model"
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"
INACTIVE = {"shebasbriar", "averyspluck", "hiptag793004736512"}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_distance_furlongs(dist: str) -> float:
    dist = dist.strip().lower()
    m = re.match(r"(\d+)\s*(\d+/\d+)?\s*([fm])", dist)
    if not m:
        return 0.0
    whole = int(m.group(1))
    frac = 0.0
    if m.group(2):
        num, den = m.group(2).split("/")
        frac = int(num) / int(den)
    val = whole + frac
    if m.group(3) == "m":
        val *= 8
    return round(val, 2)


# Garbage filter: terms that indicate non-race entries in calendar
GARBAGE_TERMS = [
    "handicapping", "stakes calendar", "track condition", "weather",
    "no headlines", "headlines", "toggle", "stables", "auctions",
    "breeding", "farms", "credits", "retire", "purchase",
    "month day year", "jan feb mar", "owner stats",
]


def is_real_race(race: Dict) -> bool:
    """Filter out non-race entries from calendar."""
    conditions = race.get("conditions", "").lower()
    raw = race.get("raw_text", "").lower()
    combined = conditions + " " + raw

    # Must have a date
    if not race.get("date"):
        return False

    # Check for garbage terms
    for term in GARBAGE_TERMS:
        if term in combined:
            return False

    # Must have meaningful class/conditions text
    class_keywords = ["clm", "oclm", "mdn", "mdspwt", "alw", "stk", "hcp",
                      "claiming", "maiden", "allowance", "stakes", "handicap",
                      "n1x", "n2x", "n3x", "statebred", "fillies",
                      "year-old", "opt"]
    if not any(kw in combined for kw in class_keywords):
        return False

    return True


def score_race_fit(horse_model: Dict, race: Dict) -> Dict:
    """Score how well a race fits a horse using model data."""
    score = horse_model["ev_score"]
    reasons = []
    risks = []

    # Distance fit
    dist_text = race.get("distance", "")
    if dist_text:
        dist_f = parse_distance_furlongs(dist_text)
        if dist_f > 0:
            # Use consistency as distance preference proxy
            consist = horse_model.get("consistency", 0)
            if dist_f <= 6.5:  # sprint
                if consist >= 3:
                    score += 5
                    reasons.append(f"Sprint distance ({dist_text})")
            elif dist_f <= 8.5:  # mid
                reasons.append(f"Mid distance ({dist_text})")
                score += 3
            else:  # route
                reasons.append(f"Route ({dist_text})")

    # Track match
    horse_track = horse_model.get("track", "")
    race_track = race.get("track", "")
    if horse_track and race_track:
        if race_track.upper() in horse_track.upper():
            score += 8
            reasons.append(f"Home track ({race_track})")
        else:
            score -= 2
            risks.append(f"Ship to {race_track}")

    # Class check
    conditions = race.get("conditions", "").lower()
    if "maiden" in conditions or "mdn" in conditions:
        record = horse_model.get("record", {})
        if int(record.get("wins", 0)) > 0:
            score -= 30
            risks.append("Ineligible: winner in maiden")
        else:
            score += 5
            reasons.append("Maiden eligible")

    # Form bonus
    cycle = horse_model.get("form_cycle", "")
    if cycle == "PEAKING":
        score += 5
        reasons.append("🔥 PEAKING form")
    elif cycle == "READY":
        reasons.append("✅ READY")
    elif cycle == "NEEDS_WORK":
        score -= 5
        risks.append("⚠️ Needs more work")
    elif cycle == "REST_REQUIRED":
        score -= 20
        risks.append("🛏️ Rest required")

    return {
        "score": round(score, 1),
        "reasons": reasons,
        "risks": risks,
    }


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    # Load model ratings
    ratings_path = MODEL_DIR / "horse_ratings.json"
    if not ratings_path.exists():
        print("ERROR: Run 10_fit_trainer_brain.py first")
        return
    horse_models = json.loads(ratings_path.read_text(encoding="utf-8"))

    # Load race calendar
    cal_path = OUTPUTS / f"race_calendar_{today}.json"
    if not cal_path.exists():
        # Find most recent
        cals = sorted(OUTPUTS.glob("race_calendar_*.json"), reverse=True)
        if cals:
            cal_path = cals[0]
    races_all = json.loads(cal_path.read_text(encoding="utf-8")).get("races", []) if cal_path.exists() else []

    # HARD FILTER: only real races
    races = [r for r in races_all if is_real_race(r)]
    filtered_count = len(races_all) - len(races)
    print(f"Races: {len(races_all)} total, {filtered_count} filtered, {len(races)} valid")

    # Load entries
    entries_path = OUTPUTS / f"upcoming_entries_{today}.json"
    if not entries_path.exists():
        ents = sorted(OUTPUTS.glob("upcoming_entries_*.json"), reverse=True)
        if ents:
            entries_path = ents[0]
    entries = json.loads(entries_path.read_text(encoding="utf-8")).get("entries", []) if entries_path.exists() else []
    entered_norms = {norm(e["horse_name"]) for e in entries
                     if e.get("source") == "tracker_nominations" and e.get("horse_name")}

    # Load snapshot for record data
    snap_path = ROOT / "inputs" / today / "stable_snapshot.json"
    if not snap_path.exists():
        dirs = sorted((ROOT / "inputs").glob("20*-*-*"), reverse=True)
        for d in dirs:
            sp = d / "stable_snapshot.json"
            if sp.exists():
                snap_path = sp
                break
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    snap_by_norm = {norm(h["name"]): h for h in snap.get("horses", [])}

    # Score each horse against each valid race
    recommendations: List[Dict] = []
    for name, model in horse_models.items():
        h_norm = norm(name)
        if h_norm in INACTIVE:
            continue

        snap_h = snap_by_norm.get(h_norm, {})
        model["track"] = snap_h.get("track", "?")
        model["record"] = snap_h.get("record", {})

        already_entered = h_norm in entered_norms

        # Score against all races
        race_scores = []
        for race in races:
            fit = score_race_fit(model, race)
            if fit["score"] > 0:
                race_scores.append({
                    "race": race,
                    "score": fit["score"],
                    "reasons": fit["reasons"],
                    "risks": fit["risks"],
                })
        race_scores.sort(key=lambda x: x["score"], reverse=True)
        top3 = race_scores[:3]

        recommendations.append({
            "horse": name,
            "elo": model["elo_rating"],
            "win_pct": model["win_pct"],
            "top3_pct": model["top3_pct"],
            "ev_score": model["ev_score"],
            "form_cycle": model["form_cycle"],
            "next_action": model["next_action"],
            "form_factors": model["form_factors"],
            "stamina": model["stamina"],
            "condition": model["condition"],
            "consistency": model["consistency"],
            "already_entered": already_entered,
            "top_races": top3,
            "track": model["track"],
            "record": model.get("record", {}),
        })

    # ── Generate Race_Opportunities.md ──────────────────

    lines = [
        "# 🏁 Race Opportunities — Trainer Brain v1",
        f"> **Generated:** {today} | **Model:** ELO + Form Cycle | "
        f"**Races:** {len(races)} valid ({filtered_count} filtered)",
        "",
    ]

    # Already entered
    entered = [r for r in recommendations if r["already_entered"]]
    if entered:
        lines.append("## ✅ Already Entered / Nominated")
        lines.append("| Horse | ELO | Win% | Top3% | EV | Form |")
        lines.append("|-------|-----|------|-------|-----|------|")
        for r in sorted(entered, key=lambda x: -x["ev_score"]):
            cycle_icon = {"PEAKING": "🔥", "READY": "✅", "NEEDS_WORK": "🏋️", "REST_REQUIRED": "🛏️"}.get(r["form_cycle"], "?")
            lines.append(f"| {r['horse']} | {r['elo']} | {r['win_pct']}% | {r['top3_pct']}% | {r['ev_score']} | {cycle_icon} |")
        lines.append("")

    # PEAKING + READY with race targets
    active = [r for r in recommendations
              if r["form_cycle"] in ("PEAKING", "READY") and not r["already_entered"] and r["top_races"]]
    if active:
        lines.append("## 🎯 Race Targets (Approval Required)")
        for r in sorted(active, key=lambda x: -x["ev_score"]):
            rec = r.get("record", {})
            rec_str = f"{rec.get('wins', 0)}W/{rec.get('starts', 0)}S" if rec.get("starts") else "Unraced"
            cycle_icon = "🔥" if r["form_cycle"] == "PEAKING" else "✅"
            lines.append(f"### {cycle_icon} {r['horse']} — ELO {r['elo']} | Win {r['win_pct']}% | Top3 {r['top3_pct']}% | EV {r['ev_score']}")
            lines.append(f"*{rec_str} · {r['track']} · Stam {r['stamina']}% · Factors: {'; '.join(r['form_factors'][:3])}*")
            lines.append("")
            lines.append("| # | Race | Fit Score | Why | Risks |")
            lines.append("|---|------|-----------|-----|-------|")
            for i, tr in enumerate(r["top_races"], 1):
                race = tr["race"]
                parts = []
                if race.get("date"):
                    parts.append(race["date"])
                if race.get("track"):
                    parts.append(race["track"])
                if race.get("distance"):
                    parts.append(race["distance"])
                if race.get("surface"):
                    parts.append(race["surface"])
                conds = race.get("conditions", "")[:45]
                if conds:
                    parts.append(conds)
                desc = " · ".join(parts)
                fit = "; ".join(tr["reasons"][:3])
                risk = "; ".join(tr["risks"][:2]) if tr["risks"] else "—"
                lines.append(f"| {i} | {desc} | {tr['score']} | {fit} | {risk} |")
            lines.append("")

    # Ready but no races
    no_match = [r for r in recommendations
                if r["form_cycle"] in ("PEAKING", "READY") and not r["already_entered"] and not r["top_races"]]
    if no_match:
        lines.append("## ❓ Ready — No Matching Races")
        lines.append("| Horse | ELO | Win% | EV | Form |")
        lines.append("|-------|-----|------|-----|------|")
        for r in no_match:
            lines.append(f"| {r['horse']} | {r['elo']} | {r['win_pct']}% | {r['ev_score']} | {r['form_cycle']} |")
        lines.append("")

    # Needs work
    work = [r for r in recommendations if r["form_cycle"] == "NEEDS_WORK"]
    if work:
        lines.append("## 🏋️ Needs Work")
        for r in work:
            lines.append(f"- **{r['horse']}** — Stam {r['stamina']}%, {'; '.join(r['form_factors'][:2])}")
        lines.append("")

    # Rest
    rest = [r for r in recommendations if r["form_cycle"] == "REST_REQUIRED"]
    if rest:
        lines.append("## 🛏️ Rest Required")
        for r in rest:
            lines.append(f"- **{r['horse']}** — Stam {r['stamina']}%, {'; '.join(r['form_factors'][:2])}")
        lines.append("")

    lines.append("---")
    lines.append(f"*Trainer Brain v1 · ELO + Form Cycle · {today}*")
    opp = "\n".join(lines) + "\n"
    (REPORTS / "Race_Opportunities.md").write_text(opp, encoding="utf-8")
    print(f"Race_Opportunities.md: {len(opp)} chars")

    # ── Approval Queue ──────────────────────────────────

    queue: List[Dict] = []
    for r in recommendations:
        if r["form_cycle"] == "REST_REQUIRED":
            queue.append({
                "horse": r["horse"], "action": "rest",
                "reason": f"Stamina {r['stamina']}%",
                "approval_required": False,
                "ev_score": r["ev_score"],
                "form_cycle": r["form_cycle"],
                "timestamp": datetime.now().isoformat(),
            })
        elif r["form_cycle"] == "NEEDS_WORK":
            queue.append({
                "horse": r["horse"], "action": "timed_work",
                "reason": "; ".join(r["form_factors"][:2]),
                "approval_required": False,
                "ev_score": r["ev_score"],
                "form_cycle": r["form_cycle"],
                "timestamp": datetime.now().isoformat(),
            })
        elif r["already_entered"]:
            queue.append({
                "horse": r["horse"], "action": "review_entry",
                "reason": "Already entered",
                "win_pct": r["win_pct"], "top3_pct": r["top3_pct"],
                "approval_required": True,
                "ev_score": r["ev_score"],
                "form_cycle": r["form_cycle"],
                "timestamp": datetime.now().isoformat(),
            })
        elif r["top_races"]:
            tr = r["top_races"][0]
            race = tr["race"]
            queue.append({
                "horse": r["horse"], "action": "enter_race",
                "race_date": race.get("date", ""),
                "race_track": race.get("track", ""),
                "race_distance": race.get("distance", ""),
                "race_conditions": race.get("conditions", "")[:60],
                "fit_score": tr["score"],
                "win_pct": r["win_pct"],
                "top3_pct": r["top3_pct"],
                "ev_score": r["ev_score"],
                "form_cycle": r["form_cycle"],
                "reasons": tr["reasons"],
                "risks": tr["risks"],
                "approval_required": True,
                "timestamp": datetime.now().isoformat(),
            })

    (OUTPUTS / "approval_queue.json").write_text(
        json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
    needs_approval = sum(1 for q in queue if q.get("approval_required"))
    print(f"approval_queue.json: {len(queue)} items ({needs_approval} need approval)")

    # ── Update Dashboard with Form Cycle ─────────────────

    dash_path = REPORTS / "Stable_Dashboard.md"
    if dash_path.exists():
        dash = dash_path.read_text(encoding="utf-8")
        # Add Form Cycle section if not present
        if "Form Cycle" not in dash:
            form_lines = [
                "",
                "## 📊 Form Cycle Overview",
                "| Horse | Form | ELO | Win% | Top3% | EV | Action |",
                "|-------|------|-----|------|-------|----|--------|",
            ]
            for r in sorted(recommendations, key=lambda x: -x["ev_score"]):
                cycle_icon = {"PEAKING": "🔥", "READY": "✅", "NEEDS_WORK": "🏋️", "REST_REQUIRED": "🛏️"}.get(r["form_cycle"], "?")
                form_lines.append(
                    f"| {r['horse']} | {cycle_icon} {r['form_cycle']} | {r['elo']} | "
                    f"{r['win_pct']}% | {r['top3_pct']}% | {r['ev_score']} | {r['next_action']} |")
            form_lines.append("")
            form_block = "\n".join(form_lines)
            # Insert before the footer
            if "---\n*Auto-generated" in dash:
                dash = dash.replace("---\n*Auto-generated", form_block + "\n---\n*Auto-generated")
            else:
                dash += form_block
            dash_path.write_text(dash, encoding="utf-8")
            print("Dashboard updated with Form Cycle")

    # Summary
    counts = {}
    for r in recommendations:
        counts[r["form_cycle"]] = counts.get(r["form_cycle"], 0) + 1
    print(f"\nForm Cycle Summary:")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
