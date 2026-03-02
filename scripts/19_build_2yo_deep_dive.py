"""19_build_2yo_deep_dive.py -- Detailed per-horse 2YO analysis.

Reads latest snapshot + works features + hardcoded conformation data
from live pulls. Writes reports/2YO_Deep_Dive.md with detailed analysis.
"""

import json
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "inputs"
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"

# Conformation data from live browser pull (2026-03-02)
CONFORMATION = {
    "Blank Sunset": {
        "lumbo": "Ideal", "stifles": "Mid", "rear": "Hip to Stifle Longest",
        "back_sound": "Ideal", "humerus": "Medium-Long", "hum_angle": "Medium",
        "front_sound": "Very Good", "forehand": "Light-Average",
    },
    "Drinkers Drought": {
        "lumbo": "Ideal", "stifles": "Mid", "rear": "Femur Shortest",
        "back_sound": "Very Good", "humerus": "Medium", "hum_angle": "High",
        "front_sound": "Very Good", "forehand": "Light-Average",
    },
    "Favorite Indian": {
        "lumbo": "Ideal", "stifles": "Mid", "rear": "Ilium Shortest",
        "back_sound": "Good", "humerus": "Medium-Long", "hum_angle": "High-Medium",
        "front_sound": "Ideal", "forehand": "Average",
    },
    "Film The Scene": {
        "lumbo": "Very Good", "stifles": "Mid-Low", "rear": "Hip to Stifle Longest",
        "back_sound": "Ideal", "humerus": "Medium", "hum_angle": "Medium",
        "front_sound": "Ideal", "forehand": "Light-Average",
    },
    "Gen Xpress": {
        "lumbo": "Ideal", "stifles": "Mid-Low", "rear": "Hip to Stifle Longest",
        "back_sound": "Average", "humerus": "Long", "hum_angle": "High-Medium",
        "front_sound": "Very Good", "forehand": "Average",
    },
    "Hi How Are Ya": {
        "lumbo": "Very Good", "stifles": "Mid", "rear": "Balanced",
        "back_sound": "Very Good", "humerus": "Medium", "hum_angle": "High-Medium",
        "front_sound": "Very Good", "forehand": "Light-Average",
    },
    "Looks Like Nicholas": {
        "lumbo": "Very Good", "stifles": "Mid-Low", "rear": "Balanced",
        "back_sound": "Ideal", "humerus": "Medium", "hum_angle": "Medium",
        "front_sound": "Very Good", "forehand": "Light-Average",
    },
    "Neon Reflection": {
        "lumbo": "Very Good", "stifles": "High-Mid", "rear": "Hip to Stifle Shortest",
        "back_sound": "Very Good", "humerus": "Short-Medium", "hum_angle": "Medium",
        "front_sound": "Ideal", "forehand": "Light-Average",
    },
    "Scarlet Smoke": {
        "lumbo": "Very Good", "stifles": "Mid", "rear": "Femur Shortest",
        "back_sound": "Good", "humerus": "Medium", "hum_angle": "High-Medium",
        "front_sound": "Very Good", "forehand": "Light-Average",
    },
}

# Work times from live browser pull (2026-03-02)
WORK_TIMES = {
    "Blank Sunset": [
        {"date": "26Feb26", "dist": "5f", "time": "1:03", "effort": "b"},
        {"date": "16Feb26", "dist": "5f", "time": "1:05.1", "effort": "b"},
    ],
    "Drinkers Drought": [
        {"date": "28Feb26", "dist": "3f", "time": ":37.1", "effort": "b"},
    ],
    "Favorite Indian": [
        {"date": "28Feb26", "dist": "3f", "time": ":37.2", "effort": "b"},
    ],
    "Film The Scene": [
        {"date": "26Feb26", "dist": "5f", "time": "1:02.1", "effort": "b"},
        {"date": "12Feb26", "dist": "5f", "time": "1:02.1", "effort": "b"},
        {"date": "07Feb26", "dist": "5f", "time": "1:02.3", "effort": "b"},
    ],
    "Gen Xpress": [
        {"date": "26Feb26", "dist": "5f", "time": "1:04", "effort": "b"},
        {"date": "19Feb26", "dist": "5f", "time": "1:06.3", "effort": "b"},
    ],
    "Hi How Are Ya": [
        {"date": "28Feb26", "dist": "3f", "time": ":37.2", "effort": "b"},
    ],
    "Looks Like Nicholas": [
        {"date": "26Feb26", "dist": "5f", "time": "1:01.2", "effort": "b"},
        {"date": "12Feb26", "dist": "5f", "time": "1:01.4", "effort": "b"},
        {"date": "08Feb26", "dist": "5f", "time": "1:01.3", "effort": "b"},
    ],
    "Neon Reflection": [
        {"date": "26Feb26", "dist": "5f", "time": "1:01.3", "effort": "b"},
        {"date": "12Feb26", "dist": "5f", "time": "1:01.3", "effort": "b"},
        {"date": "07Feb26", "dist": "5f", "time": "1:05.2", "effort": "b"},
    ],
    "Scarlet Smoke": [
        {"date": "27Feb26", "dist": "3f", "time": ":36.2", "effort": "b"},
    ],
}


def find_latest_snapshot():
    candidates = sorted(INPUTS.rglob("stable_snapshot.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def pct(val):
    try: return float(str(val).replace("%", "").strip())
    except: return 0.0


def pint(val):
    try: return int(str(val).replace("+", "").strip())
    except: return 0


def stifle_hypothesis(stifles):
    """Convert stifle position to distance hypothesis."""
    m = {"High": "Sprint (5f-6f)", "High-Mid": "Sprint-Mile (5f-7f)",
         "Mid": "Versatile (6f-1m)", "Mid-Low": "Route (7f-1m+)",
         "Low": "Deep Route (1m+)"}
    return m.get(stifles, "Unknown")


def confo_score(c):
    """Simple conformation quality score 0-100."""
    ratings = {"Ideal": 100, "Very Good": 80, "Good": 60, "Average": 40, "Poor": 20}
    keys = ["lumbo", "back_sound", "front_sound"]
    vals = [ratings.get(c.get(k, "Average"), 40) for k in keys]
    return sum(vals) / len(vals)


def speed_tier(times):
    """Classify 5f speed tier."""
    fives = [t for t in times if t["dist"] == "5f"]
    if not fives:
        return "Untested", None
    best = min(fives, key=lambda t: t["time"])
    t = best["time"]
    if t <= "1:01.5":
        return "Elite", t
    elif t <= "1:02.5":
        return "Strong", t
    elif t <= "1:04.0":
        return "Developing", t
    else:
        return "Needs Work", t


def baseline_tier(times):
    """Classify 3f baseline tier."""
    threes = [t for t in times if t["dist"] == "3f"]
    if not threes:
        return "Untested", None
    best = min(threes, key=lambda t: t["time"])
    t = best["time"]
    if t <= ":35.0":
        return "Top Tier", t
    elif t <= ":36.0":
        return "Above Average", t
    elif t <= ":36.5":
        return "Stakes Range", t
    else:
        return "Average", t


def analyze_horse(name, snap_data, confo, times):
    """Generate detailed analysis for a single horse."""
    cond = pct(snap_data.get("condition", "100%"))
    stam = pct(snap_data.get("stamina", "100%"))
    consist = pint(snap_data.get("consistency", "0"))
    sex = snap_data.get("sex", "?")
    sire = snap_data.get("sire", "?")
    dam = snap_data.get("dam", "?")
    color = snap_data.get("color", "?")
    weight = snap_data.get("weight", "?")
    height = snap_data.get("height", "?")
    track = snap_data.get("track", "?")
    accessories = snap_data.get("accessories", [])
    works_count = snap_data.get("works_count", 0)

    stifles = confo.get("stifles", "Mid") if confo else "Unknown"
    dist_hyp = stifle_hypothesis(stifles)
    cs = confo_score(confo) if confo else 0
    st, best_5f = speed_tier(times) if times else ("Untested", None)
    bt, best_3f = baseline_tier(times) if times else ("Untested", None)

    meters_ok = 95 <= cond <= 105 and 95 <= stam <= 105

    # Determine phase
    tw = len(times) if times else 0
    if tw < 3:
        phase = f"Phase A: Baseline ({tw}/3 done)"
        next_work = "3f Dirt Breezing Conservative/Horse Lead"
    elif tw < 7:
        phase = f"Phase B: Instruction mapping ({tw-3}/4 done)"
        next_work = "5f Dirt Handily -- test Lead/Stalk/Close"
    elif tw < 11:
        phase = f"Phase C: Adds mapping ({tw-7}/4 done)"
        next_work = "5f Dirt -- test blinkers/shadow roll/lasix/bute"
    elif consist >= 5:
        phase = "Race-Ready"
        next_work = "Find MSW race"
    else:
        phase = "Maintenance"
        next_work = "5f Dirt Breezing maintenance"

    # Build strengths
    strengths = []
    if confo:
        if confo.get("lumbo") == "Ideal":
            strengths.append("Ideal lumbosacral -- maximum power transfer")
        elif confo.get("lumbo") == "Very Good":
            strengths.append("Very Good lumbosacral -- strong athletic base")
        if confo.get("front_sound") == "Ideal":
            strengths.append("Ideal front leg soundness -- durable career ahead")
        if confo.get("back_sound") == "Ideal":
            strengths.append("Ideal back leg soundness -- handles high training loads")
    if st == "Elite":
        strengths.append(f"Elite 5f speed ({best_5f}) -- top of the class")
    elif st == "Strong":
        strengths.append(f"Strong 5f speed ({best_5f}) -- competitive level")
    if bt in ("Top Tier", "Above Average"):
        strengths.append(f"{bt} 3f baseline ({best_3f}) -- natural speed")
    if consist >= 5:
        strengths.append(f"+{consist} consistency -- race ready")
    if sex in ("f",) and sire == "Comanche":
        strengths.append("Comanche filly -- breeding value if she races well")
    if not strengths:
        strengths.append("Still in early development -- potential unknown")
    strengths = strengths[:3]

    # Build concerns
    concerns = []
    if confo:
        if confo.get("back_sound") == "Average":
            concerns.append("Average back leg soundness -- injury risk under heavy training")
        elif confo.get("back_sound") == "Good":
            concerns.append("Good (not Ideal) back leg soundness -- monitor under load")
        if confo.get("humerus") in ("Long",):
            concerns.append("Long humerus -- may be slow out of the gate")
        if confo.get("humerus") in ("Short-Medium",):
            concerns.append("Short-Medium humerus -- limited stride extension")
    if tw == 0:
        concerns.append("Zero timed works -- completely untested")
    elif tw == 1:
        concerns.append("Only 1 work -- too early for conclusions")
    if not meters_ok:
        concerns.append(f"Meters out of range (C:{cond:.0f}%/S:{stam:.0f}%) -- can't work today")
    if consist == 0 and tw > 0:
        concerns.append("Zero consistency -- not building fitness yet")
    if st == "Needs Work":
        concerns.append(f"Slow 5f time ({best_5f}) -- behind the class")
    if not concerns:
        concerns.append("No major red flags identified")
    concerns = concerns[:3]

    # Unknowns
    unknowns = []
    if not any(t["dist"] == "5f" for t in (times or [])):
        unknowns.append("No 5f works yet -- true distance aptitude unknown")
    unknowns.append("Surface preference (dirt vs turf) -- not tested yet")
    if not accessories:
        unknowns.append("Equipment response (blinkers/shadow roll) -- not tested")
    else:
        unknowns.append("Medication response (lasix/bute) -- not fully tested")
    unknowns = unknowns[:2]

    # 14-day plan
    plan = []
    plan.append("Day 1-2: Check meters -- only proceed if C and S both 95-105%")
    if tw < 3:
        plan.append(f"Day 3: Timed work -- 3f Dirt Breezing (baseline {tw+1}/3)")
        plan.append("Day 4-13: Rest/train, rebuild stamina")
        plan.append(f"Day 14: Timed work -- 3f Dirt Breezing (baseline {min(tw+2,3)}/3)")
    elif tw < 7:
        plan.append("Day 3: Timed work -- 5f Dirt Handily (instruction test)")
        plan.append("Day 4-13: Rest/train, rebuild stamina")
        plan.append("Day 14: Timed work -- 5f Dirt Handily (next instruction)")
    else:
        plan.append("Day 3: Timed work -- 5f Dirt with equipment/med test")
        plan.append("Day 4-13: Rest/train, rebuild stamina")
        plan.append("Day 14: Timed work -- 5f with next add variation")

    return {
        "name": name, "sex": sex, "color": color, "sire": sire, "dam": dam,
        "height": height, "weight": weight, "track": track,
        "cond": cond, "stam": stam, "consist": consist,
        "stifles": stifles, "dist_hyp": dist_hyp,
        "confo_score": cs, "speed_tier": st, "best_5f": best_5f,
        "baseline_tier": bt, "best_3f": best_3f,
        "phase": phase, "next_work": next_work, "meters_ok": meters_ok,
        "strengths": strengths, "concerns": concerns, "unknowns": unknowns,
        "plan": plan, "works": times or [], "tw": tw,
        "accessories": accessories,
    }


def tier_horse(h):
    """Assign S/A/B/C tier."""
    score = 0
    if h["speed_tier"] == "Elite": score += 40
    elif h["speed_tier"] == "Strong": score += 30
    elif h["speed_tier"] == "Developing": score += 15
    score += h["confo_score"] * 0.3
    if h["consist"] >= 5: score += 15
    elif h["consist"] >= 3: score += 8
    score += h["tw"] * 2

    if score >= 55: return "S"
    elif score >= 40: return "A"
    elif score >= 25: return "B"
    else: return "C"


def main():
    snap_path = find_latest_snapshot()
    if not snap_path:
        print("ERROR: No stable_snapshot.json found.")
        return

    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    all_horses = snap.get("horses", [])
    twoyos = [h for h in all_horses if str(h.get("age", "")) == "2"]
    snap_date = snap_path.parent.name
    today = date.today().isoformat()

    # Analyze each horse
    analyses = []
    for h in twoyos:
        name = h.get("name", "?")
        confo = CONFORMATION.get(name)
        times = WORK_TIMES.get(name, [])
        a = analyze_horse(name, h, confo, times)
        a["tier"] = tier_horse(a)
        analyses.append(a)

    # Sort by tier then speed
    tier_order = {"S": 0, "A": 1, "B": 2, "C": 3}
    analyses.sort(key=lambda a: (tier_order.get(a["tier"], 9), -a["confo_score"]))

    # Build report
    L = []
    L.append(f"# 2YO Deep Dive -- {today}")
    L.append(f"Snapshot: `{snap_date}` | 2-year-olds: {len(analyses)}")
    L.append("")

    # Stable-wide ranking
    L.append("## Stable-Wide 2YO Ranking")
    L.append("")
    L.append("| Tier | Horse | Speed | Confo | Stifles | Why |")
    L.append("|------|-------|-------|-------|---------|-----|")
    for a in analyses:
        spd = f"{a['best_5f'] or a['best_3f'] or 'N/A'}"
        reason = []
        if a["speed_tier"] == "Elite": reason.append("fastest in class")
        elif a["speed_tier"] == "Strong": reason.append("strong speed")
        if a["confo_score"] >= 85: reason.append("elite confo")
        elif a["confo_score"] >= 70: reason.append("solid confo")
        if a["consist"] >= 5: reason.append("race-ready")
        if not reason: reason.append("early development")
        L.append(f"| **{a['tier']}** | {a['name']} | {spd} | {a['confo_score']:.0f} | {a['stifles']} | {', '.join(reason)} |")
    L.append("")

    # Superlatives
    by_speed = sorted([a for a in analyses if a["best_5f"]], key=lambda a: a["best_5f"])
    sprinters = [a for a in analyses if a["stifles"] in ("High-Mid", "High")]
    routers = [a for a in analyses if a["stifles"] in ("Mid-Low", "Low")]

    L.append("### Superlatives")
    if by_speed:
        L.append(f"- **Most likely stakes-type**: {by_speed[0]['name']} ({by_speed[0]['best_5f']} 5f, +{by_speed[0]['consist']} con)")
    if sprinters:
        L.append(f"- **Best sprinter profile**: {sprinters[0]['name']} ({sprinters[0]['stifles']} stifles)")
    if routers:
        L.append(f"- **Best router profile**: {routers[0]['name']} ({routers[0]['stifles']} stifles)")
    early = [a for a in analyses if a["tw"] <= 1]
    if early:
        L.append(f"- **Needs time**: {', '.join(a['name'] for a in early)} (1 or fewer works)")
    L.append("")

    # Detailed per-horse sections
    L.append("---")
    L.append("")
    for a in analyses:
        sex_label = {"c": "Colt", "f": "Filly"}.get(a["sex"], a["sex"])
        L.append(f"## {a['name']}")
        L.append(f"**{a['color']} {sex_label}** | {a['sire']} x {a['dam']} | "
                 f"{a['height']}h / {a['weight']}lbs | Track: {a['track']}")
        L.append("")

        # Summary line
        L.append(f"> **{a['dist_hyp']}** -- {a['speed_tier']} speed -- "
                 f"{a['phase']} -- Next: {a['next_work']}")
        L.append("")

        # Meters
        ok = "YES" if a["meters_ok"] else "NO"
        L.append(f"**Meters**: Cond {a['cond']:.0f}% | Stam {a['stam']:.0f}% | "
                 f"+{a['consist']} con | Work-eligible: {ok}")
        L.append("")

        # Conformation
        confo = CONFORMATION.get(a["name"])
        if confo:
            L.append(f"**Conformation** (score {a['confo_score']:.0f}/100): "
                     f"Lumbo: {confo['lumbo']} | Stifles: {confo['stifles']} | "
                     f"Rear: {confo['rear']} | "
                     f"Back: {confo['back_sound']} | Front: {confo['front_sound']} | "
                     f"Humerus: {confo['humerus']} ({confo['hum_angle']})")
            L.append("")

        # Works
        if a["works"]:
            L.append("**Works**:")
            for w in a["works"]:
                L.append(f"- {w['date']} {w['dist']} fst {w['time']}{w['effort']}")
            L.append("")

        if a["accessories"]:
            L.append(f"**Equipment**: {', '.join(a['accessories'])}")
            L.append("")

        # Strengths
        L.append("### Strengths")
        for s in a["strengths"]:
            L.append(f"- {s}")
        L.append("")

        # Concerns
        L.append("### Concerns")
        for c in a["concerns"]:
            L.append(f"- {c}")
        L.append("")

        # Unknowns
        L.append("### What We Don't Know Yet")
        for u in a["unknowns"]:
            L.append(f"- {u}")
        L.append("")

        # 14-day plan
        L.append("### Next 14-Day Plan")
        for p in a["plan"]:
            L.append(f"- {p}")
        L.append("")
        L.append("---")
        L.append("")

    L.append(f"*Generated {today} by 19_build_2yo_deep_dive.py*")

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "2YO_Deep_Dive.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote {out} ({len(analyses)} horses)")
    return str(snap_path), str(out), True


if __name__ == "__main__":
    result = main()
