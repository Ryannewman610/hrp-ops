"""18_2yo_experiment_scheduler.py -- Structured 2YO experiment plan.

Reads outputs/2yo_status.json and produces reports/2YO_Experiment_Plan.md
with phased experiments: baseline -> instruction mapping -> adds mapping.

Phases:
  A: Identical baseline works (10-14 day spacing, meters 95-105/95-105)
  B: Instruction mapping (Lead/Stalk/Close patterns)
  C: Adds mapping (one add at a time: blinkers, shadow roll, lasix, bute)

Hard rule: NO timed work unless Condition AND Stamina are both 95-105%.
"""

import json
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"

# Phase A: Baseline template -- identical every time
BASELINE = {
    "distance": "3f",
    "surface": "Dirt",
    "effort": "Breezing",
    "start": "Conservative",
    "pace": "Horse Lead",
    "weight": "120",
    "accessories": "None",
    "medications": "None",
}

# Phase B: Instruction variations to test
INSTRUCTIONS = [
    {"label": "B1-Lead",   "start": "Aggressive",   "pace": "Horse Lead",     "effort": "Handily"},
    {"label": "B2-Stalk",  "start": "Normal",        "pace": "Push",           "effort": "Handily"},
    {"label": "B3-CloseA", "start": "Conservative",  "pace": "Restrain",       "effort": "Handily"},
    {"label": "B4-CloseB", "start": "Conservative",  "pace": "Heavy Restrain", "effort": "Handily"},
]

# Phase C: Adds to test (one at a time, using best instruction from B)
ADDS = [
    {"label": "C1-Blinkers",    "accessory": "Blinkers",     "medication": "None"},
    {"label": "C2-ShadowRoll",  "accessory": "Shadow Roll",  "medication": "None"},
    {"label": "C3-Lasix",       "accessory": "None",         "medication": "Lasix"},
    {"label": "C4-Bute",        "accessory": "None",         "medication": "Bute"},
]

WORK_SPACING_DAYS = 12  # 10-14 day target, use 12 as default


def determine_phase(horse):
    """Determine which phase a horse is in based on work count."""
    tw = horse.get("total_works", 0)
    accessories = horse.get("accessories", [])
    consist = horse.get("consistency", 0)

    if tw < 3:
        return "A", f"Baseline {tw}/3"
    elif tw < 7:
        return "B", f"Instruction mapping ({tw - 3}/4)"
    elif tw < 11:
        return "C", f"Adds mapping ({tw - 7}/4)"
    elif consist >= 5:
        return "DONE", "Race-ready -- find MSW"
    else:
        return "MAINTAIN", f"Continue 5f maintenance (+{consist} con)"


def next_experiment(horse):
    """Return the next experiment to run for this horse."""
    tw = horse.get("total_works", 0)
    phase, desc = determine_phase(horse)

    if phase == "A":
        idx = tw  # 0, 1, 2
        return {
            "phase": "A",
            "label": f"A{idx + 1}-Baseline",
            "distance": BASELINE["distance"],
            "surface": BASELINE["surface"],
            "effort": BASELINE["effort"],
            "start": BASELINE["start"],
            "pace": BASELINE["pace"],
            "accessories": BASELINE["accessories"],
            "medications": BASELINE["medications"],
        }
    elif phase == "B":
        idx = min(tw - 3, len(INSTRUCTIONS) - 1)
        instr = INSTRUCTIONS[idx]
        return {
            "phase": "B",
            "label": instr["label"],
            "distance": "5f",
            "surface": "Dirt",
            "effort": instr["effort"],
            "start": instr["start"],
            "pace": instr["pace"],
            "accessories": "None",
            "medications": "None",
        }
    elif phase == "C":
        idx = min(tw - 7, len(ADDS) - 1)
        add = ADDS[idx]
        return {
            "phase": "C",
            "label": add["label"],
            "distance": "5f",
            "surface": "Dirt",
            "effort": "Handily",
            "start": "Normal",
            "pace": "Horse Lead",
            "accessories": add["accessory"],
            "medications": add["medication"],
        }
    else:
        return {
            "phase": phase,
            "label": "Maintenance",
            "distance": "5f",
            "surface": "Dirt",
            "effort": "Breezing",
            "start": "Normal",
            "pace": "Horse Lead",
            "accessories": "Best from C",
            "medications": "Best from C",
        }


def main():
    status_path = OUTPUTS / "2yo_status.json"
    if not status_path.exists():
        print("ERROR: outputs/2yo_status.json not found. Run 17_build_2yo_dashboard.py first.")
        return

    data = json.loads(status_path.read_text(encoding="utf-8"))
    horses = data.get("horses", [])
    today = date.today()
    today_s = today.isoformat()

    lines = [
        f"# 2YO Experiment Plan -- {today_s}",
        "",
        "## Hard Rules",
        "- NO timed work unless Condition 95-105% AND Stamina 95-105%",
        "- Minimum 10-14 days between works for clean data",
        "- Change ONE variable at a time between experiments",
        "- Record all times for comparison",
        "",
        "## Phase Overview",
        "",
        "| Phase | Purpose | Works | Template |",
        "|-------|---------|-------|----------|",
        "| A | Baseline speed | 3x identical 3f | Conservative / Horse Lead / Breezing |",
        "| B | Instruction mapping | 4x varied 5f | Lead / Stalk / Close A / Close B |",
        "| C | Adds mapping | 4x varied 5f | Blinkers / Shadow Roll / Lasix / Bute |",
        "| DONE | Race-ready | Maintenance | Best combo from B+C |",
        "",
        "---",
        "",
        "## Current Status Per Horse",
        "",
        "| Horse | Sex | Works | Phase | Next Experiment | Meters OK? |",
        "|-------|-----|-------|-------|-----------------|------------|",
    ]

    experiments = []
    for h in horses:
        phase, desc = determine_phase(h)
        nxt = next_experiment(h)
        meters_ok = h.get("meters_ok", False)
        ok_str = "YES" if meters_ok else "NO"

        lines.append(
            f"| {h['name']} | {h['sex']} | {h['total_works']} | "
            f"{phase} ({desc}) | {nxt['label']} | {ok_str} |"
        )
        experiments.append({"horse": h, "next": nxt, "meters_ok": meters_ok})

    lines.append("")

    # Scheduled experiments
    lines.append("## Scheduled Next Experiments")
    lines.append("")

    ready = [e for e in experiments if e["meters_ok"]]
    not_ready = [e for e in experiments if not e["meters_ok"]]

    if ready:
        lines.append("### Ready to Work (meters 95-105%)")
        lines.append("")
        for e in ready:
            h = e["horse"]
            n = e["next"]
            dsl = h.get("days_since_last_work")
            dsl_str = f"{dsl}d ago" if dsl is not None else "never"
            can_work = dsl is None or dsl >= 10

            status = "EXECUTE" if can_work else f"WAIT ({10 - dsl}d)"

            lines.append(f"#### {h['name']} -- {n['label']} [{status}]")
            lines.append(f"- Last work: {dsl_str}")
            lines.append(f"- Distance: {n['distance']} | Surface: {n['surface']}")
            lines.append(f"- Start: {n['start']} | Pace: {n['pace']} | Effort: {n['effort']}")
            lines.append(f"- Accessories: {n['accessories']} | Meds: {n['medications']}")
            lines.append("")

    if not_ready:
        lines.append("### NOT Ready (meters out of range)")
        lines.append("")
        for e in not_ready:
            h = e["horse"]
            lines.append(
                f"- **{h['name']}**: Cond {h['condition']:.0f}% / Stam {h['stamina']:.0f}% -- wait for 95-105%"
            )
        lines.append("")

    # Timeline
    lines.append("## Projected Timeline")
    lines.append("")
    lines.append("| Horse | Phase A Done | Phase B Done | Phase C Done | Race-Ready |")
    lines.append("|-------|-------------|-------------|-------------|------------|")

    for e in experiments:
        h = e["horse"]
        tw = h["total_works"]
        remaining_a = max(0, 3 - tw)
        remaining_b = max(0, 7 - max(tw, 3))
        remaining_c = max(0, 11 - max(tw, 7))
        total_remaining = remaining_a + remaining_b + remaining_c

        base = today
        a_done = base + timedelta(days=remaining_a * WORK_SPACING_DAYS)
        b_done = a_done + timedelta(days=remaining_b * WORK_SPACING_DAYS)
        c_done = b_done + timedelta(days=remaining_c * WORK_SPACING_DAYS)

        lines.append(
            f"| {h['name']} | {a_done.isoformat()} | {b_done.isoformat()} | "
            f"{c_done.isoformat()} | ~{c_done.isoformat()} |"
        )

    lines.append("")
    lines.append(f"---\n*Generated {today_s} by 18_2yo_experiment_scheduler.py*")

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "2YO_Experiment_Plan.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out} ({len(horses)} horses)")


if __name__ == "__main__":
    main()
