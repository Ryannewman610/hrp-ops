"""Focused diagnostic — dump to file for full analysis."""
import json, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
out = []

# 1. Race Calendar entries
cal = json.load(open(ROOT / "outputs" / "race_calendar_2026-02-25.json", "r", encoding="utf-8"))
out.append(f"CALENDAR: {cal['total_races']} races")
for i, r in enumerate(cal["races"]):
    out.append(f"  [{i}] track={r.get('track','NONE'):10s} date={r.get('date','NONE'):12s} "
               f"cond={r.get('conditions','NONE')[:45]}")

# 2. Field scout
scouts = sorted(glob.glob(str(ROOT / "outputs" / "field_scout_*.json")), reverse=True)
if scouts:
    fs = json.load(open(scouts[0], "r", encoding="utf-8"))
    out.append(f"\nFIELD SCOUT: {fs['total_scouted']} races")
    for r in fs["races"]:
        out.append(f"  field={r.get('field_size')} str={r.get('field_strength_score')} "
                   f"track={r.get('track','?'):6s} cond={r.get('conditions','?')[:35]}")

# 3. Approval_Pack steps lines
ap = ROOT / "reports" / "Approval_Pack.md"
if ap.exists():
    out.append("\nAPPROVAL_PACK STEPS:")
    for line in ap.read_text(encoding="utf-8").split("\n"):
        if "Steps:" in line or "Select" in line:
            out.append(f"  {line.strip()[:120]}")

# 4. Race_Opportunities field column
rp = ROOT / "reports" / "Race_Opportunities.md"
if rp.exists():
    out.append("\nRACE_OPP FIELD COLUMN:")
    for line in rp.read_text(encoding="utf-8").split("\n"):
        if "| 1 " in line or "| 2 " in line or "| 3 " in line:
            out.append(f"  {line.strip()[:130]}")

result = "\n".join(out)
Path(ROOT / "outputs" / "_diag.txt").write_text(result, encoding="utf-8")
print(result)
