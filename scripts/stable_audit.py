"""stable_audit.py — Audit all horses for gelding, statebred, and edge opportunities."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Find latest snapshot
snap_path = sorted(ROOT.glob("inputs/20*-*-*/stable_snapshot.json"), reverse=True)[0]
snap = json.loads(snap_path.read_text(encoding="utf-8"))

print(f"Snapshot: {snap_path.parent.name}")
print(f"Horses: {len(snap.get('horses', []))}")
print(f"Balance: ${snap.get('balance', '?')}")
print()

# Categorize all horses
colts = []
fillies = []
geldings = []
mares = []
unknown_sex = []

for h in sorted(snap.get("horses", []), key=lambda x: x["name"]):
    name = h["name"]
    sex = str(h.get("sex", "")).lower()
    age = h.get("age", "?")
    track = h.get("track", "?")
    sire = h.get("sire", "?")
    bred = h.get("bred_state", "")
    cond = h.get("condition", "?")
    stam = h.get("stamina", "?")
    con = h.get("consistency", "?")
    record = h.get("record", {})
    starts = record.get("starts", 0)
    wins = record.get("wins", 0)

    row = f"  {name:25s} {sex:8s} age:{age:>2s} {track:6s} bred:{bred:>5s} " \
          f"sire:{str(sire)[:18]:18s} {starts}st-{wins}w cond:{cond} stam:{stam} +{con}"
    print(row)

    if "colt" in sex or sex == "c":
        colts.append(h)
    elif "filly" in sex or sex == "f":
        fillies.append(h)
    elif "gelding" in sex or sex == "g":
        geldings.append(h)
    elif "mare" in sex or sex == "m":
        mares.append(h)
    else:
        unknown_sex.append(h)

print()
print("=" * 60)
print("GELDING ANALYSIS")
print("=" * 60)
print(f"  Colts (ungelded): {len(colts)}")
print(f"  Geldings: {len(geldings)}")
print(f"  Fillies: {len(fillies)}")
print(f"  Mares: {len(mares)}")
print()

if colts:
    print("  Colts that MIGHT benefit from gelding:")
    print("  (Forum intel: colts may never reach full speed without gelding)")
    for h in colts:
        name = h["name"]
        record = h.get("record", {})
        starts = int(record.get("starts", 0))
        wins = int(record.get("wins", 0))
        age = h.get("age", "?")
        # Flag colts with 3+ starts but poor win rate
        if starts >= 3 and wins / starts < 0.2:
            print(f"    ⚠️  {name} (age {age}, {starts}st-{wins}w = {wins/starts*100:.0f}%W) — CONSIDER GELDING")
        elif starts == 0:
            print(f"    🔍 {name} (age {age}, unraced) — evaluate after first works")
        else:
            print(f"    ✅ {name} (age {age}, {starts}st-{wins}w) — performing OK")

print()
print("=" * 60)
print("STATEBRED STATUS")
print("=" * 60)
sb_horses = [h for h in snap.get("horses", []) if h.get("bred_state")]
if sb_horses:
    for h in sb_horses:
        print(f"  {h['name']:25s} bred:{h.get('bred_state','?'):>5s}")
else:
    print("  No bred_state data in snapshot — need to check profiles")
    print("  State-bred horses get 15-30% purse bonuses (NY/CA/FL)")

print()
print("=" * 60)
print("FINANCIAL SNAPSHOT")
print("=" * 60)
balance = snap.get("balance", "unknown")
print(f"  Balance: ${balance}")
total_earnings = sum(float(h.get("record", {}).get("earnings", 0))
                     for h in snap.get("horses", []))
print(f"  Total lifetime earnings: ${total_earnings:.2f}")
horse_count = len(snap.get("horses", []))
print(f"  Horses: {horse_count}")
print(f"  Daily upkeep (est): ${horse_count * 0.10:.2f}/day (${horse_count * 0.10 * 30:.2f}/month)")


if __name__ == "__main__":
    pass
