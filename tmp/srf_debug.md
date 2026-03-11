=== SRF in stable_snapshot.json ===
Races with SRF: 105
Races without SRF: 3

Sample races with SRF values:
  Captain Cook: 8Mar26 2/5 SRF=87
  Cayuga Lake: 7Feb26 4/5 SRF=88
  Class A: 7Mar26 6/1 SRF=78
  Core N Light: 6Mar26 8/5 SRF=73
  Cornswaggled: 28Feb26 3/1 SRF=89
  Crowds Ransom: 4Feb26 9/7 SRF=39
  Crypto King: 20Feb26 7/8 SRF=92
  Euclidean: 26Feb26 1/1 SRF=92
  Hardline Anvil: 7Mar26 8/3 SRF=68
  Harsh Frontier: 3Mar26 4/5 SRF=95
  Ideal Sinissippi: 7Mar26 1/2 SRF=90
  Iron Timekeeper: 5Mar26 7/4 SRF=73
  Kingston Quickstep: 17Jan26 5/6 SRF=61
  Lo And Behold: 27Feb26 3/2 SRF=81
  Sassy Astray: 4Mar26 6/6 SRF=67
  Strike King: 4Mar26 4/6 SRF=88
  Thats Some Bullship: 21Feb26 4/1 SRF=85
  Trieste Ruler: 7Mar26 7/5 SRF=83
  Urshalim Craftwork: 17Jan26 6/3 SRF=40

=== horse_ratings.json ===
Horses: 68
  American Shorthair: srf=None, elo=None, keys=['srf_power', 'srf_avg', 'srf_best', 'srf_last', 'srf_trend', 'srf_races', 'elo_rating', 'win_pct', 'top3_pct', 'ev_score']
  Basic Math: srf=None, elo=None, keys=['srf_power', 'srf_avg', 'srf_best', 'srf_last', 'srf_trend', 'srf_races', 'elo_rating', 'win_pct', 'top3_pct', 'ev_score']
  Blank Sunset: srf=None, elo=None, keys=['srf_power', 'srf_avg', 'srf_best', 'srf_last', 'srf_trend', 'srf_races', 'elo_rating', 'win_pct', 'top3_pct', 'ev_score']
  Breath Of The Grayte: srf=None, elo=None, keys=['srf_power', 'srf_avg', 'srf_best', 'srf_last', 'srf_trend', 'srf_races', 'elo_rating', 'win_pct', 'top3_pct', 'ev_score']
  Captain Cook: srf=None, elo=None, keys=['srf_power', 'srf_avg', 'srf_best', 'srf_last', 'srf_trend', 'srf_races', 'elo_rating', 'win_pct', 'top3_pct', 'ev_score']
Horses with non-zero SRF (first 5 checked): 0

=== Dashboard SRF display ===
  dashboard.py L179: # SRF
  dashboard.py L180: "srf_power": rating_info.get("srf_power", 0),
  dashboard.py L181: "srf_best": rating_info.get("srf_best"),
  dashboard.py L182: "srf_last": rating_info.get("srf_last"),
  dashboard.py L183: "srf_avg": rating_info.get("srf_avg"),
  dashboard.py L265: "srf_power": rating.get("srf_power", 0),
  dashboard.py L266: "srf_avg": rating.get("srf_avg", 0),
  dashboard.py L267: "srf_best": rating.get("srf_best", 0),
  dashboard.py L268: "srf_last": rating.get("srf_last", 0),
  dashboard.py L269: "srf_trend": rating.get("srf_trend", ""),
  dashboard.py L270: "srf_races": rating.get("srf_races", 0),
  dashboard.py L298: "horses": sorted(horses, key=lambda x: -x["srf_power"]),
  dashboard.py L311: if m.get("srf_power", 0) > 0:
  dashboard.py L313: ranked.sort(key=lambda x: -x["srf_power"])
  dashboard.py L384: "srf_power": rating.get("srf_power", 0),
  dashboard.py L541: "srf_power": rat.get("srf_power", 0),
  dashboard.py L773: "srf_power": rat.get("srf_power", 0),
  dashboard.py L855: "srf_power": rat.get("srf_power", 0),
  dashboard.py L1062: SRF Power: {ri.get('srf_power', 'N/A')} | SRF Best: {ri.get('srf_best', 'N/A')} | SRF Last: {ri.get(
  dashboard.py L1103: ctx += f"- {name} ({h.get('age','?')}yo {h.get('sex','?')}) Cond:{h.get('condition','?')}% Stam:{h.g
  dashboard.py L1170: === SRF (Speed Rating) TIERS ===
  dashboard.py L1176: - N/A = Not yet raced, SRF unknown
  dashboard.py L1193: - A horse with no SRF has never raced — evaluate ONLY from works data and conformation.