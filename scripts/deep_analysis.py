"""deep_analysis.py — Mine all race data for hidden patterns and edges.

Analyzes: jockey performance, condition/stamina sweet spots, distance
preferences, track bias, post position effects, SRF trajectories.
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    with open(ROOT / 'outputs' / 'outcomes_log.csv', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    print(f'Total races: {len(rows)}')
    print(f'With finish: {sum(1 for r in rows if r.get("finish_position"))}')
    print(f'With SRF: {sum(1 for r in rows if r.get("srf"))}')
    print(f'With jockey: {sum(1 for r in rows if r.get("jockey"))}')
    print(f'With condition: {sum(1 for r in rows if r.get("race_condition"))}')
    print(f'With post pos: {sum(1 for r in rows if r.get("post_position"))}')
    print()

    # 1. Win rate by horse
    print('=' * 60)
    print('WIN RATE BY HORSE (3+ starts)')
    print('=' * 60)
    by_horse = defaultdict(lambda: {'starts': 0, 'wins': 0, 'top3': 0, 'srfs': [], 'finishes': []})
    for r in rows:
        h = r['horse_name']
        by_horse[h]['starts'] += 1
        fp = r.get('finish_position', '')
        if fp and str(fp).isdigit():
            fpi = int(fp)
            by_horse[h]['finishes'].append(fpi)
            if fpi == 1: by_horse[h]['wins'] += 1
            if fpi <= 3: by_horse[h]['top3'] += 1
        srf = r.get('srf', '')
        if srf and str(srf).isdigit(): by_horse[h]['srfs'].append(int(srf))

    for h in sorted(by_horse, key=lambda x: -by_horse[x]['wins']):
        d = by_horse[h]
        if d['starts'] >= 3:
            avg_srf = f"{sum(d['srfs'])/len(d['srfs']):.0f}" if d['srfs'] else '---'
            avg_fin = f"{sum(d['finishes'])/len(d['finishes']):.1f}" if d['finishes'] else '---'
            print(f"  {h:25s} {d['starts']:2d}st {d['wins']:2d}w {d['top3']:2d}t3 "
                  f"{d['wins']/d['starts']*100:5.1f}%W  avgFin:{avg_fin:>4s}  avgSRF:{avg_srf}")

    # 2. Jockey performance
    print()
    print('=' * 60)
    print('JOCKEY PERFORMANCE (3+ rides)')
    print('=' * 60)
    by_jockey = defaultdict(lambda: {'starts': 0, 'wins': 0, 'top3': 0, 'srfs': [], 'horses': set()})
    for r in rows:
        j = r.get('jockey', '')
        if not j: continue
        by_jockey[j]['starts'] += 1
        by_jockey[j]['horses'].add(r['horse_name'])
        fp = r.get('finish_position', '')
        if fp and str(fp).isdigit():
            if int(fp) == 1: by_jockey[j]['wins'] += 1
            if int(fp) <= 3: by_jockey[j]['top3'] += 1
        srf = r.get('srf', '')
        if srf and str(srf).isdigit(): by_jockey[j]['srfs'].append(int(srf))

    for j in sorted(by_jockey, key=lambda x: -by_jockey[x]['wins']):
        d = by_jockey[j]
        if d['starts'] >= 3:
            avg_srf = f"{sum(d['srfs'])/len(d['srfs']):.1f}" if d['srfs'] else '---'
            horses = ','.join(sorted(d['horses']))[:40]
            print(f"  {j:20s} {d['starts']:2d}st {d['wins']:2d}w {d['top3']:2d}t3 "
                  f"{d['wins']/d['starts']*100:5.1f}%W  avgSRF:{avg_srf:>5s}  [{horses}]")

    # 3. Condition at race time vs finish
    print()
    print('=' * 60)
    print('CONDITION AT RACE TIME vs RESULT')
    print('=' * 60)
    cond_finishes = []
    for r in rows:
        cond = r.get('race_condition', '')
        fp = r.get('finish_position', '')
        if cond and fp and str(cond).isdigit() and str(fp).isdigit():
            cond_finishes.append((int(cond), int(fp)))

    if cond_finishes:
        wins = [c for c, f in cond_finishes if f == 1]
        losses = [c for c, f in cond_finishes if f > 3]
        if wins: print(f'  Avg condition when WIN:   {sum(wins)/len(wins):.1f}%  (n={len(wins)})')
        if losses: print(f'  Avg condition when OFF:   {sum(losses)/len(losses):.1f}%  (n={len(losses)})')
        print()
        for lo, hi in [(85,90), (90,95), (95,100), (100,105), (105,110)]:
            bucket = [(c,f) for c,f in cond_finishes if lo <= c < hi]
            if bucket:
                bw = sum(1 for c,f in bucket if f == 1)
                bt3 = sum(1 for c,f in bucket if f <= 3)
                print(f'  Cond {lo:3d}-{hi:3d}%: {len(bucket):2d} races, '
                      f'{bw:2d}w {bt3:2d}t3 ({bw/len(bucket)*100:4.0f}%W {bt3/len(bucket)*100:4.0f}%T3)')

    # 4. Stamina at race time
    print()
    print('=' * 60)
    print('STAMINA AT RACE TIME vs RESULT')
    print('=' * 60)
    stam_finishes = []
    for r in rows:
        stam = r.get('race_stamina', '')
        fp = r.get('finish_position', '')
        if stam and fp and str(stam).isdigit() and str(fp).isdigit():
            stam_finishes.append((int(stam), int(fp)))

    if stam_finishes:
        wins = [s for s, f in stam_finishes if f == 1]
        if wins: print(f'  Avg stamina when WIN:  {sum(wins)/len(wins):.1f}  (n={len(wins)})')
        for lo, hi in [(0,5), (5,10), (10,15), (15,20), (20,30), (30,50)]:
            bucket = [(s,f) for s,f in stam_finishes if lo <= s < hi]
            if bucket:
                bw = sum(1 for s,f in bucket if f == 1)
                bt3 = sum(1 for s,f in bucket if f <= 3)
                print(f'  Stam {lo:2d}-{hi:2d}: {len(bucket):2d} races, '
                      f'{bw:2d}w {bt3:2d}t3 ({bw/len(bucket)*100:4.0f}%W {bt3/len(bucket)*100:4.0f}%T3)')

    # 5. Track performance
    print()
    print('=' * 60)
    print('TRACK PERFORMANCE')
    print('=' * 60)
    by_track = defaultdict(lambda: {'starts': 0, 'wins': 0, 'top3': 0, 'srfs': []})
    for r in rows:
        t = r.get('track', '')
        if not t: continue
        by_track[t]['starts'] += 1
        fp = r.get('finish_position', '')
        if fp and str(fp).isdigit():
            if int(fp) == 1: by_track[t]['wins'] += 1
            if int(fp) <= 3: by_track[t]['top3'] += 1
        srf = r.get('srf', '')
        if srf and str(srf).isdigit(): by_track[t]['srfs'].append(int(srf))
    for t in sorted(by_track, key=lambda x: -by_track[x]['starts']):
        d = by_track[t]
        avg_srf = f"{sum(d['srfs'])/len(d['srfs']):.1f}" if d['srfs'] else '---'
        print(f"  {t:5s} {d['starts']:2d}st {d['wins']:2d}w {d['top3']:2d}t3  "
              f"{d['wins']/d['starts']*100:5.1f}%W  avgSRF:{avg_srf}")

    # 6. SRF by distance
    print()
    print('=' * 60)
    print('SRF BY DISTANCE')
    print('=' * 60)
    by_dist = defaultdict(lambda: {'srfs': [], 'wins': 0, 'starts': 0})
    for r in rows:
        dist = r.get('distance', '')
        if not dist: continue
        by_dist[dist]['starts'] += 1
        srf = r.get('srf', '')
        if srf and str(srf).isdigit(): by_dist[dist]['srfs'].append(int(srf))
        fp = r.get('finish_position', '')
        if fp and str(fp).isdigit() and int(fp) == 1: by_dist[dist]['wins'] += 1
    for d in sorted(by_dist):
        dd = by_dist[d]
        avg_srf = f"{sum(dd['srfs'])/len(dd['srfs']):.1f}" if dd['srfs'] else '---'
        best = f"{max(dd['srfs'])}" if dd['srfs'] else '---'
        print(f"  {d:12s} {dd['starts']:2d}st {dd['wins']:2d}w  avgSRF:{avg_srf:>5s}  best:{best:>3s}")

    # 7. Per-horse distance preference
    print()
    print('=' * 60)
    print('HORSE DISTANCE PREFERENCE (SRF by distance)')
    print('=' * 60)
    horse_dist = defaultdict(lambda: defaultdict(list))
    for r in rows:
        h = r['horse_name']
        dist = r.get('distance', '')
        srf = r.get('srf', '')
        if dist and srf and str(srf).isdigit():
            horse_dist[h][dist].append(int(srf))
    for h in sorted(horse_dist):
        dists = horse_dist[h]
        if len(dists) >= 2 or any(len(v) >= 2 for v in dists.values()):
            parts = []
            for d in sorted(dists):
                srfs = dists[d]
                parts.append(f"{d}={sum(srfs)/len(srfs):.0f}({len(srfs)})")
            print(f"  {h:25s} {' | '.join(parts)}")

    # 8. Post position analysis
    print()
    print('=' * 60)
    print('POST POSITION vs FINISH')
    print('=' * 60)
    pp_data = []
    for r in rows:
        pp = r.get('post_position', '')
        fp = r.get('finish_position', '')
        if pp and fp and str(pp).isdigit() and str(fp).isdigit():
            pp_data.append((int(pp), int(fp)))
    for pp in sorted(set(p for p,f in pp_data)):
        finishes = [f for p,f in pp_data if p == pp]
        if finishes:
            avg_f = sum(finishes)/len(finishes)
            wins = sum(1 for f in finishes if f == 1)
            t3 = sum(1 for f in finishes if f <= 3)
            print(f'  PP{pp:2d}: {len(finishes):2d} races  avgFinish:{avg_f:4.1f}  {wins}w {t3}t3')

    # 9. Field size analysis
    print()
    print('=' * 60)
    print('FIELD SIZE vs WIN RATE')
    print('=' * 60)
    fs_data = defaultdict(lambda: {'starts': 0, 'wins': 0, 'top3': 0})
    for r in rows:
        fs = r.get('field_size', '')
        fp = r.get('finish_position', '')
        if fs and fp and str(fs).isdigit() and str(fp).isdigit():
            fs_data[int(fs)]['starts'] += 1
            if int(fp) == 1: fs_data[int(fs)]['wins'] += 1
            if int(fp) <= 3: fs_data[int(fs)]['top3'] += 1
    for fs in sorted(fs_data):
        d = fs_data[fs]
        if d['starts'] >= 2:
            print(f"  {fs:2d}-horse: {d['starts']:2d}st {d['wins']:2d}w {d['top3']:2d}t3 "
                  f"{d['wins']/d['starts']*100:5.1f}%W {d['top3']/d['starts']*100:5.1f}%T3")

    # 10. SRF trend per horse (last 3 vs previous)
    print()
    print('=' * 60)
    print('SRF TRAJECTORY (recent vs older)')
    print('=' * 60)
    for h in sorted(by_horse):
        d = by_horse[h]
        srfs = d['srfs']
        if len(srfs) >= 4:
            recent = srfs[:2]
            older = srfs[2:4]
            diff = sum(recent)/len(recent) - sum(older)/len(older)
            arrow = '↑' if diff > 2 else '↓' if diff < -2 else '→'
            print(f"  {h:25s} recent:[{','.join(str(s) for s in recent)}] "
                  f"older:[{','.join(str(s) for s in older)}] "
                  f"diff:{diff:+.1f} {arrow}")

    # Save insights as JSON
    insights = {
        "best_jockeys": [],
        "optimal_condition": None,
        "track_strengths": {},
        "distance_preferences": {},
    }

    # Best jockeys
    for j in sorted(by_jockey, key=lambda x: -by_jockey[x]['wins']):
        d = by_jockey[j]
        if d['starts'] >= 3:
            insights["best_jockeys"].append({
                "jockey": j, "starts": d['starts'], "wins": d['wins'],
                "top3": d['top3'], "win_pct": round(d['wins']/d['starts']*100, 1),
                "avg_srf": round(sum(d['srfs'])/len(d['srfs']), 1) if d['srfs'] else None,
            })

    # Optimal condition
    if cond_finishes:
        wins_cond = [c for c, f in cond_finishes if f == 1]
        insights["optimal_condition"] = {
            "avg_win_condition": round(sum(wins_cond)/len(wins_cond), 1) if wins_cond else None,
            "sample_size": len(cond_finishes),
        }

    # Track results
    for t, d in by_track.items():
        insights["track_strengths"][t] = {
            "starts": d['starts'], "wins": d['wins'], "top3": d['top3'],
            "win_pct": round(d['wins']/d['starts']*100, 1),
        }

    (ROOT / 'outputs' / 'deep_analysis.json').write_text(
        json.dumps(insights, indent=2), encoding='utf-8')
    print(f"\nSaved to outputs/deep_analysis.json")


if __name__ == "__main__":
    main()
