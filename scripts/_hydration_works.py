import csv

rows = sorted(
    [r for r in csv.DictReader(open(r"c:\hrp-ops\outputs\model\dataset_works.csv"))
     if r["horse_name"] == "Hydration"],
    key=lambda r: r["date"], reverse=True
)
print(f"Hydration: {len(rows)} total works\n")
print(f"{'Date':12s} {'Track':7s} {'Dist':5s} {'Surf':5s} {'Time':8s} {'Rank':5s}")
print("-" * 50)
for r in rows:
    print(f"{r['date']:12s} {r['track']:7s} {r['distance']:5s} {r['surface']:5s} {r['time']:8s} {r['rank']:5s}")
