"""17_build_2yo_dashboard.py -- 2YO-only dashboard and weekly plan.

Finds latest stable_snapshot.json, filters to 2-year-olds, and produces:
  - outputs/2yo_status.json   (structured data)
  - reports/2YO_Dashboard.md  (per-horse status table)
  - reports/2YO_Weekly_Plan.md (work schedule following baseline science)
"""

import json
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "inputs"
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"

# Baseline work template -- clean science, no variables
BASELINE_WORK = {
    "distance": "3f",
    "surface": "Dirt",
    "effort": "Breezing",
    "start": "Conservative",
    "pace": "Horse Lead",
    "weight": "120",
    "accessories": "None",
    "medications": "None",
}

STEP_UP_WORK = {
    "distance": "5f",
    "surface": "Dirt",
    "effort": "Breezing",
    "start": "Normal",
    "pace": "Horse Lead",
    "weight": "120",
}


def find_latest_snapshot():
    candidates = sorted(
        INPUTS.rglob("stable_snapshot.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def pct(val):
    try:
        return float(str(val).replace("%", "").strip())
    except (ValueError, TypeError):
        return 0.0


def pint(val):
    try:
        return int(str(val).replace("+", "").strip())
    except (ValueError, TypeError):
        return 0


def main():
    snap_path = find_latest_snapshot()
    if not snap_path:
        print("ERROR: No stable_snapshot.json found.")
        return

    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    all_horses = snap.get("horses", [])
    snap_date = snap_path.parent.name
    today = date.today()
    today_s = today.isoformat()

    # Filter to 2-year-olds
    twoyos = [h for h in all_horses if str(h.get("age", "")) == "2"]

    # Load works features if available
    wf_path = OUTPUTS / f"works_features_{today_s}.json"
    if not wf_path.exists():
        wf_candidates = sorted(OUTPUTS.glob("works_features_*.json"), reverse=True)
        wf_path = wf_candidates[0] if wf_candidates else None
    works_data = {}
    if wf_path and wf_path.exists():
        for wf in json.loads(wf_path.read_text(encoding="utf-8")):
            works_data[wf.get("horse_name", "")] = wf

    # Build status for each 2YO
    statuses = []
    for h in twoyos:
        name = h.get("name", "?")
        cond = pct(h.get("condition", "100%"))
        stam = pct(h.get("stamina", "100%"))
        consist = pint(h.get("consistency", "0"))
        sex = h.get("sex", "?")
        color = h.get("color", "?")
        sire = h.get("sire", "?")
        dam = h.get("dam", "?")
        track = h.get("track", "?")
        weight = h.get("weight", "?")
        height = h.get("height", "?")
        starts = pint(h.get("record", {}).get("starts", 0))
        wins = pint(h.get("record", {}).get("wins", 0))
        accessories = h.get("accessories", [])
        works_count = h.get("works_count", 0)

        wf = works_data.get(name, {})
        total_works = wf.get("total_works", 0)
        days_since = wf.get("days_since_last_work")
        sharpness = wf.get("sharpness_index", 0)
        readiness = wf.get("readiness_index", 0)

        # Readiness tag
        meters_ok = 95 <= cond <= 105 and 95 <= stam <= 105
        if starts > 0:
            tag = "[RACED]"
        elif consist >= 5 and meters_ok:
            tag = "[GO]"
        elif consist >= 3 and meters_ok:
            tag = "[FIT]"
        elif total_works >= 3 and meters_ok:
            tag = "[WORKING]"
        elif total_works >= 1:
            tag = "[BASELINE]"
        elif stam < 70:
            tag = "[LOW-STAM]"
        else:
            tag = "[NEW]"

        # Determine work phase
        if total_works == 0:
            phase = "Needs first 3f baseline"
        elif total_works < 3:
            phase = f"3f baselines ({total_works}/3 done)"
        elif total_works < 5:
            phase = f"Step up to 5f ({total_works} works)"
        elif consist >= 5:
            phase = "Race-ready -- find MSW"
        else:
            phase = f"Continue 5f works (+{consist} con)"

        statuses.append({
            "name": name,
            "age": 2,
            "sex": sex,
            "color": color,
            "sire": sire,
            "dam": dam,
            "height": height,
            "weight": weight,
            "track": track,
            "condition": cond,
            "stamina": stam,
            "consistency": consist,
            "starts": starts,
            "wins": wins,
            "total_works": total_works,
            "days_since_last_work": days_since,
            "sharpness": sharpness,
            "readiness": readiness,
            "accessories": accessories,
            "tag": tag,
            "phase": phase,
            "meters_ok": meters_ok,
        })

    # Sort: most advanced first
    tag_order = {"[GO]": 0, "[FIT]": 1, "[RACED]": 1, "[WORKING]": 2,
                 "[BASELINE]": 3, "[NEW]": 4, "[LOW-STAM]": 5}
    statuses.sort(key=lambda s: (tag_order.get(s["tag"], 9), -s["total_works"]))

    # ── Write outputs/2yo_status.json ──
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    status_out = OUTPUTS / "2yo_status.json"
    json.dump({"date": today_s, "count": len(statuses), "horses": statuses},
              open(status_out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    # ── Write reports/2YO_Dashboard.md ──
    REPORTS.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# 2YO Dashboard -- {today_s}",
        f"Snapshot: `{snap_date}` | 2-year-olds: {len(statuses)}",
        "",
        "| Tag | Horse | Sex | Cond | Stam | +Con | Works | Last Work | Track | Phase |",
        "|-----|-------|-----|------|------|------|-------|-----------|-------|-------|",
    ]
    for s in statuses:
        dsl = f"{s['days_since_last_work']}d ago" if s["days_since_last_work"] is not None else "never"
        lines.append(
            f"| {s['tag']} | {s['name']} | {s['sex']} | "
            f"{s['condition']:.0f}% | {s['stamina']:.0f}% | +{s['consistency']} | "
            f"{s['total_works']} | {dsl} | {s['track']} | {s['phase']} |"
        )
    lines.append("")
    lines.append("### Pedigree Reference")
    lines.append("| Horse | Sire | Dam | Color | Height | Weight | Accessories |")
    lines.append("|-------|------|-----|-------|--------|--------|-------------|")
    for s in statuses:
        acc = ", ".join(s["accessories"]) if s["accessories"] else "None"
        lines.append(
            f"| {s['name']} | {s['sire']} | {s['dam']} | {s['color']} | "
            f"{s['height']}h | {s['weight']}lbs | {acc} |"
        )
    lines.append("")
    lines.append(f"---\n*Generated {today_s} by 17_build_2yo_dashboard.py*")

    (REPORTS / "2YO_Dashboard.md").write_text("\n".join(lines), encoding="utf-8")

    # ── Write reports/2YO_Weekly_Plan.md ──
    wlines = [
        f"# 2YO Weekly Plan -- {today_s}",
        "",
        "## Philosophy",
        "- Keep all 2YOs in Training Mode",
        "- Timed works ONLY when BOTH condition AND stamina are 95-105%",
        "- Use standardized baseline template for clean science (no variable changes)",
        "- Work every 3 days (WRRWRR cycle) to build consistency",
        "- 3f baselines first, then step up to 5f after 3 clean baselines",
        "",
        "## Baseline Work Template",
        f"- Distance: {BASELINE_WORK['distance']} | Surface: {BASELINE_WORK['surface']}",
        f"- Effort: {BASELINE_WORK['effort']} | Start: {BASELINE_WORK['start']}",
        f"- Pace: {BASELINE_WORK['pace']} | Weight: {BASELINE_WORK['weight']}",
        f"- Accessories: {BASELINE_WORK['accessories']} | Meds: {BASELINE_WORK['medications']}",
        "",
        "## 7-Day Schedule",
        "",
    ]

    # Build 7-day plan per horse
    days = [today + timedelta(days=i) for i in range(7)]
    day_labels = [d.strftime("%a %d") for d in days]

    header = "| Horse | Tag | " + " | ".join(day_labels) + " |"
    sep = "|-------|-----|" + "|".join(["-----"] * 7) + "|"
    wlines.append(header)
    wlines.append(sep)

    for s in statuses:
        row_days = []
        # Determine work days based on days_since_last_work
        dsl = s["days_since_last_work"]
        if dsl is None:
            # Never worked -- first work today if meters OK
            next_work_offset = 0 if s["meters_ok"] else -1
        else:
            # Next work = 3 - (dsl % 3) days from now (maintain WRRWRR)
            remainder = dsl % 3
            next_work_offset = (3 - remainder) % 3

        for di in range(7):
            if not s["meters_ok"] and di == 0:
                row_days.append("REST")
            elif next_work_offset >= 0 and (di - next_work_offset) % 3 == 0 and di >= next_work_offset:
                work_type = "3f" if s["total_works"] < 3 else "5f"
                row_days.append(work_type)
            else:
                row_days.append("--")

        wlines.append(f"| {s['name']} | {s['tag']} | " + " | ".join(row_days) + " |")

    wlines.append("")
    wlines.append("## Per-Horse Notes")
    wlines.append("")
    for s in statuses:
        notes = []
        if s["total_works"] == 0:
            notes.append("Needs first 3f baseline work")
        if not s["meters_ok"]:
            notes.append(f"Meters out of range (C:{s['condition']:.0f}% S:{s['stamina']:.0f}%) -- wait")
        if s["consistency"] >= 5:
            notes.append("Race-ready consistency -- scout MSW races")
        if s["accessories"]:
            notes.append(f"Has: {', '.join(s['accessories'])}")
        if notes:
            wlines.append(f"- **{s['name']}**: {'; '.join(notes)}")

    wlines.append("")
    wlines.append(f"---\n*Generated {today_s} by 17_build_2yo_dashboard.py*")

    (REPORTS / "2YO_Weekly_Plan.md").write_text("\n".join(wlines), encoding="utf-8")

    print(f"Done: {len(statuses)} 2YOs processed")
    print(f"  -> {status_out}")
    print(f"  -> {REPORTS / '2YO_Dashboard.md'}")
    print(f"  -> {REPORTS / '2YO_Weekly_Plan.md'}")


if __name__ == "__main__":
    main()
