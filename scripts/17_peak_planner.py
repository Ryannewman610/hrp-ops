"""17_peak_planner.py — 14-day per-horse plan with actions.

Generates a daily schedule for each horse: REST / WORK / RACE TARGET.
Uses works intelligence features + race calendar + snapshot meters.

Hard constraints:
  - stamina < 70% → no racing, rest only
  - No consecutive hard works (2+ day gap required)
  - Max 1 race per horse in window unless clearly justified
  - Freshen with rest days between work and race
  - Overracing wall: 4+ races in 60d without works → force rest+works cycle
  - High > low rule: 106% condition/stamina beats 94% (prefer slightly high)

Shipping strategies (La Canada):
  - Option 2: Farm training mode → ship 10d pre-race → train race morning
  - Option 4: Ship from farm day-of (no real consistency penalty despite claims)
  - Option 5: Ship 100/100 non-slow-transit to 1/1/2 track → arrives green/green

Output: outputs/peak_plan_YYYY-MM-DD.json
        reports/Training_Plan.md
"""

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
MODEL_DIR = OUTPUTS / "model"
REPORTS = ROOT / "reports"
INACTIVE = {"shebasbriar", "averyspluck", "hiptag793004736512"}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_latest_json(pattern: str) -> Dict:
    matches = sorted(OUTPUTS.glob(pattern), reverse=True)
    if matches:
        return json.loads(matches[0].read_text(encoding="utf-8"))
    return {}


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    today = date.today()
    today_s = today.isoformat()

    # Load works features
    wf_path = OUTPUTS / f"works_features_{today_s}.json"
    if not wf_path.exists():
        matches = sorted(OUTPUTS.glob("works_features_*.json"), reverse=True)
        if matches:
            wf_path = matches[0]
    works_features = json.loads(wf_path.read_text(encoding="utf-8")) if wf_path.exists() else []
    wf_by_norm = {norm(f["horse_name"]): f for f in works_features}

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
    horses = [h for h in snap.get("horses", []) if norm(h["name"]) not in INACTIVE]

    # Load race calendar
    cal_path = OUTPUTS / f"race_calendar_{today_s}.json"
    if not cal_path.exists():
        cals = sorted(OUTPUTS.glob("race_calendar_*.json"), reverse=True)
        if cals:
            cal_path = cals[0]
    races = json.loads(cal_path.read_text(encoding="utf-8")).get("races", []) if cal_path.exists() else []

    # Load horse ratings
    ratings_path = MODEL_DIR / "horse_ratings.json"
    ratings = json.loads(ratings_path.read_text(encoding="utf-8")) if ratings_path.exists() else {}

    # Build 14-day windows
    window = [today + timedelta(days=i) for i in range(14)]
    window_strs = [d.isoformat() for d in window]

    # Index races by date (normalize MM/DD/YYYY to ISO)
    races_by_date: Dict[str, List[Dict]] = {}
    for r in races:
        rd = r.get("date", "")
        # Convert M/D/YYYY to ISO
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", rd)
        if m:
            iso = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
            races_by_date.setdefault(iso, []).append(r)

    print(f"Horses: {len(horses)}, Races: {len(races)}, Window: {window_strs[0]} to {window_strs[-1]}")

    # Generate plans
    plans = []
    peaking_soon = []
    at_risk = []

    for h in horses:
        h_norm = norm(h["name"])
        wf = wf_by_norm.get(h_norm, {})
        rat = None
        for rname, rmod in ratings.items():
            if norm(rname) == h_norm:
                rat = rmod
                break

        stam_raw = h.get("stamina", "100%").replace("%", "")
        try:
            stam = float(stam_raw)
        except ValueError:
            stam = 100.0

        cond_raw = h.get("condition", "100%").replace("%", "")
        try:
            cond = float(cond_raw)
        except ValueError:
            cond = 100.0

        readiness = wf.get("readiness_index", 50)
        sharpness = wf.get("sharpness_index", 50)
        fatigue = wf.get("fatigue_proxy", 30)
        days_since_work = wf.get("days_since_last_work")
        form_cycle = rat.get("form_cycle", "UNKNOWN") if rat else "UNKNOWN"
        overracing_risk = wf.get("overracing_risk", "OK")
        work_quality_tier = wf.get("work_quality_tier", "NO_DATA")

        # Determine horse state and plan
        daily_plan: List[Dict] = []
        race_scheduled = False
        last_hard_work_day = -3  # Assume no recent hard work

        # OVERRACING WALL: force rest+work cycle if overraced
        if overracing_risk == "HIGH":
            for di, day in enumerate(window):
                day_s = day.isoformat()
                if di % 3 == 0 and di > 0:
                    daily_plan.append({"date": day_s, "day_offset": di,
                                       "action": "WORK", "work_type": "timed",
                                       "reason": "Recovery work — breaking overracing wall"})
                else:
                    daily_plan.append({"date": day_s, "day_offset": di,
                                       "action": "REST",
                                       "reason": "Rest — overracing recovery (Stu's 4-race wall)"})
            horse_plan = {
                "horse_name": h["name"],
                "stamina": stam,
                "condition": cond,
                "readiness_index": readiness,
                "sharpness_index": sharpness,
                "fatigue_proxy": fatigue,
                "form_cycle": form_cycle,
                "work_quality_tier": work_quality_tier,
                "overracing_risk": overracing_risk,
                "daily_plan": daily_plan,
            }
            plans.append(horse_plan)
            at_risk.append(h["name"])
            continue

        for di, day in enumerate(window):
            day_s = day.isoformat()
            action: Dict[str, Any] = {"date": day_s, "day_offset": di}

            # HARD CONSTRAINT: stamina < 70% → REST only
            if stam < 70:
                action["action"] = "REST"
                action["reason"] = f"Stamina {stam:.0f}% < 70% threshold"
                daily_plan.append(action)
                continue

            # Check if races available on this day
            day_races = races_by_date.get(day_s, [])

            # Day 0 = today
            if di == 0:
                # Today: based on current readiness
                if readiness >= 75 and day_races and not race_scheduled:
                    # Find best race
                    is_maiden = h.get("record", {}).get("wins", 0) == 0
                    eligible_races = day_races
                    if is_maiden:
                        eligible_races = [r for r in day_races
                                          if "maiden" in r.get("race_type", "").lower()]
                    if eligible_races:
                        race = eligible_races[0]
                        action["action"] = "RACE"
                        action["target_race"] = {
                            "race_id": race.get("race_id", ""),
                            "track": race.get("track", ""),
                            "race_num": race.get("race_num", ""),
                            "distance": race.get("distance", ""),
                            "race_type": race.get("race_type", ""),
                            "field_size": race.get("field_size"),
                        }
                        action["reason"] = f"Readiness {readiness}, sharp {sharpness}"
                        race_scheduled = True
                    else:
                        action["action"] = "WORK"
                        action["work_type"] = "timed"
                        action["reason"] = "No eligible race today; sharpen"
                elif fatigue >= 60:
                    action["action"] = "REST"
                    action["reason"] = f"Fatigue {fatigue} — recover"
                elif sharpness < 40:
                    action["action"] = "WORK"
                    action["work_type"] = "timed"
                    action["reason"] = f"Sharpness {sharpness} — need to work"
                else:
                    action["action"] = "REST"
                    action["reason"] = "Light day — maintain"
            else:
                # Future days: plan ahead
                if race_scheduled:
                    # After a race: rest 2-3 days
                    action["action"] = "REST"
                    action["reason"] = "Post-race recovery"
                elif di - last_hard_work_day < 2:
                    # Too close to last work
                    action["action"] = "REST"
                    action["reason"] = "Recovery between works"
                elif day_races and readiness >= 60 and not race_scheduled:
                    # Future race target
                    is_maiden = h.get("record", {}).get("wins", 0) == 0
                    eligible_races = day_races
                    if is_maiden:
                        eligible_races = [r for r in day_races
                                          if "maiden" in r.get("race_type", "").lower()]
                    if eligible_races:
                        race = eligible_races[0]
                        action["action"] = "RACE_TARGET"
                        action["target_race"] = {
                            "race_id": race.get("race_id", ""),
                            "track": race.get("track", ""),
                            "race_num": race.get("race_num", ""),
                            "distance": race.get("distance", ""),
                            "race_type": race.get("race_type", ""),
                            "field_size": race.get("field_size"),
                        }
                        action["reason"] = f"Target race — build toward peak"
                        race_scheduled = True
                    else:
                        # Work to build sharpness
                        if di % 3 == 0:
                            action["action"] = "WORK"
                            action["work_type"] = "timed"
                            action["reason"] = "Build fitness"
                            last_hard_work_day = di
                        else:
                            action["action"] = "REST"
                            action["reason"] = "Recovery"
                elif di % 3 == 0:
                    action["action"] = "WORK"
                    action["work_type"] = "timed"
                    action["reason"] = "Maintain fitness"
                    last_hard_work_day = di
                else:
                    action["action"] = "REST"
                    action["reason"] = "Recovery"

            daily_plan.append(action)

        horse_plan = {
            "horse_name": h["name"],
            "stamina": stam,
            "condition": cond,
            "readiness_index": readiness,
            "sharpness_index": sharpness,
            "fatigue_proxy": fatigue,
            "form_cycle": form_cycle,
            "daily_plan": daily_plan,
        }
        plans.append(horse_plan)

        # Track alerts
        if readiness >= 70 and stam >= 85:
            peaking_soon.append(h["name"])
        if fatigue >= 60 or stam < 75:
            at_risk.append(h["name"])

    # Save plan JSON
    plan_data = {
        "generated": today_s,
        "window": {"start": window_strs[0], "end": window_strs[-1]},
        "total_horses": len(plans),
        "peaking_soon": peaking_soon,
        "at_risk": at_risk,
        "plans": plans,
    }
    plan_path = OUTPUTS / f"peak_plan_{today_s}.json"
    plan_path.write_text(json.dumps(plan_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"peak_plan_{today_s}.json: {len(plans)} horse plans")

    # ── Generate Training_Plan.md ──────────────────────

    md = [
        "# 📋 Training Plan — Daily Orders",
        f"> **Generated:** {today_s} | **Horses:** {len(plans)} | **Window:** 14 days",
        "",
    ]

    # Today's orders
    md.append("## 🎯 Today's Orders")
    today_races = []
    today_works = []
    today_rests = []

    for p in plans:
        if not p["daily_plan"]:
            continue
        day0 = p["daily_plan"][0]
        act = day0.get("action", "")
        name = p["horse_name"]
        if act == "RACE":
            tr = day0.get("target_race", {})
            today_races.append(f"- 🏇 **{name}** → {tr.get('track', '?')} R#{tr.get('race_num', '?')} "
                               f"{tr.get('distance', '?')} {tr.get('race_type', '')} (Field {tr.get('field_size', '?')})")
        elif act == "WORK":
            today_works.append(f"- 🏋️ **{name}** — {day0.get('work_type', 'timed')} work ({day0.get('reason', '')})")
        else:
            today_rests.append(f"- 🛏️ **{name}** — rest ({day0.get('reason', '')})")

    if today_races:
        md.append("### Race Entries")
        md.extend(today_races)
        md.append("")
    if today_works:
        md.append("### Timed Works")
        md.extend(today_works)
        md.append("")
    if today_rests:
        md.append("### Rest")
        md.extend(today_rests)
        md.append("")

    # Peaking soon shortlist
    if peaking_soon:
        md.append("## ⚡ Peaking Soon")
        md.append("These horses have high readiness (≥70) and good stamina (≥85%):")
        for name in sorted(peaking_soon):
            wf = wf_by_norm.get(norm(name), {})
            md.append(f"- **{name}** — Readiness {wf.get('readiness_index', '?')}, "
                      f"Sharp {wf.get('sharpness_index', '?')}, Trend: {wf.get('work_trend', '?')}")
        md.append("")

    # At risk shortlist
    if at_risk:
        md.append("## ⚠️ At Risk / Fatigue")
        md.append("These horses have high fatigue (≥60) or low stamina (<75%):")
        for name in sorted(at_risk):
            wf = wf_by_norm.get(norm(name), {})
            snap_h = next((h for h in horses if h["name"] == name), {})
            md.append(f"- **{name}** — Fatigue {wf.get('fatigue_proxy', '?')}, "
                      f"Stamina {snap_h.get('stamina', '?')}")
        md.append("")

    # 7-day calendar view
    md.append("## 📅 7-Day View")
    md.append("| Horse | " + " | ".join([(today + timedelta(days=i)).strftime("%a %d") for i in range(7)]) + " |")
    md.append("|-------" + "|----" * 7 + "|")
    action_icons = {"RACE": "🏇", "RACE_TARGET": "🎯", "WORK": "🏋️", "REST": "💤"}
    for p in sorted(plans, key=lambda x: -x["readiness_index"])[:20]:  # Top 20
        row = f"| {p['horse_name']}"
        for i in range(7):
            if i < len(p["daily_plan"]):
                icon = action_icons.get(p["daily_plan"][i].get("action", ""), "·")
                row += f" | {icon}"
            else:
                row += " | ·"
        row += " |"
        md.append(row)
    md.append("")

    # Full 14-day view compact
    md.append("## 📅 14-Day Summary")
    md.append("| Horse | Ready | Sharp | Fat | Plan Summary |")
    md.append("|-------|-------|-------|-----|-------------|")
    for p in sorted(plans, key=lambda x: -x["readiness_index"]):
        acts = [d.get("action", "?")[0] for d in p["daily_plan"]]  # R/W/L
        plan_str = "".join(acts[:14])
        md.append(f"| {p['horse_name']} | {p['readiness_index']} | {p['sharpness_index']} | "
                  f"{p['fatigue_proxy']} | `{plan_str}` |")
    md.append("")

    md.extend([
        "---",
        f"*Training Plan v3 · {today_s}*",
        "*SAFETY: No in-game actions taken. All entries require manual execution.*",
    ])

    report = "\n".join(md) + "\n"
    (REPORTS / "Training_Plan.md").write_text(report, encoding="utf-8")
    print(f"Training_Plan.md: {len(report)} chars")


if __name__ == "__main__":
    main()
