"""recommend_actions.py — Generate race recommendations + approval queue.

Inputs:  inputs/YYYY-MM-DD/stable_snapshot.json + global pages
Outputs: reports/Race_Opportunities.md
         outputs/approval_queue.json
         Adds "Today's Top 10 Actions" to Stable_Dashboard.md
"""

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
OUTPUTS = ROOT / "outputs"


def load_snapshot() -> Dict[str, Any]:
    today = date.today().isoformat()
    snap_path = ROOT / "inputs" / today / "stable_snapshot.json"
    if not snap_path.exists():
        # Try most recent
        dirs = sorted((ROOT / "inputs").glob("20*-*-*"), reverse=True)
        for d in dirs:
            sp = d / "stable_snapshot.json"
            if sp.exists():
                snap_path = sp
                break
    return json.loads(snap_path.read_text(encoding="utf-8"))


def classify_horse(h: Dict) -> Dict[str, Any]:
    """Classify a horse's readiness and recommend an action.

    Incorporates knowledge from SimRacingForm guides (Maximum Cool, La Canada, Stu):
    - Career ladder: maiden claimer → claimer → starter allowance → allowance → stakes
    - SB condition loophole: SB wins don't count toward NW conditions
    - Overracing wall: 4+ races in 60 days without works = performance collapse
    - High > low rule: 106% beats 94% every time
    """
    stam_str = h.get("stamina", "100%").replace("%", "")
    cond_str = h.get("condition", "100%").replace("%", "")
    try:
        stam = int(stam_str) if stam_str.isdigit() else 100
    except ValueError:
        stam = 100
    try:
        cond = int(cond_str) if cond_str.isdigit() else 100
    except ValueError:
        cond = 100

    consist_str = h.get("consistency", "0")
    try:
        consist = int(consist_str.replace("+", "")) if consist_str else 0
    except ValueError:
        consist = 0

    record = h.get("record", {})
    starts = int(record.get("starts", 0))
    wins = int(record.get("wins", 0))
    noms = h.get("nominations", [])
    races = h.get("recent_races", [])
    age_str = h.get("age", "3")
    state = h.get("state", "")

    # Classification
    info: Dict[str, Any] = {
        "name": h["name"],
        "stamina": stam,
        "condition": cond,
        "consistency": consist,
        "starts": starts,
        "wins": wins,
        "nominated": len(noms) > 0,
        "nom_count": len(noms),
        "nominations": noms,
        "recent_races": races[:3],
    }

    # ── Race placement tier (Stu's career ladder) ──
    if wins == 0:
        info["placement_tier"] = "maiden"
        info["suggested_race_types"] = ["MSW", "maiden_claimer"]
        info["placement_note"] = "Try MSW first; if 3+ losses consider maiden claimer (easier)"
    elif wins <= 2:
        info["placement_tier"] = "conditioned"
        info["suggested_race_types"] = ["NW1_allowance", "starter_allowance", "claimer"]
        info["placement_note"] = "NW1/starter allowances ideal; protect NW conditions"
    elif wins <= 5:
        info["placement_tier"] = "allowance"
        info["suggested_race_types"] = ["NW2_allowance", "allowance_claiming", "starter_allowance"]
        info["placement_note"] = "Watch NW condition usage carefully"
    else:
        info["placement_tier"] = "stakes_eligible"
        info["suggested_race_types"] = ["stakes", "open_allowance", "handicap"]
        info["placement_note"] = "Stakes-level or open company"

    # SB awareness
    if state:
        info["sb_eligible"] = True
        info["sb_note"] = f"Check {state} state-bred races first (SB wins don't burn NW conditions)"
    else:
        info["sb_eligible"] = False

    # ── Overracing check ──
    race_count_60d = len([r for r in races[:6] if r])  # approximate from recent races
    if race_count_60d >= 4:
        info["overracing_warning"] = True
        info["action"] = "rest"
        info["reason"] = f"Overracing risk: {race_count_60d} recent races. Works needed between races."
        info["priority"] = 0
        return info

    # ── Determine recommendation ──
    if stam < 70:
        info["action"] = "rest"
        info["reason"] = f"Stamina critically low ({stam}%). Rest to recover."
        info["priority"] = 1
    elif stam < 85:
        info["action"] = "work"
        info["reason"] = f"Stamina low ({stam}%). Light works to rebuild."
        info["priority"] = 2
    elif len(noms) > 0:
        info["action"] = "race_ready"
        info["reason"] = f"Nominated ({len(noms)} race(s)). Set jockey + review."
        info["priority"] = 3
    elif cond >= 95 and stam >= 95 and consist >= 3:
        # High > low: slightly above 105 is fine
        info["action"] = "enter_race"
        info["reason"] = f"In peak form (C:{cond}/S:{stam}/+{consist}). Find best race — check SB first!"
        info["priority"] = 4
    elif starts == 0:
        info["action"] = "work"
        info["reason"] = "Unraced — needs timed works + accessory testing."
        info["priority"] = 5
    else:
        info["action"] = "enter_race"
        info["reason"] = "Good condition — filter races: SB/bonus → race type → track."
        info["priority"] = 6

    return info


def build_race_opportunities(horses: List[Dict]) -> str:
    """Generate Race_Opportunities.md content."""
    today = date.today().isoformat()
    lines = [
        f"# 🏁 Race Opportunities",
        f"> **Generated:** {today}",
        "",
    ]

    # Group by action
    rest = [h for h in horses if h["action"] == "rest"]
    work = [h for h in horses if h["action"] == "work"]
    nominated = [h for h in horses if h["action"] == "race_ready"]
    ready = [h for h in horses if h["action"] == "enter_race"]

    if nominated:
        lines.append("## ✅ Already Nominated — Review & Set Jockey")
        lines.append("| Horse | Nominations | Stamina | Cond |")
        lines.append("|-------|-------------|---------|------|")
        for h in nominated:
            nom_details = "; ".join(
                f"{n.get('date','?')} {n.get('track','?')} {n.get('distance','?')}"
                for n in h["nominations"]
            )
            lines.append(
                f"| {h['name']} | {nom_details} | {h['stamina']}% | {h['condition']}% |"
            )
        lines.append("")

    if ready:
        lines.append("## 🎯 Ready to Enter — Find Race (Approval Required)")
        lines.append("| Horse | Stamina | Cond | Consist | Record | Reason |")
        lines.append("|-------|---------|------|---------|--------|--------|")
        for h in sorted(ready, key=lambda x: x["priority"]):
            rec = f"{h['wins']}W from {h['starts']}S" if h["starts"] > 0 else "Unraced"
            lines.append(
                f"| {h['name']} | {h['stamina']}% | {h['condition']}% | "
                f"+{h['consistency']} | {rec} | {h['reason']} |"
            )
        lines.append("")

    if work:
        lines.append("## 🏋️ Needs Work/Training")
        lines.append("| Horse | Stamina | Cond | Reason |")
        lines.append("|-------|---------|------|--------|")
        for h in work:
            lines.append(
                f"| {h['name']} | {h['stamina']}% | {h['condition']}% | {h['reason']} |"
            )
        lines.append("")

    if rest:
        lines.append("## 🛏️ Rest Required")
        lines.append("| Horse | Stamina | Cond | Reason |")
        lines.append("|-------|---------|------|--------|")
        for h in rest:
            lines.append(
                f"| {h['name']} | {h['stamina']}% | {h['condition']}% | {h['reason']} |"
            )
        lines.append("")

    lines.append("---")
    lines.append(f"*Auto-generated by `recommend_actions.py` on {today}*")
    return "\n".join(lines) + "\n"


def build_approval_queue(horses: List[Dict]) -> List[Dict]:
    """Build approval_queue.json entries."""
    queue: List[Dict] = []
    for h in sorted(horses, key=lambda x: x["priority"]):
        entry = {
            "horse": h["name"],
            "action": h["action"],
            "reason": h["reason"],
            "stamina": h["stamina"],
            "condition": h["condition"],
            "consistency": h.get("consistency", 0),
            "placement_tier": h.get("placement_tier", "unknown"),
            "suggested_race_types": h.get("suggested_race_types", []),
            "placement_note": h.get("placement_note", ""),
            "sb_eligible": h.get("sb_eligible", False),
            "sb_note": h.get("sb_note", ""),
            "approval_required": h["action"] in ("enter_race", "race_ready"),
            "timestamp": datetime.now().isoformat(),
        }
        if h.get("overracing_warning"):
            entry["overracing_warning"] = True
        if h.get("nominations"):
            entry["nominations"] = h["nominations"]
        if h.get("recent_races"):
            entry["recent_form"] = [
                f"{r.get('finish','?')}/{r.get('field','?')} {r.get('date','?')} {r.get('track','?')}"
                for r in h["recent_races"]
            ]
        queue.append(entry)
    return queue


def build_top10_block(horses: List[Dict]) -> str:
    """Generate a Top 10 Actions block for the dashboard."""
    lines = ["## 🎬 Today's Top 10 Actions", ""]
    sorted_h = sorted(horses, key=lambda x: x["priority"])[:10]
    for i, h in enumerate(sorted_h, 1):
        icon = {"rest": "🛏️", "work": "🏋️", "race_ready": "✅", "enter_race": "🎯"}.get(
            h["action"], "❓"
        )
        approval = " ⚠️ **APPROVAL**" if h["action"] in ("enter_race", "race_ready") else ""
        lines.append(f"{i}. {icon} **{h['name']}** — {h['reason']}{approval}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    snap = load_snapshot()
    horses = [classify_horse(h) for h in snap.get("horses", [])]

    # Write Race_Opportunities.md
    opp_content = build_race_opportunities(horses)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "Race_Opportunities.md").write_text(opp_content, encoding="utf-8")
    print(f"Written: reports/Race_Opportunities.md")

    # Write approval_queue.json
    queue = build_approval_queue(horses)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "approval_queue.json").write_text(
        json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Written: outputs/approval_queue.json ({len(queue)} entries)")

    # Update Stable_Dashboard.md with Top 10 block
    dash_path = REPORTS / "Stable_Dashboard.md"
    if dash_path.exists():
        dash = dash_path.read_text(encoding="utf-8")
        top10 = build_top10_block(horses)
        # Insert after "## Quick Stats" section or at end
        if "## 🎬 Today" in dash:
            # Replace existing block
            dash = re.sub(
                r"## 🎬 Today.*?(?=## |\Z)", top10 + "\n", dash, flags=re.DOTALL
            )
        elif "## Roster" in dash:
            dash = dash.replace("## Roster", top10 + "\n## Roster")
        else:
            dash += "\n" + top10
        dash_path.write_text(dash, encoding="utf-8")
        print("Updated: reports/Stable_Dashboard.md with Top 10 Actions")

    # Summary
    actions = {}
    for h in horses:
        actions[h["action"]] = actions.get(h["action"], 0) + 1
    print(f"\nAction summary:")
    for action, count in sorted(actions.items()):
        print(f"  {action}: {count}")
    approvals = sum(1 for h in horses if h["action"] in ("enter_race", "race_ready"))
    print(f"  needing approval: {approvals}")


if __name__ == "__main__":
    main()
