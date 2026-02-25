"""compare_snapshots.py — Generate day-over-day change report.

Compares the two most recent stable_snapshot.json files and produces
reports/Overnight_Changes.md showing:
  - Balance change
  - Stamina/condition changes per horse
  - New nominations or entries
  - New race results
  - Horses added/removed
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_snapshots() -> Tuple[Optional[Path], Optional[Path]]:
    """Find the two most recent snapshot files."""
    dirs = sorted((ROOT / "inputs").glob("20*-*-*"), reverse=True)
    snaps: List[Path] = []
    for d in dirs:
        sp = d / "stable_snapshot.json"
        if sp.exists():
            snaps.append(sp)
        if len(snaps) == 2:
            break
    if len(snaps) == 2:
        return snaps[1], snaps[0]  # older, newer
    elif len(snaps) == 1:
        return None, snaps[0]
    return None, None


def safe_int(val: str, default: int = 0) -> int:
    v = str(val).replace("%", "").replace("+", "").strip()
    return int(v) if v.isdigit() else default


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    older_path, newer_path = find_snapshots()

    if not newer_path:
        print("No snapshots found.")
        return

    newer = json.loads(newer_path.read_text(encoding="utf-8"))
    new_date = newer["date"]

    if not older_path:
        print(f"Only one snapshot ({new_date}). Need 2+ days for comparison.")
        return

    older = json.loads(older_path.read_text(encoding="utf-8"))
    old_date = older["date"]

    print(f"Comparing: {old_date} → {new_date}")

    # Build horse lookups
    old_by_norm: Dict[str, Dict] = {norm(h["name"]): h for h in older.get("horses", [])}
    new_by_norm: Dict[str, Dict] = {norm(h["name"]): h for h in newer.get("horses", [])}

    lines = [
        "# 📊 Overnight Changes",
        f"> **{old_date} → {new_date}**",
        "",
    ]

    # Balance change
    old_bal = older.get("balance", "?")
    new_bal = newer.get("balance", "?")
    try:
        bal_diff = float(new_bal) - float(old_bal)
        bal_icon = "📈" if bal_diff > 0 else "📉" if bal_diff < 0 else "➡️"
        lines.append(f"## 💰 Balance: ${old_bal} → ${new_bal} ({bal_icon} ${bal_diff:+.2f})")
    except (ValueError, TypeError):
        lines.append(f"## 💰 Balance: ${old_bal} → ${new_bal}")
    lines.append("")

    # Horses added/removed
    old_names = set(old_by_norm.keys())
    new_names = set(new_by_norm.keys())
    added = new_names - old_names
    removed = old_names - new_names

    if added or removed:
        lines.append("## 🐴 Roster Changes")
        for n in sorted(added):
            h = new_by_norm[n]
            lines.append(f"- ➕ **{h['name']}** added")
        for n in sorted(removed):
            h = old_by_norm[n]
            lines.append(f"- ➖ **{h['name']}** removed")
        lines.append("")

    # Stamina/Condition changes
    changes: List[Dict[str, Any]] = []
    for n in sorted(old_names & new_names):
        old_h = old_by_norm[n]
        new_h = new_by_norm[n]

        old_stam = safe_int(old_h.get("stamina", "100"))
        new_stam = safe_int(new_h.get("stamina", "100"))
        old_cond = safe_int(old_h.get("condition", "100"))
        new_cond = safe_int(new_h.get("condition", "100"))
        old_consist = safe_int(old_h.get("consistency", "0"))
        new_consist = safe_int(new_h.get("consistency", "0"))

        stam_diff = new_stam - old_stam
        cond_diff = new_cond - old_cond
        consist_diff = new_consist - old_consist

        old_starts = int(old_h.get("record", {}).get("starts", 0))
        new_starts = int(new_h.get("record", {}).get("starts", 0))
        raced = new_starts > old_starts

        old_works = int(old_h.get("works_count", 0))
        new_works = int(new_h.get("works_count", 0))
        new_work_count = new_works - old_works

        if stam_diff or cond_diff or consist_diff or raced or new_work_count:
            changes.append({
                "name": new_h["name"],
                "stam_old": old_stam, "stam_new": new_stam, "stam_diff": stam_diff,
                "cond_old": old_cond, "cond_new": new_cond, "cond_diff": cond_diff,
                "consist_diff": consist_diff,
                "raced": raced,
                "new_works": new_work_count,
            })

    if changes:
        lines.append("## 📈 Stamina / Condition Changes")
        lines.append("| Horse | Stamina | Condition | Notes |")
        lines.append("|-------|---------|-----------|-------|")
        for c in sorted(changes, key=lambda x: abs(x["stam_diff"]), reverse=True):
            stam_arrow = f"{c['stam_old']}→{c['stam_new']}%" if c["stam_diff"] else f"{c['stam_new']}%"
            cond_arrow = f"{c['cond_old']}→{c['cond_new']}%" if c["cond_diff"] else f"{c['cond_new']}%"
            notes = []
            if c["stam_diff"] > 0:
                notes.append(f"⬆️ Stam +{c['stam_diff']}")
            elif c["stam_diff"] < 0:
                notes.append(f"⬇️ Stam {c['stam_diff']}")
            if c["cond_diff"]:
                notes.append(f"Cond {c['cond_diff']:+d}")
            if c["consist_diff"]:
                notes.append(f"Consist {c['consist_diff']:+d}")
            if c["raced"]:
                notes.append("🏇 Raced!")
            if c["new_works"]:
                notes.append(f"🏋️ +{c['new_works']} works")
            lines.append(f"| {c['name']} | {stam_arrow} | {cond_arrow} | {'; '.join(notes)} |")
        lines.append("")
    else:
        lines.append("## 📈 No Stamina/Condition Changes Detected")
        lines.append("")

    # Unchanged horses
    unchanged = len(old_names & new_names) - len(changes)
    lines.append(f"**Unchanged:** {unchanged} horses with no metric changes")
    lines.append("")

    lines.append("---")
    lines.append(f"*Auto-generated by `compare_snapshots.py` — {old_date} vs {new_date}*")

    report = "\n".join(lines) + "\n"
    out_path = REPORTS / "Overnight_Changes.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"Written: {out_path} ({len(report)} chars)")
    print(f"  Changes detected: {len(changes)} horses")
    print(f"  Added: {len(added)}, Removed: {len(removed)}")


if __name__ == "__main__":
    main()
