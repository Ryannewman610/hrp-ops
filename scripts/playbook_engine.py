"""playbook_engine.py — HRP Playbook Simulation Engine.

Models ALL fitness influencers from official HRP mechanics:
- Nightly maintenance (condition decay by age, stamina recovery)
- Standard & heavy training (farm only, 6 variants)
- Timed works (track only, breezing & handily, 5 distances each)
- Racing stamina drain (by distance)
- Training mode (farm: C & S move toward 100)
- Consistency tracking (2-4 works+races in 30 days = UP)
"""

from itertools import combinations

# ── Action Effects Table ─────────────────────────────────
# Midpoint values from docs/mechanics/official_rules_reference.md

# Training actions (available at ALL locations)
TRAIN_ACTIONS = {
    "TRAIN_STD":       {"cond": 12.0, "stam": -10.0, "label": "Std Training"},
    "TRAIN_STD_SHORT": {"cond": 12.0, "stam": -9.0,  "label": "Std-Short"},
    "TRAIN_STD_LONG":  {"cond": 12.0, "stam": -11.0, "label": "Std-Long"},
    "TRAIN_HVY":       {"cond": 18.0, "stam": -30.0, "label": "Hvy Training"},
    "TRAIN_HVY_SHORT": {"cond": 18.0, "stam": -27.0, "label": "Hvy-Short"},
    "TRAIN_HVY_LONG":  {"cond": 18.0, "stam": -33.0, "label": "Hvy-Long"},
}

# Work actions (timed works at TRACKS)
WORK_ACTIONS = {
    "WORK_3F_B": {"cond": 10.5, "stam": -21.5, "label": "3f Breeze"},
    "WORK_4F_B": {"cond": 11.0, "stam": -23.5, "label": "4f Breeze"},
    "WORK_5F_B": {"cond": 12.0, "stam": -25.5, "label": "5f Breeze"},
    "WORK_6F_B": {"cond": 12.5, "stam": -27.5, "label": "6f Breeze"},
    "WORK_1M_B": {"cond": 14.0, "stam": -31.5, "label": "1m Breeze"},
    "WORK_3F_H": {"cond": 11.0, "stam": -24.5, "label": "3f Handily"},
    "WORK_4F_H": {"cond": 11.5, "stam": -26.5, "label": "4f Handily"},
    "WORK_5F_H": {"cond": 12.5, "stam": -28.5, "label": "5f Handily"},
    "WORK_6F_H": {"cond": 13.0, "stam": -30.5, "label": "6f Handily"},
    "WORK_1M_H": {"cond": 14.5, "stam": -34.5, "label": "1m Handily"},
}

# Race effects (by distance)
RACE_EFFECTS = {
    "RACE_5F":   {"cond": 3.0, "stam": -58.5, "label": "Race 5f"},
    "RACE_6F":   {"cond": 3.0, "stam": -59.5, "label": "Race 6f"},
    "RACE_7F":   {"cond": 3.0, "stam": -60.5, "label": "Race 7f"},
    "RACE_1M":   {"cond": 3.0, "stam": -61.5, "label": "Race 1m"},
    "RACE_9F":   {"cond": 3.0, "stam": -62.5, "label": "Race 1⅛m"},
    "RACE_10F":  {"cond": 3.0, "stam": -63.5, "label": "Race 1¼m"},
}

# Combined lookup
ALL_ACTIONS = {**TRAIN_ACTIONS, **WORK_ACTIONS, **RACE_EFFECTS}

REST_KEY = "REST"

CAP = 110.0

# Known farm abbreviations in HRP track field
FARM_INDICATORS = {"Mou", "Farm", "FRM", "farm", "(FM)"}


# ── Helpers ──────────────────────────────────────────────

def decay_for_age(age_str):
    """Nightly condition decay midpoint by age."""
    try:
        age = int(str(age_str).replace("yo", ""))
    except (ValueError, TypeError):
        age = 3
    if age <= 1:
        return 5.5   # 1yo: 1-10, mid 5.5
    elif age <= 2:
        return 4.5   # 2yo: 1-8, mid 4.5
    elif age == 3:
        return 3.5   # 3yo: 1-6, mid 3.5
    else:
        return 2.5   # 4+:  1-4, mid 2.5


STAM_RECOVERY = 10.0  # nightly stamina gain (midpoint 6-14)


def is_farm(track_str):
    """Determine if a location is a farm (training available) vs track (works)."""
    if not track_str:
        return False
    for indicator in FARM_INDICATORS:
        if indicator in track_str:
            return True
    return False


def get_candidate_actions(track_str):
    """Return list of action keys available at this location.

    Training (std/hvy) is available everywhere.
    Timed works are available at tracks.
    At farms, only training; at tracks, both training and works.
    Training MODE (C&S→100) is farm-only but handled separately.
    """
    if is_farm(track_str):
        # At farm: training only (no timed works available)
        return ["TRAIN_STD", "TRAIN_HVY"]
    else:
        # At track: training + timed works
        return ["TRAIN_STD", "TRAIN_HVY",
                "WORK_3F_B", "WORK_4F_B", "WORK_5F_B", "WORK_5F_H"]


# ── Simulation Engine ───────────────────────────────────

def simulate(c_now, s_now, decay, days, action_schedule):
    """Forward-simulate day-by-day with a given action schedule.

    Args:
        c_now: Current condition %
        s_now: Current stamina %
        decay: Nightly condition decay for this horse's age
        days: Total days to simulate
        action_schedule: dict mapping day_index -> action_key from ALL_ACTIONS

    Returns:
        (final_cond, final_stam) rounded to 1 decimal
    """
    c, s = float(c_now), float(s_now)
    for d in range(days):
        action_key = action_schedule.get(d)
        if action_key and action_key in ALL_ACTIONS:
            fx = ALL_ACTIONS[action_key]
            c += fx["cond"]
            s += fx["stam"]
        # Nightly maintenance
        c -= decay
        s += STAM_RECOVERY
        c = max(0.0, min(CAP, c))
        s = max(0.0, min(CAP, s))
    return round(c, 1), round(s, 1)


def simulate_daily(c_now, s_now, decay, days, action_schedule):
    """Like simulate() but returns per-day snapshots.

    Returns list of dicts with day, action_key, action_label, proj_cond, proj_stam.
    """
    c, s = float(c_now), float(s_now)
    daily = []
    for d in range(days):
        action_key = action_schedule.get(d, REST_KEY)
        label = "Rest"
        if action_key in ALL_ACTIONS:
            fx = ALL_ACTIONS[action_key]
            c += fx["cond"]
            s += fx["stam"]
            label = fx["label"]
        # Nightly maintenance
        c -= decay
        s += STAM_RECOVERY
        c = max(0.0, min(CAP, c))
        s = max(0.0, min(CAP, s))
        daily.append({
            "day": d,
            "action": action_key,
            "action_label": label,
            "proj_cond": round(c, 1),
            "proj_stam": round(s, 1),
        })
    return daily


def score_outcome(fc, fs):
    """Score a projected final condition & stamina. Higher = better."""
    in_range_c = 95 <= fc <= 105
    in_range_s = 95 <= fs <= 105
    score = -(abs(fc - 100) + abs(fs - 100))
    if in_range_c:
        score += 20
    if in_range_s:
        score += 20
    if fc < 75 or fs < 75:
        score -= 50  # auto-scratch territory
    return score


def find_optimal_schedule(c_now, s_now, decay, days_to_race, track_str):
    """Find the best daily action schedule to arrive at 95-105 C & S.

    Evaluates multiple action types based on location (farm vs track),
    tries 0-4 active days with evenly-spaced placement + shifts.

    Returns:
        (action_schedule, proj_cond, proj_stam)
        action_schedule is a dict mapping day_index -> action_key
    """
    if days_to_race <= 0:
        return {}, c_now, s_now

    candidates = get_candidate_actions(track_str)

    best_schedule = {}
    best_c, best_s = simulate(c_now, s_now, decay, days_to_race, {})
    best_score = score_outcome(best_c, best_s)

    max_works = min(4, days_to_race)

    for action_key in candidates:
        for n_works in range(1, max_works + 1):
            # Space works evenly, last work at least 1 day before race
            available = max(1, days_to_race - 1)
            spacing = max(1, available // (n_works + 1))
            work_days = set()
            for w in range(n_works):
                day = spacing * (w + 1) - 1
                if day < days_to_race:
                    work_days.add(day)

            schedule = {d: action_key for d in work_days}
            fc, fs = simulate(c_now, s_now, decay, days_to_race, schedule)
            sc = score_outcome(fc, fs)
            if sc > best_score:
                best_score = sc
                best_schedule = dict(schedule)
                best_c, best_s = fc, fs

            # Try shifted variants
            for shift in [-1, 1]:
                shifted = set(
                    max(0, min(days_to_race - 1, d + shift))
                    for d in work_days
                )
                schedule_s = {d: action_key for d in shifted}
                fc, fs = simulate(c_now, s_now, decay, days_to_race, schedule_s)
                sc = score_outcome(fc, fs)
                if sc > best_score:
                    best_score = sc
                    best_schedule = dict(schedule_s)
                    best_c, best_s = fc, fs

    return best_schedule, best_c, best_s


def assess_consistency(works_count_30d, planned_works):
    """Assess consistency direction based on 30-day work+race count.

    Args:
        works_count_30d: works + races in last 30 days (from snapshot)
        planned_works: number of works in the planned schedule

    Returns:
        (total_count, note_str)
    """
    total = works_count_30d + planned_works
    if 2 <= total <= 4:
        return total, "✅ good"
    elif total < 2:
        return total, "⬆️ add work"
    elif total == 5:
        return total, "➡️ no change"
    else:
        return total, "⚠️ too many"
