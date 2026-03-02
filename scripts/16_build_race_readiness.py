"""16_build_race_readiness.py -- Build race readiness report from stable snapshot.

Finds the latest stable_snapshot.json, evaluates each horse's fitness
for upcoming races, and writes reports/race_readiness.md with concise tables.
"""

import json
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "inputs"
REPORTS = ROOT / "reports"


def find_latest_snapshot():
    """Find newest stable_snapshot.json by modified time."""
    candidates = sorted(
        INPUTS.rglob("stable_snapshot.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def parse_pct(val):
    """Parse '105%' -> 105.0"""
    try:
        return float(str(val).replace("%", "").strip())
    except (ValueError, TypeError):
        return 0.0


def parse_int(val):
    try:
        return int(str(val).replace("+", "").strip())
    except (ValueError, TypeError):
        return 0


def classify(h):
    """Return (status_emoji, status_label, notes) for a horse."""
    cond = parse_pct(h.get("condition", "100%"))
    stam = parse_pct(h.get("stamina", "100%"))
    consist = parse_int(h.get("consistency", "0"))
    starts = parse_int(h.get("record", {}).get("starts", 0))
    wins = parse_int(h.get("record", {}).get("wins", 0))
    works = h.get("works_count", 0)
    noms = h.get("nominations", [])
    has_nom = any(
        n.get("field", "") != "No nominations." for n in noms
    )

    notes = []

    # Race readiness thresholds
    if stam < 50:
        status, label = "[CRIT]", "Exhausted"
        notes.append(f"Stam {stam:.0f}%")
    elif stam < 70:
        status, label = "[LOW]", "Low Stamina"
        notes.append(f"Stam {stam:.0f}%")
    elif cond < 95:
        status, label = "[WARN]", "Low Condition"
        notes.append(f"Cond {cond:.0f}%")
    elif consist < 3 and starts == 0:
        status, label = "[DEV]", "Developing"
        notes.append(f"Con +{consist}")
    elif consist >= 5 and cond >= 100 and stam >= 90:
        status, label = "[GO]", "Race Ready"
    elif consist >= 3:
        status, label = "[FIT]", "Fit"
    else:
        status, label = "[OK]", "Maintaining"

    if has_nom:
        notes.insert(0, "NOMINATED")

    return status, label, cond, stam, consist, starts, wins, works, ", ".join(notes)


def main():
    snap_path = find_latest_snapshot()
    if not snap_path:
        print("ERROR: No stable_snapshot.json found.")
        return

    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    horses = snap.get("horses", [])
    snap_date = snap_path.parent.name
    today = date.today().isoformat()

    # Classify all horses
    rows = []
    for h in horses:
        status, label, cond, stam, consist, starts, wins, works, notes = classify(h)
        rows.append({
            "name": h.get("name", "?"),
            "age": h.get("age", "?"),
            "sex": h.get("sex", "?"),
            "status": status,
            "label": label,
            "cond": cond,
            "stam": stam,
            "consist": consist,
            "record": f"{starts}-{wins}",
            "works": works,
            "notes": notes,
        })

    # Sort: race-ready first, then by condition desc
    priority = {"[GO]": 0, "[FIT]": 1, "[OK]": 2, "[DEV]": 3, "[WARN]": 4, "[LOW]": 5, "[CRIT]": 6}
    rows.sort(key=lambda r: (priority.get(r["status"], 9), -r["cond"]))

    # Separate by group
    race_ready = [r for r in rows if r["status"] in ("[GO]", "[FIT]")]
    developing = [r for r in rows if r["status"] == "[DEV]"]
    maintaining = [r for r in rows if r["status"] == "[OK]"]
    at_risk = [r for r in rows if r["status"] in ("[WARN]", "[LOW]", "[CRIT]")]

    # Build report
    lines = [
        f"# Race Readiness Report -- {today}",
        f"Snapshot: `{snap_date}` | Horses: {len(rows)}",
        "",
    ]

    def table(group, title):
        if not group:
            return
        lines.append(f"## {title} ({len(group)})")
        lines.append("")
        lines.append("| Status | Horse | Age | Sex | Cond | Stam | +Con | Record | Works | Notes |")
        lines.append("|--------|-------|-----|-----|------|------|------|--------|-------|-------|")
        for r in group:
            lines.append(
                f"| {r['status']} | {r['name']} | {r['age']} | {r['sex']} | "
                f"{r['cond']:.0f}% | {r['stam']:.0f}% | +{r['consist']} | "
                f"{r['record']} | {r['works']} | {r['notes']} |"
            )
        lines.append("")

    table(race_ready, "Race Ready")
    table(developing, "Developing")
    table(maintaining, "Maintaining")
    table(at_risk, "At Risk")

    # Summary
    lines.append("---")
    lines.append(f"*Generated {today} by 16_build_race_readiness.py*")

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "race_readiness.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out} ({len(rows)} horses)")


if __name__ == "__main__":
    main()
