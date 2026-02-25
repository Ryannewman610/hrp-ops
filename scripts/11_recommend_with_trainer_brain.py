"""11_recommend_with_trainer_brain.py — Model-driven race recommendations.

Uses Trainer Brain model + structured race calendar (with field sizes) to produce:
  - reports/Race_Opportunities.md
  - reports/Approval_Pack.md
  - outputs/approval_queue.json
  - outputs/predictions_log_YYYY-MM-DD.json (PHASE 1)
  - outputs/predictions_log.csv (append-only)
  - Updates Stable_Dashboard.md
"""

import csv
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def is_real_race(race: Dict) -> bool:
    """With the new block parser, races are already validated.
    Just double-check for obvious issues."""
    if not race.get("date"):
        return False
    if not race.get("track"):
        return False
    # Track must not be "TRACK" or "RACE TYPE"
    if race["track"] in ("TRACK", "RACE TYPE", "RACE"):
        return False
    return True


def score_race_fit(horse_model: Dict, race: Dict, works_feat: Dict = None) -> Dict:
    """Score how well a race fits a horse, integrating works intelligence."""
    score = horse_model["ev_score"]
    reasons = []
    risks = []
    wf = works_feat or {}

    # Distance fit
    dist_text = race.get("distance", "")
    if dist_text:
        dist_f = parse_distance_furlongs(dist_text)
        if dist_f > 0:
            consist = horse_model.get("consistency", 0)
            if dist_f <= 6.5:
                if consist >= 3:
                    score += 5
                    reasons.append(f"Sprint ({dist_text})")
            elif dist_f <= 8.5:
                reasons.append(f"Mid ({dist_text})")
                score += 3
            else:
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
    race_type = race.get("race_type", "").lower()
    conditions = race.get("conditions", "").lower()
    is_maiden = "maiden" in race_type or "maiden" in conditions
    if is_maiden:
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
        reasons.append("🔥 PEAKING")
    elif cycle == "READY":
        reasons.append("✅ READY")
    elif cycle == "NEEDS_WORK":
        score -= 5
        risks.append("⚠️ Needs work")
    elif cycle == "REST_REQUIRED":
        score -= 20
        risks.append("🛏️ Rest required")

    # Field size bonus
    field_size = race.get("field_size")
    if field_size is not None:
        if field_size <= 5:
            score += 8
            reasons.append(f"Small field ({field_size})")
        elif field_size <= 7:
            score += 4
            reasons.append(f"Medium field ({field_size})")
        elif field_size >= 10:
            score -= 3
            risks.append(f"Large field ({field_size})")

    # === Works Intelligence Integration ===
    readiness = wf.get("readiness_index", 50)
    sharpness = wf.get("sharpness_index", 50)
    fatigue = wf.get("fatigue_proxy", 30)
    trend = wf.get("work_trend", "unknown")

    if readiness >= 75:
        score += 6
        reasons.append(f"🎯 Ready {readiness}")
    elif readiness >= 55:
        score += 2
    elif readiness < 35:
        score -= 8
        risks.append(f"⚠️ Low readiness {readiness}")

    if fatigue >= 60:
        score -= 5
        risks.append(f"😓 Fatigue {fatigue}")

    if trend == "improving":
        score += 3
        reasons.append("📈 Works improving")
    elif trend == "declining":
        score -= 3
        risks.append("📉 Works declining")

    # Confidence badge
    data_points = sum(1 for k in ["readiness_index", "sharpness_index", "work_trend"]
                      if k in wf)
    if data_points >= 2 and readiness >= 60:
        confidence = "HIGH"
    elif data_points >= 1:
        confidence = "MED"
    else:
        confidence = "LOW"

    return {
        "score": round(score, 1),
        "reasons": reasons,
        "risks": risks,
        "confidence": confidence,
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
        cals = sorted(OUTPUTS.glob("race_calendar_*.json"), reverse=True)
        if cals:
            cal_path = cals[0]
    races_all = json.loads(cal_path.read_text(encoding="utf-8")).get("races", []) if cal_path.exists() else []

    races = [r for r in races_all if is_real_race(r)]
    print(f"Races: {len(races_all)} total, {len(races)} valid")

    # Load entries from tracker nominations
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

    # Load works features
    wf_path = OUTPUTS / f"works_features_{today}.json"
    if not wf_path.exists():
        wfs = sorted(OUTPUTS.glob("works_features_*.json"), reverse=True)
        if wfs:
            wf_path = wfs[0]
    works_features = json.loads(wf_path.read_text(encoding="utf-8")) if wf_path.exists() else []
    wf_by_norm = {norm(f["horse_name"]): f for f in works_features}
    print(f"Works features loaded: {len(works_features)} horses")

    # Score each horse against each valid race
    recommendations: List[Dict] = []
    for name, model in horse_models.items():
        h_norm = norm(name)
        if h_norm in INACTIVE:
            continue

        snap_h = snap_by_norm.get(h_norm, {})
        model["track"] = snap_h.get("track", "?")
        model["record"] = snap_h.get("record", {})
        wf = wf_by_norm.get(h_norm, {})

        already_entered = h_norm in entered_norms

        race_scores = []
        for race in races:
            fit = score_race_fit(model, race, wf)
            if fit["score"] > 0:
                entry = {
                    "race": race,
                    "score": fit["score"],
                    "reasons": fit["reasons"],
                    "risks": fit["risks"],
                    "field_size": race.get("field_size"),
                }
                race_scores.append(entry)
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
        "# 🏁 Race Opportunities — Trainer Brain v2",
        f"> **Generated:** {today} | **Model:** ELO + Form Cycle | "
        f"**Races:** {len(races)} valid",
        "",
    ]

    # Already entered
    entered = [r for r in recommendations if r["already_entered"]]
    if entered:
        lines.append("## ✅ Already Entered / Nominated")
        lines.append("| Horse | ELO | Win% | Top3% | EV | Form |")
        lines.append("|-------|-----|------|-------|-----|------|")
        for r in sorted(entered, key=lambda x: -x["ev_score"]):
            ci = {"PEAKING": "🔥", "READY": "✅", "NEEDS_WORK": "🏋️", "REST_REQUIRED": "🛏️"}.get(r["form_cycle"], "?")
            lines.append(f"| {r['horse']} | {r['elo']} | {r['win_pct']}% | {r['top3_pct']}% | {r['ev_score']} | {ci} |")
        lines.append("")

    # PEAKING + READY with race targets
    active = [r for r in recommendations
              if r["form_cycle"] in ("PEAKING", "READY") and not r["already_entered"] and r["top_races"]]
    if active:
        lines.append("## 🎯 Race Targets (Approval Required)")
        for r in sorted(active, key=lambda x: -x["ev_score"]):
            rec = r.get("record", {})
            rec_str = f"{rec.get('wins', 0)}W/{rec.get('starts', 0)}S" if rec.get("starts") else "Unraced"
            ci = "🔥" if r["form_cycle"] == "PEAKING" else "✅"
            lines.append(f"### {ci} {r['horse']} — ELO {r['elo']} | Win {r['win_pct']}% | Top3 {r['top3_pct']}% | EV {r['ev_score']}")
            lines.append(f"*{rec_str} · {r['track']} · Stam {r['stamina']}%*")
            lines.append("")
            lines.append("| # | Race | Field | Fit | Why | Risks |")
            lines.append("|---|------|-------|-----|-----|-------|")
            for i, tr in enumerate(r["top_races"], 1):
                race = tr["race"]
                desc = f"{race.get('date','?')} · {race.get('track','?')} R{race.get('race_num','?')} · {race.get('distance','')} {race.get('surface','')} · {race.get('race_type','')}"
                fld = str(tr.get("field_size")) if tr.get("field_size") is not None else "?"
                fit_txt = "; ".join(tr["reasons"][:3])
                risk_txt = "; ".join(tr["risks"][:2]) if tr["risks"] else "—"
                lines.append(f"| {i} | {desc} | {fld} | {tr['score']} | {fit_txt} | {risk_txt} |")
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
    lines.append(f"*Trainer Brain v2 · ELO + Form Cycle · {today}*")
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
                "race_id": race.get("race_id", ""),
                "race_date": race.get("date", ""),
                "race_track": race.get("track", ""),
                "race_num": race.get("race_num", ""),
                "race_distance": race.get("distance", ""),
                "race_conditions": race.get("race_type", ""),
                "race_purse": race.get("purse", ""),
                "field_size": race.get("field_size"),
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

    # ── Approval Pack ──────────────────────────────────

    pack_lines = [
        "# 📋 Approval Pack",
        f"> **Generated:** {today} | **Model:** ELO + Form Cycle v2",
        "",
        "## Instructions",
        "Review each recommendation. Check box to approve, leave unchecked to skip.",
        "Only approved items should be manually entered on HRP.",
        "",
    ]

    entered_q = [q for q in queue if q.get("action") == "review_entry"]
    if entered_q:
        pack_lines.append("## ✅ Already Nominated (Review)")
        for q in entered_q:
            pack_lines.append(f"- [ ] **{q['horse']}** — EV {q.get('ev_score',0)} | Win {q.get('win_pct',0)}% | {q['form_cycle']}")
            pack_lines.append(f"  - [Profile](https://www.horseracingpark.com/stables/horse.aspx?Horse={q['horse'].replace(' ', '+')})")
        pack_lines.append("")

    entry_q = [q for q in queue if q.get("action") == "enter_race"]
    if entry_q:
        pack_lines.append("## 🎯 Recommended Entries (Approval Required)")
        for q in sorted(entry_q, key=lambda x: -(x.get("ev_score", 0))):
            track = q.get("race_track", "?")
            race_date = q.get("race_date", "?")
            race_num = q.get("race_num", "?")
            dist = q.get("race_distance", "?")
            cond = q.get("race_conditions", "")
            fld = q.get("field_size")
            fld_str = f" (Field: {fld})" if fld else ""
            pack_lines.append(f"- [ ] **{q['horse']}** → {race_date} {track} R#{race_num} {dist} {cond}{fld_str}")
            pack_lines.append(f"  - EV {q.get('ev_score',0)} | Win {q.get('win_pct',0)}% | Top3 {q.get('top3_pct',0)}% | Form: {q['form_cycle']}")
            pack_lines.append(f"  - Fit: {'; '.join(q.get('reasons', [])[:3])}")
            if q.get("risks"):
                pack_lines.append(f"  - Risks: {'; '.join(q['risks'][:2])}")
            pack_lines.append(f"  - **Steps:** [Find a Race](https://www.horseracingpark.com/stables/find_race.aspx) → Select **{track}** → Race #{race_num} → Enter **{q['horse']}**")
            pack_lines.append(f"  - [Horse Profile](https://www.horseracingpark.com/stables/horse.aspx?Horse={q['horse'].replace(' ', '+')})")
        pack_lines.append("")

    work_q = [q for q in queue if q.get("action") in ("timed_work", "rest")]
    if work_q:
        pack_lines.append("## 🏋️ Training / Rest (No Approval Needed)")
        for q in work_q:
            action = "🛏️ Rest" if q["action"] == "rest" else "🏋️ Timed Work"
            pack_lines.append(f"- [x] **{q['horse']}** — {action}: {q.get('reason', '')}")
        pack_lines.append("")

    pack_lines.extend([
        "---",
        f"*Approval Pack generated by Trainer Brain v2 — {today}*",
        "*SAFETY: No in-game actions taken. All entries require manual execution.*",
    ])

    pack = "\n".join(pack_lines) + "\n"
    (REPORTS / "Approval_Pack.md").write_text(pack, encoding="utf-8")
    print(f"Approval_Pack.md: {len(pack)} chars")

    # ── PHASE 1: Predictions Log ──────────────────────

    predictions = []
    for r in recommendations:
        if not r["top_races"]:
            continue
        for tr in r["top_races"]:
            race = tr["race"]
            predictions.append({
                "generated_at": datetime.now().isoformat(),
                "horse_name": r["horse"],
                "race_id": race.get("race_id", ""),
                "track": race.get("track", ""),
                "date": race.get("date", ""),
                "race_num": race.get("race_num", ""),
                "distance": race.get("distance", ""),
                "surface": race.get("surface", ""),
                "race_type": race.get("race_type", ""),
                "conditions": race.get("conditions", "")[:100],
                "form_tag": r["form_cycle"],
                "predicted_win_prob": r["win_pct"],
                "predicted_top3_prob": r["top3_pct"],
                "ev_score": r["ev_score"],
                "fit_score": tr["score"],
                "field_size": race.get("field_size"),
                "purse": race.get("purse", ""),
                "approved": "",
            })

    # Save daily JSON
    pred_json_path = OUTPUTS / f"predictions_log_{today}.json"
    pred_json_path.write_text(json.dumps(predictions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"predictions_log_{today}.json: {len(predictions)} predictions")

    # Append to CSV (create if not exists)
    csv_path = OUTPUTS / "predictions_log.csv"
    csv_exists = csv_path.exists()
    fieldnames = [
        "generated_at", "horse_name", "race_id", "track", "date", "race_num",
        "distance", "surface", "race_type", "conditions", "form_tag",
        "predicted_win_prob", "predicted_top3_prob", "ev_score", "fit_score",
        "field_size", "purse", "approved",
    ]
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not csv_exists:
            writer.writeheader()
        for p in predictions:
            writer.writerow(p)
    print(f"predictions_log.csv: appended {len(predictions)} rows")

    # ── Summary ────────────────────────────────────────

    counts = {}
    for r in recommendations:
        counts[r["form_cycle"]] = counts.get(r["form_cycle"], 0) + 1
    print(f"\nForm Cycle Summary:")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
