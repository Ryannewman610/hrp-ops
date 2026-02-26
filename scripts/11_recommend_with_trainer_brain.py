"""11_recommend_with_trainer_brain.py — Model-driven race recommendations.

Uses Trainer Brain model + structured race calendar (with field sizes) to produce:
  - reports/Race_Opportunities.md
  - reports/Approval_Pack.md
  - outputs/approval_queue.json
  - outputs/predictions_log_YYYY-MM-DD.json (PHASE 1)
  - outputs/predictions_log.csv (append-only)
  - Updates Stable_Dashboard.md
"""

import csv
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "outputs" / "model"
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"
INACTIVE = {"shebasbriar", "averyspluck", "hiptag793004736512"}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_distance_furlongs(dist: str) -> float:
    dist = dist.strip().lower()
    m = re.match(r"(\d+)\s*(\d+/\d+)?\s*([fm])", dist)
    if not m:
        return 0.0
    whole = int(m.group(1))
    frac = 0.0
    if m.group(2):
        num, den = m.group(2).split("/")
        frac = int(num) / int(den)
    val = whole + frac
    if m.group(3) == "m":
        val *= 8
    return round(val, 2)


def parse_conditions(conditions: str) -> Dict[str, Any]:
    """Extract structured eligibility & weight data from race conditions text.

    HRP conditions strings contain real eligibility gates and weight rules
    that we were previously ignoring (Audit Hole #4).

    Examples parsed:
      'Have won less than 3 races'          -> max_wins: 2
      'Have not won either 4 races other..' -> max_non_maiden_wins: 3
      'Weight 124 lbs'                      -> base_weight: 124
      'Non-winners of a race since ..2 lbs' -> weight_allowances present
      'For Four Year Olds And Upward'       -> min_age: 4
      'For Fillies Three Years Old'         -> sex_restriction: 'f'
    """
    result: Dict[str, Any] = {}
    c = conditions.lower() if conditions else ""

    # --- Wins cap: "Have won less than N races" ---
    m = re.search(r"have won less than (\d+) races?", c)
    if m:
        result["max_wins"] = int(m.group(1)) - 1  # "less than 3" = max 2

    # --- Non-maiden wins cap: "Have not won either N races other than maiden..." ---
    m = re.search(r"have not won (?:either )?(\d+) races? other than", c)
    if m:
        result["max_non_maiden_wins"] = int(m.group(1)) - 1

    # --- Base weight: "Weight 124 lbs" ---
    m = re.search(r"weight (\d+) lbs", c)
    if m:
        result["base_weight"] = int(m.group(1))

    # --- Weight allowances: "Non-winners of a race since DATE N lbs" ---
    allowances = re.findall(
        r"non-winners of a race[^.]*?since\s+[\d/]+\s+(\d+)\s*lbs", c
    )
    if allowances:
        result["weight_allowances"] = [int(a) for a in allowances]

    # --- Age: "For ... Three Year Olds" / "Four Year Olds And Upward" ---
    age_words = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
    m = re.search(r"for[^.]*?(two|three|four|five|six)\s+year", c)
    if m:
        result["min_age"] = age_words.get(m.group(1), 3)
        if "upward" in c:
            result["max_age"] = 99
        else:
            result["max_age"] = result["min_age"]

    # --- Sex restriction ---
    if "fillies and mares" in c or "f&m" in c:
        result["sex_restriction"] = "f_and_m"
    elif "fillies" in c or "filly" in c:
        result["sex_restriction"] = "f"
    elif "colts and geldings" in c:
        result["sex_restriction"] = "c_and_g"

    # --- State-bred bonus ---
    m = re.search(r"plus up to \$(\d+\.?\d*) for (\w+)-breds", c)
    if m:
        result["state_bred_bonus"] = float(m.group(1))
        result["state_bred_state"] = m.group(2).upper()

    return result


def is_real_race(race: Dict) -> bool:
    """With the new block parser, races are already validated.
    Just double-check for obvious issues."""
    if not race.get("date"):
        return False
    if not race.get("track"):
        return False
    # Track must not be "TRACK" or "RACE TYPE"
    if race["track"] in ("TRACK", "RACE TYPE", "RACE"):
        return False
    return True


def score_race_fit(horse_model: Dict, race: Dict,
                   works_feat: Dict = None,
                   abilities: Dict = None) -> Dict:
    """Score how well a race fits a horse, with hard eligibility checks.

    HRP Rules enforced:
      1. Maidens (0 wins) can ONLY enter maiden races (MSW / MCL)
      2. Winners (1+ wins) are INELIGIBLE for maiden races
      3. Condition and stamina must both be >= 75 to race
      4. Timed work within 90 days required (checked separately)
      5. Age/sex restrictions on some races
    Uses horse abilities (speed ratings, surface/distance preferences) for
    differentiated scoring when available.
    """
    score = horse_model["ev_score"]
    reasons = []
    risks = []
    wf = works_feat or {}
    ab = abilities or {}

    # ═══════════════════════════════════════════════
    # HARD ELIGIBILITY CHECKS (instant disqualification)
    # ═══════════════════════════════════════════════
    race_type = race.get("race_type", "").lower()
    conditions = race.get("conditions", "").lower()
    race_class = race_type + " " + conditions

    # CRITICAL: Maiden classification uses ONLY race_type, NOT conditions.
    # The conditions field may contain misleading text like "Non Winners Of A
    # Maiden Claiming Prize" in Allowance races, which is NOT a maiden race.
    is_maiden_race = "maiden" in race_type
    # Explicit override: Allowance is NEVER a maiden race
    if "allowance" in race_type:
        is_maiden_race = False
    is_allowance = "allowance" in race_type
    is_claiming = "claiming" in race_type and not is_maiden_race
    is_stakes = "stakes" in race_type or "handicap" in race_type

    record = horse_model.get("record", {})
    wins = int(record.get("wins", 0))
    is_maiden_horse = wins == 0

    # CHECK 1: Maiden horse in non-maiden race → INELIGIBLE
    if is_maiden_horse and not is_maiden_race:
        return {
            "score": -999,
            "reasons": [],
            "risks": ["🚫 INELIGIBLE: maiden cannot enter non-maiden race"],
            "confidence": "N/A",
            "eligible": False,
        }

    # CHECK 2: Winner in maiden race → INELIGIBLE
    if not is_maiden_horse and is_maiden_race:
        return {
            "score": -999,
            "reasons": [],
            "risks": ["🚫 INELIGIBLE: winner cannot enter maiden race"],
            "confidence": "N/A",
            "eligible": False,
        }

    # CHECK 3: Condition/Stamina gates (HRP: both must be >=75)
    snap_data = horse_model.get("_snap", {})
    cond_raw = snap_data.get("condition", horse_model.get("condition", "100%"))
    stam_raw = snap_data.get("stamina", horse_model.get("stamina", "100%"))
    try:
        cond_val = float(str(cond_raw).replace("%", ""))
    except ValueError:
        cond_val = 100.0
    try:
        stam_val = float(str(stam_raw).replace("%", ""))
    except ValueError:
        stam_val = 100.0

    if stam_val < 75:
        return {
            "score": -999,
            "reasons": [],
            "risks": [f"🚫 INELIGIBLE: stamina {stam_val:.0f}% < 75% threshold"],
            "confidence": "N/A",
            "eligible": False,
        }
    if cond_val < 75:
        return {
            "score": -999,
            "reasons": [],
            "risks": [f"🚫 INELIGIBLE: condition {cond_val:.0f}% < 75% threshold"],
            "confidence": "N/A",
            "eligible": False,
        }

    # CHECK 4: Age restrictions
    horse_age = snap_data.get("age", "")
    race_age = race.get("age_restriction", "").lower() if race.get("age_restriction") else ""
    # Parse age number from "3 Year Olds" or "3+"
    if horse_age and race_age:
        try:
            h_age = int(re.sub(r"[^0-9]", "", str(horse_age))[:1])
        except (ValueError, IndexError):
            h_age = 0
        if "3 year" in race_class and h_age > 3:
            return {
                "score": -999,
                "reasons": [],
                "risks": [f"🚫 INELIGIBLE: age {h_age} in 3YO-only race"],
                "confidence": "N/A",
                "eligible": False,
            }

    # CHECK 5: Sex restrictions
    horse_sex = snap_data.get("sex", "").lower()
    if "fillies" in race_class or "f&m" in race_class or "filly" in race_class:
        if horse_sex and horse_sex not in ("f", "filly", "mare"):
            return {
                "score": -999,
                "reasons": [],
                "risks": ["🚫 INELIGIBLE: fillies/mares only race"],
                "confidence": "N/A",
                "eligible": False,
            }

    # CHECK 6: Wins cap from conditions text (Audit Hole #4)
    cond_parsed = parse_conditions(conditions)
    max_wins = cond_parsed.get("max_wins")
    if max_wins is not None and wins > max_wins:
        return {
            "score": -999,
            "reasons": [],
            "risks": [f"🚫 INELIGIBLE: {wins} wins exceeds cap of {max_wins}"],
            "confidence": "N/A",
            "eligible": False,
        }
    max_nm_wins = cond_parsed.get("max_non_maiden_wins")
    if max_nm_wins is not None:
        # Count non-maiden wins (approximate: total wins for winners)
        nm_wins = wins  # All wins count for non-maiden cap
        if nm_wins > max_nm_wins:
            return {
                "score": -999,
                "reasons": [],
                "risks": [f"🚫 INELIGIBLE: {nm_wins} non-maiden wins exceeds cap of {max_nm_wins}"],
                "confidence": "N/A",
                "eligible": False,
            }

    # CHECK 7: Parsed age from conditions (more precise than race_class text)
    cond_min_age = cond_parsed.get("min_age")
    cond_max_age = cond_parsed.get("max_age", 99)
    if cond_min_age and horse_age:
        try:
            h_age_val = int(re.sub(r"[^0-9]", "", str(horse_age)))
        except (ValueError, IndexError):
            h_age_val = 0
        if h_age_val > 0:
            if h_age_val < cond_min_age:
                return {
                    "score": -999,
                    "reasons": [],
                    "risks": [f"🚫 INELIGIBLE: age {h_age_val} below minimum {cond_min_age}"],
                    "confidence": "N/A",
                    "eligible": False,
                }
            if h_age_val > cond_max_age:
                return {
                    "score": -999,
                    "reasons": [],
                    "risks": [f"🚫 INELIGIBLE: age {h_age_val} above maximum {cond_max_age}"],
                    "confidence": "N/A",
                    "eligible": False,
                }

    # ═══════════════════════════════════════════════
    # SOFT SCORING (for eligible horses only)
    # ═══════════════════════════════════════════════

    # === ABILITY-BASED SCORING ===
    ab_speed = ab.get("best_speed", 0)
    ab_surf = ab.get("preferred_surface", "Dirt")
    ab_dist = ab.get("preferred_distance", "Unknown")
    ab_turf_pct = ab.get("turf_ability", 50)
    ab_wet_pct = ab.get("wet_ability", 50)

    # Speed-based score adjustment with weight adjustment (Audit Hole #1)
    # HRP formula: Adjusted Speed = speed + ((126 - weight_carried) × 0.10)
    base_weight = cond_parsed.get("base_weight", 126)
    adj_speed = ab_speed + ((126 - base_weight) * 0.10) if ab_speed > 0 else 0

    if ab_speed > 0:
        # Use adjusted speed for scoring (accounts for weight)
        speed_adj = (adj_speed - 80) * 1.0
        score += speed_adj
        if adj_speed >= 90:
            reasons.append(f"⚡ AdjSpd {adj_speed:.0f} (raw {ab_speed}, wt {base_weight})")
        elif adj_speed >= 80:
            reasons.append(f"AdjSpd {adj_speed:.0f}")
        elif adj_speed < 70:
            risks.append(f"Slow adj {adj_speed:.0f}")
    else:
        # Unraced maiden — use works count for differentiation
        work_count = ab.get("work_count", 0)
        activity = ab.get("activity_total", 0)
        if work_count >= 3:
            score += 5
            reasons.append(f"📋 {work_count} works (prepared)")
        elif work_count >= 1:
            score += 2
            reasons.append(f"📋 {work_count} works")
        else:
            score -= 3
            risks.append("No timed works yet")

    # Surface match
    race_surface = race.get("surface", "").lower()
    is_turf_race = "turf" in race_surface or "fm" in race_surface
    is_dirt_race = not is_turf_race

    if ab_speed > 0:  # Only apply if horse has actual data
        if is_turf_race:
            if ab_surf == "Turf" or ab_turf_pct >= 95:
                score += 10
                reasons.append("🌿 Turf specialist")
            elif ab_surf == "Both" or ab_turf_pct >= 80:
                score += 4
                reasons.append("Turf OK")
            elif ab_turf_pct < 70:
                score -= 8
                risks.append(f"⚠️ Weak on turf ({ab_turf_pct}%)")
        else:  # Dirt race
            if ab_surf == "Dirt":
                score += 5
                reasons.append("🏜️ Dirt preferred")
            elif ab_surf == "Turf":
                score -= 5
                risks.append("Turf horse on dirt")

    # Wet track check (race conditions)
    track_cond = race.get("track_condition", "").lower()
    if any(w in track_cond for w in ("mud", "slop", "wet", "yield", "soft")):
        if ab_wet_pct >= 85:
            score += 5
            reasons.append(f"💧 Handles wet ({ab_wet_pct}%)")
        elif ab_wet_pct < 70 and ab_speed > 0:
            score -= 8
            risks.append(f"⚠️ Weak in wet ({ab_wet_pct}%)")

    # Class appropriateness
    if is_maiden_race:
        if "special weight" in race_class:
            score += 3
            reasons.append("MSW (no claim risk)")
        elif "claiming" in race_class:
            reasons.append("MCL")
        reasons.append("Maiden eligible")

    if is_allowance:
        if wins >= 2:
            score += 3
            reasons.append(f"Allowance fit ({wins}W)")
        elif wins == 1:
            reasons.append("First allowance try")
            score += 1

    if is_stakes:
        if wins >= 3:
            score += 5
            reasons.append(f"Stakes caliber ({wins}W)")
        elif wins < 2:
            score -= 5
            risks.append("Stakes too ambitious")

    # Track familiarity (Audit Hole #3) & 90-day work check (Audit Hole #2)
    race_track = race.get("track", "")
    horse_current_track = ab.get("current_track", "")
    last_work_by_track = ab.get("last_work_by_track", {})
    work_tracks_set = set(ab.get("work_tracks", []))

    if race_track:
        if race_track == horse_current_track:
            score += 5
            reasons.append(f"🏠 Home track ({race_track})")
        elif race_track in work_tracks_set:
            score += 3
            reasons.append(f"📍 Worked at {race_track}")
        else:
            score -= 3
            risks.append(f"⚠️ New track {race_track} (home: {horse_current_track})")

        # 90-day timed work eligibility warning
        last_work_at_track = last_work_by_track.get(race_track, "")
        if last_work_at_track:
            try:
                from datetime import datetime as _dt
                work_date = _dt.strptime(last_work_at_track, "%m/%d/%Y")
                days_since = (_dt.now() - work_date).days
                if days_since > 90:
                    score -= 10
                    risks.append(f"🚫 Last work at {race_track}: {days_since}d ago (>90d!)")
                elif days_since > 60:
                    score -= 3
                    risks.append(f"⚠️ Last work at {race_track}: {days_since}d ago")
            except (ValueError, TypeError):
                pass
        elif ab.get("work_count", 0) > 0:
            # Has works but none at this track
            risks.append(f"⚠️ No works at {race_track} — may need timed work first")

    # Distance fit (enhanced with ability data)
    dist_text = race.get("distance", "")
    if dist_text:
        dist_f = parse_distance_furlongs(dist_text)
        if dist_f > 0:
            is_sprint = dist_f <= 7
            is_route = dist_f > 7

            # Ability-based distance matching
            if ab_speed > 0 and ab_dist != "Unknown":
                if is_sprint and ab_dist == "Sprint":
                    score += 8
                    reasons.append(f"🏃 Sprint fit ({dist_text})")
                elif is_route and ab_dist == "Route":
                    score += 8
                    reasons.append(f"🏇 Route fit ({dist_text})")
                elif ab_dist == "Both":
                    score += 4
                    reasons.append(f"Versatile ({dist_text})")
                elif is_sprint and ab_dist == "Route":
                    score -= 4
                    risks.append(f"Router in sprint ({dist_text})")
                elif is_route and ab_dist == "Sprint":
                    score -= 4
                    risks.append(f"Sprinter going long ({dist_text})")
            else:
                # Fallback for unraced horses
                consist = horse_model.get("consistency", 0)
                if dist_f <= 6.5:
                    if consist >= 3:
                        score += 5
                        reasons.append(f"Sprint ({dist_text})")
                elif dist_f <= 8.5:
                    reasons.append(f"Mid ({dist_text})")
                    score += 3
                else:
                    reasons.append(f"Route ({dist_text})")

    # Consistency trend warning (Audit Hole #5)
    consistency_trend = ab.get("consistency_trend", "")
    current_consistency = ab.get("consistency", 0)
    days_since_work = ab.get("days_since_last_work", -1)
    if consistency_trend == "-1" and current_consistency > 0:
        score -= 3
        risks.append(f"📉 Consistency dropping ({current_consistency}, {ab.get('recent_activity_7d', 0)} acts/7d)")
    elif consistency_trend == "+1":
        score += 2
        reasons.append(f"📈 Consistency rising ({current_consistency})")
    if days_since_work > 14:
        score -= 2
        risks.append(f"⚠️ Stale ({days_since_work}d since last work)")

    # Shipping cost flag (Audit Hole #7)
    # If race track differs from current track, flag potential stamina hit
    if race_track and horse_current_track and race_track != horse_current_track:
        # Check race deadline vs shipping time
        race_deadline = race.get("deadline", "")
        if race_deadline:
            try:
                from datetime import datetime as _dt2
                dl = _dt2.strptime(race_deadline.split()[0], "%m/%d/%Y")
                days_to_deadline = (dl - _dt2.now()).days
                if days_to_deadline <= 1:
                    risks.append(f"⚠️ Must regular-ship (stamina hit) — deadline {days_to_deadline}d")
                elif days_to_deadline <= 2:
                    reasons.append(f"Slow-ship possible ({days_to_deadline}d to deadline)")
            except (ValueError, TypeError, IndexError):
                pass

    # === FORUM EXPERT INTELLIGENCE ===

    # Statebred ATM strategy: SB races give bonus purse AND don't count toward
    # allowance conditions. Forum experts call this "an ATM machine"
    state_bred_bonus = cond_parsed.get("state_bred_bonus", 0)
    if state_bred_bonus > 0:
        score += 3
        state = cond_parsed.get("state_bred_state", "?")
        reasons.append(f"💰 SB bonus +${state_bred_bonus:.2f} ({state}-bred)")

    # Race frequency: experts say every 4-6 weeks is optimal, 2 weeks is aggressive
    # 10 days rest minimum after a race per forum advice
    last_race_date = ab.get("last_work_date", "")  # Use last event as proxy
    if last_race_date and ab.get("race_count", 0) > 0:
        try:
            from datetime import datetime as _dt3
            lr = _dt3.strptime(last_race_date, "%m/%d/%Y")
            days_since_race = (_dt3.now() - lr).days
            if days_since_race < 10:
                score -= 3
                risks.append(f"⚠️ Too soon ({days_since_race}d since last activity)")
        except (ValueError, TypeError):
            pass

    # Weight advantage for 3-year-olds: conditions give them 2-4 lbs less
    # Forum intel: "The threes turn four and lose the weight advantage"
    if cond_parsed.get("min_age") == 4 or "upward" in conditions.lower():
        # Check if horse is 3 years old — they get weight break
        try:
            h_age_val = int(re.sub(r"[^0-9]", "", str(horse_age)))
            cond_base_wt = cond_parsed.get("base_weight", 126)
            if h_age_val == 3 and cond_base_wt > 120:
                # 3YOs typically carry 2-4 lbs less in "X and upward" races
                score += 2
                reasons.append(f"📊 3YO weight edge vs older")
        except (ValueError, TypeError):
            pass

    # === OFFICIAL HRP RULES INTEGRATION ===

    # Rule: Filly/Mare weight allowance in open (mixed-sex) races
    # Official: females get 3-5 lbs less weight vs males in non-handicap races
    # This is a real competitive edge — lower weight = faster adjusted speed
    if horse_sex in ("f", "filly", "mare"):
        sex_restricted = "fillies" in race_class or "f&m" in race_class or "filly" in race_class
        is_handicap = "handicap" in race_type
        if not sex_restricted and not is_handicap:
            # Open race — filly gets 3-5 lb weight break vs colts
            score += 2
            try:
                h_age_val2 = int(re.sub(r"[^0-9]", "", str(horse_age))[:1])
                wt_break = 5 if (h_age_val2 >= 3 and datetime.now().month < 9) else 3
            except (ValueError, TypeError, IndexError):
                wt_break = 3
            reasons.append(f"♀ Filly weight edge (-{wt_break}lbs vs colts)")

    # Rule: Condition degradation warning
    # Official: "If the condition meter drops below 50 your horse will actually
    # start degrading." — This is a critical health warning.
    if cond_val < 50:
        score -= 10
        risks.append(f"🚨 CONDITION {cond_val:.0f}% < 50 — horse is DEGRADING (Official Rule)")

    # Rule: Optimal meter fitness bonus
    # Official: 95-105 condition and stamina is equivalent/optimal
    if 95 <= cond_val <= 105 and 95 <= stam_val <= 105:
        score += 3
        reasons.append(f"💪 Peak fitness (C:{cond_val:.0f} S:{stam_val:.0f})")

    # Rule: Stamina depletion risk for long races
    # Official race stamina losses: 6f=54-65, 1m=56-67, 1 1/4m=58-69
    # If horse stamina is borderline, longer races are riskier
    if stam_val < 85:
        race_dist = race.get("distance", "")
        dist_f = parse_distance_furlongs(race_dist) if race_dist else 0
        if dist_f >= 8.0:  # 1 mile+
            score -= 3
            risks.append(f"⚠️ Low stamina {stam_val:.0f}% for route ({race_dist})")

    # Form bonus
    cycle = horse_model.get("form_cycle", "")
    if cycle == "PEAKING":
        score += 5
        reasons.append("🔥 PEAKING")
    elif cycle == "READY":
        reasons.append("✅ READY")
    elif cycle == "NEEDS_WORK":
        score -= 5
        risks.append("⚠️ Needs work")
    elif cycle == "REST_REQUIRED":
        score -= 20
        risks.append("🛏️ Rest required")

    # Field size bonus
    field_size = race.get("field_size")
    if field_size is not None:
        if field_size <= 5:
            score += 8
            reasons.append(f"Small field ({field_size})")
        elif field_size <= 7:
            score += 4
            reasons.append(f"Medium field ({field_size})")
        elif field_size >= 10:
            score -= 3
            risks.append(f"Large field ({field_size})")

    # === Works Intelligence Integration ===
    readiness = wf.get("readiness_index", 50)
    sharpness = wf.get("sharpness_index", 50)
    fatigue = wf.get("fatigue_proxy", 30)
    trend = wf.get("work_trend", "unknown")

    if readiness >= 75:
        score += 6
        reasons.append(f"🎯 Ready {readiness}")
    elif readiness >= 55:
        score += 2
    elif readiness < 35:
        score -= 8
        risks.append(f"⚠️ Low readiness {readiness}")

    if fatigue >= 60:
        score -= 5
        risks.append(f"😓 Fatigue {fatigue}")

    if trend == "improving":
        score += 3
        reasons.append("📈 Works improving")
    elif trend == "declining":
        score -= 3
        risks.append("📉 Works declining")

    # Confidence badge
    data_points = sum(1 for k in ["readiness_index", "sharpness_index", "work_trend"]
                      if k in wf)
    if data_points >= 2 and readiness >= 60:
        confidence = "HIGH"
    elif data_points >= 1:
        confidence = "MED"
    else:
        confidence = "LOW"

    return {
        "score": round(score, 1),
        "reasons": reasons,
        "risks": risks,
        "confidence": confidence,
        "eligible": True,
    }


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    # Load model ratings
    ratings_path = MODEL_DIR / "horse_ratings.json"
    if not ratings_path.exists():
        print("ERROR: Run 10_fit_trainer_brain.py first")
        return
    horse_models = json.loads(ratings_path.read_text(encoding="utf-8"))

    # Load race calendar
    cal_path = OUTPUTS / f"race_calendar_{today}.json"
    if not cal_path.exists():
        cals = sorted(OUTPUTS.glob("race_calendar_*.json"), reverse=True)
        if cals:
            cal_path = cals[0]
    races_all = json.loads(cal_path.read_text(encoding="utf-8")).get("races", []) if cal_path.exists() else []

    races = [r for r in races_all if is_real_race(r)]
    print(f"Races: {len(races_all)} total, {len(races)} valid")

    # Load entries from tracker nominations
    entries_path = OUTPUTS / f"upcoming_entries_{today}.json"
    if not entries_path.exists():
        ents = sorted(OUTPUTS.glob("upcoming_entries_*.json"), reverse=True)
        if ents:
            entries_path = ents[0]
    entries = json.loads(entries_path.read_text(encoding="utf-8")).get("entries", []) if entries_path.exists() else []
    entered_norms = {norm(e["horse_name"]) for e in entries
                     if e.get("source") == "tracker_nominations" and e.get("horse_name")}

    # Load snapshot for record data
    snap_path = ROOT / "inputs" / today / "stable_snapshot.json"
    if not snap_path.exists():
        dirs = sorted((ROOT / "inputs").glob("20*-*-*"), reverse=True)
        for d in dirs:
            sp = d / "stable_snapshot.json"
            if sp.exists():
                snap_path = sp
                break
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    snap_by_norm = {norm(h["name"]): h for h in snap.get("horses", [])}

    # Load works features
    wf_path = OUTPUTS / f"works_features_{today}.json"
    if not wf_path.exists():
        wfs = sorted(OUTPUTS.glob("works_features_*.json"), reverse=True)
        if wfs:
            wf_path = wfs[0]
    works_features = json.loads(wf_path.read_text(encoding="utf-8")) if wf_path.exists() else []
    wf_by_norm = {norm(f["horse_name"]): f for f in works_features}
    print(f"Works features loaded: {len(works_features)} horses")

    # Load horse abilities
    ab_path = OUTPUTS / "horse_abilities.json"
    abilities_all = json.loads(ab_path.read_text(encoding="utf-8")) if ab_path.exists() else []
    ab_by_norm = {norm(a["horse_name"]): a for a in abilities_all}
    print(f"Abilities loaded: {len(abilities_all)} horses")

    # Score each horse against each valid race
    recommendations: List[Dict] = []
    eligible_count = 0
    ineligible_count = 0

    for name, model in horse_models.items():
        h_norm = norm(name)
        if h_norm in INACTIVE:
            continue

        snap_h = snap_by_norm.get(h_norm, {})
        model["track"] = snap_h.get("track", "?")
        model["record"] = snap_h.get("record", {})
        model["_snap"] = snap_h  # Pass full snapshot for eligibility checks
        wf = wf_by_norm.get(h_norm, {})
        ab = ab_by_norm.get(h_norm, {})

        already_entered = h_norm in entered_norms

        race_scores = []
        for race in races:
            fit = score_race_fit(model, race, wf, ab)
            # Hard filter: skip ineligible races entirely
            if not fit.get("eligible", True):
                ineligible_count += 1
                continue
            eligible_count += 1
            if fit["score"] > 0:
                entry = {
                    "race": race,
                    "score": fit["score"],
                    "reasons": fit["reasons"],
                    "risks": fit["risks"],
                    "field_size": race.get("field_size"),
                }
                race_scores.append(entry)
        race_scores.sort(key=lambda x: x["score"], reverse=True)
        top3 = race_scores[:3]

        recommendations.append({
            "horse": name,
            "elo": model["elo_rating"],
            "win_pct": model["win_pct"],
            "top3_pct": model["top3_pct"],
            "ev_score": model["ev_score"],
            "form_cycle": model["form_cycle"],
            "next_action": model["next_action"],
            "form_factors": model["form_factors"],
            "stamina": model["stamina"],
            "condition": model["condition"],
            "consistency": model["consistency"],
            "already_entered": already_entered,
            "top_races": top3,
            "track": model["track"],
            "record": model.get("record", {}),
        })

    # ── Generate Race_Opportunities.md ──────────────────

    lines = [
        "# 🏁 Race Opportunities — Trainer Brain v2",
        f"> **Generated:** {today} | **Model:** ELO + Form Cycle | "
        f"**Races:** {len(races)} valid",
        "",
    ]

    # Already entered
    entered = [r for r in recommendations if r["already_entered"]]
    if entered:
        lines.append("## ✅ Already Entered / Nominated")
        lines.append("| Horse | ELO | Win% | Top3% | EV | Form |")
        lines.append("|-------|-----|------|-------|-----|------|")
        for r in sorted(entered, key=lambda x: -x["ev_score"]):
            ci = {"PEAKING": "🔥", "READY": "✅", "NEEDS_WORK": "🏋️", "REST_REQUIRED": "🛏️"}.get(r["form_cycle"], "?")
            lines.append(f"| {r['horse']} | {r['elo']} | {r['win_pct']}% | {r['top3_pct']}% | {r['ev_score']} | {ci} |")
        lines.append("")

    # PEAKING + READY with race targets
    active = [r for r in recommendations
              if r["form_cycle"] in ("PEAKING", "READY") and not r["already_entered"] and r["top_races"]]
    if active:
        lines.append("## 🎯 Race Targets (Approval Required)")
        for r in sorted(active, key=lambda x: -x["ev_score"]):
            rec = r.get("record", {})
            rec_str = f"{rec.get('wins', 0)}W/{rec.get('starts', 0)}S" if rec.get("starts") else "Unraced"
            ci = "🔥" if r["form_cycle"] == "PEAKING" else "✅"
            lines.append(f"### {ci} {r['horse']} — ELO {r['elo']} | Win {r['win_pct']}% | Top3 {r['top3_pct']}% | EV {r['ev_score']}")
            lines.append(f"*{rec_str} · {r['track']} · Stam {r['stamina']}%*")
            lines.append("")
            lines.append("| # | Race | Field | Fit | Why | Risks |")
            lines.append("|---|------|-------|-----|-----|-------|")
            for i, tr in enumerate(r["top_races"], 1):
                race = tr["race"]
                desc = f"{race.get('date','?')} · {race.get('track','?')} R{race.get('race_num','?')} · {race.get('distance','')} {race.get('surface','')} · {race.get('race_type','')}"
                fld = str(tr.get("field_size")) if tr.get("field_size") is not None else "?"
                fit_txt = "; ".join(tr["reasons"][:3])
                risk_txt = "; ".join(tr["risks"][:2]) if tr["risks"] else "—"
                lines.append(f"| {i} | {desc} | {fld} | {tr['score']} | {fit_txt} | {risk_txt} |")
            lines.append("")

    # Ready but no races
    no_match = [r for r in recommendations
                if r["form_cycle"] in ("PEAKING", "READY") and not r["already_entered"] and not r["top_races"]]
    if no_match:
        lines.append("## ❓ Ready — No Matching Races")
        lines.append("| Horse | ELO | Win% | EV | Form |")
        lines.append("|-------|-----|------|-----|------|")
        for r in no_match:
            lines.append(f"| {r['horse']} | {r['elo']} | {r['win_pct']}% | {r['ev_score']} | {r['form_cycle']} |")
        lines.append("")

    # Needs work
    work = [r for r in recommendations if r["form_cycle"] == "NEEDS_WORK"]
    if work:
        lines.append("## 🏋️ Needs Work")
        for r in work:
            lines.append(f"- **{r['horse']}** — Stam {r['stamina']}%, {'; '.join(r['form_factors'][:2])}")
        lines.append("")

    # Rest
    rest = [r for r in recommendations if r["form_cycle"] == "REST_REQUIRED"]
    if rest:
        lines.append("## 🛏️ Rest Required")
        for r in rest:
            lines.append(f"- **{r['horse']}** — Stam {r['stamina']}%, {'; '.join(r['form_factors'][:2])}")
        lines.append("")

    lines.append("---")
    lines.append(f"*Trainer Brain v2 · ELO + Form Cycle · {today}*")
    opp = "\n".join(lines) + "\n"
    (REPORTS / "Race_Opportunities.md").write_text(opp, encoding="utf-8")
    print(f"Race_Opportunities.md: {len(opp)} chars")

    # ── Approval Queue ──────────────────────────────────

    queue: List[Dict] = []
    for r in recommendations:
        if r["form_cycle"] == "REST_REQUIRED":
            queue.append({
                "horse": r["horse"], "action": "rest",
                "reason": f"Stamina {r['stamina']}%",
                "approval_required": False,
                "ev_score": r["ev_score"],
                "form_cycle": r["form_cycle"],
                "timestamp": datetime.now().isoformat(),
            })
        elif r["form_cycle"] == "NEEDS_WORK":
            queue.append({
                "horse": r["horse"], "action": "timed_work",
                "reason": "; ".join(r["form_factors"][:2]),
                "approval_required": False,
                "ev_score": r["ev_score"],
                "form_cycle": r["form_cycle"],
                "timestamp": datetime.now().isoformat(),
            })
        elif r["already_entered"]:
            queue.append({
                "horse": r["horse"], "action": "review_entry",
                "reason": "Already entered",
                "win_pct": r["win_pct"], "top3_pct": r["top3_pct"],
                "approval_required": True,
                "ev_score": r["ev_score"],
                "form_cycle": r["form_cycle"],
                "timestamp": datetime.now().isoformat(),
            })
        elif r["top_races"]:
            tr = r["top_races"][0]
            race = tr["race"]
            queue.append({
                "horse": r["horse"], "action": "enter_race",
                "race_id": race.get("race_id", ""),
                "race_date": race.get("date", ""),
                "race_track": race.get("track", ""),
                "race_num": race.get("race_num", ""),
                "race_distance": race.get("distance", ""),
                "race_conditions": race.get("race_type", ""),
                "race_purse": race.get("purse", ""),
                "field_size": race.get("field_size"),
                "fit_score": tr["score"],
                "win_pct": r["win_pct"],
                "top3_pct": r["top3_pct"],
                "ev_score": r["ev_score"],
                "form_cycle": r["form_cycle"],
                "reasons": tr["reasons"],
                "risks": tr["risks"],
                "approval_required": True,
                "timestamp": datetime.now().isoformat(),
            })

    (OUTPUTS / "approval_queue.json").write_text(
        json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
    needs_approval = sum(1 for q in queue if q.get("approval_required"))
    print(f"approval_queue.json: {len(queue)} items ({needs_approval} need approval)")

    # ── Approval Pack ──────────────────────────────────

    pack_lines = [
        "# 📋 Approval Pack",
        f"> **Generated:** {today} | **Model:** ELO + Form Cycle v2",
        "",
        "## Instructions",
        "Review each recommendation. Check box to approve, leave unchecked to skip.",
        "Only approved items should be manually entered on HRP.",
        "",
    ]

    entered_q = [q for q in queue if q.get("action") == "review_entry"]
    if entered_q:
        pack_lines.append("## ✅ Already Nominated (Review)")
        for q in entered_q:
            pack_lines.append(f"- [ ] **{q['horse']}** — EV {q.get('ev_score',0)} | Win {q.get('win_pct',0)}% | {q['form_cycle']}")
            pack_lines.append(f"  - [Profile](https://www.horseracingpark.com/stables/horse.aspx?Horse={q['horse'].replace(' ', '+')})")
        pack_lines.append("")

    entry_q = [q for q in queue if q.get("action") == "enter_race"]
    if entry_q:
        pack_lines.append("## 🎯 Recommended Entries (Approval Required)")
        for q in sorted(entry_q, key=lambda x: -(x.get("ev_score", 0))):
            track = q.get("race_track", "?")
            race_date = q.get("race_date", "?")
            race_num = q.get("race_num", "?")
            dist = q.get("race_distance", "?")
            cond = q.get("race_conditions", "")
            fld = q.get("field_size")
            fld_str = f" (Field: {fld})" if fld else ""
            pack_lines.append(f"- [ ] **{q['horse']}** → {race_date} {track} R#{race_num} {dist} {cond}{fld_str}")
            pack_lines.append(f"  - EV {q.get('ev_score',0)} | Win {q.get('win_pct',0)}% | Top3 {q.get('top3_pct',0)}% | Form: {q['form_cycle']}")
            pack_lines.append(f"  - Fit: {'; '.join(q.get('reasons', [])[:3])}")
            if q.get("risks"):
                pack_lines.append(f"  - Risks: {'; '.join(q['risks'][:2])}")
            pack_lines.append(f"  - **Steps:** [Find a Race](https://www.horseracingpark.com/stables/find_race.aspx) → Select **{track}** → Race #{race_num} → Enter **{q['horse']}**")
            pack_lines.append(f"  - [Horse Profile](https://www.horseracingpark.com/stables/horse.aspx?Horse={q['horse'].replace(' ', '+')})")
        pack_lines.append("")

    work_q = [q for q in queue if q.get("action") in ("timed_work", "rest")]
    if work_q:
        pack_lines.append("## 🏋️ Training / Rest (No Approval Needed)")
        for q in work_q:
            action = "🛏️ Rest" if q["action"] == "rest" else "🏋️ Timed Work"
            pack_lines.append(f"- [x] **{q['horse']}** — {action}: {q.get('reason', '')}")
        pack_lines.append("")

    pack_lines.extend([
        "---",
        f"*Approval Pack generated by Trainer Brain v2 — {today}*",
        "*SAFETY: No in-game actions taken. All entries require manual execution.*",
    ])

    pack = "\n".join(pack_lines) + "\n"
    (REPORTS / "Approval_Pack.md").write_text(pack, encoding="utf-8")
    print(f"Approval_Pack.md: {len(pack)} chars")

    # ── PHASE 1: Predictions Log ──────────────────────

    predictions = []
    for r in recommendations:
        if not r["top_races"]:
            continue
        for tr in r["top_races"]:
            race = tr["race"]
            predictions.append({
                "generated_at": datetime.now().isoformat(),
                "horse_name": r["horse"],
                "race_id": race.get("race_id", ""),
                "track": race.get("track", ""),
                "date": race.get("date", ""),
                "race_num": race.get("race_num", ""),
                "distance": race.get("distance", ""),
                "surface": race.get("surface", ""),
                "race_type": race.get("race_type", ""),
                "conditions": race.get("conditions", "")[:100],
                "form_tag": r["form_cycle"],
                "predicted_win_prob": r["win_pct"],
                "predicted_top3_prob": r["top3_pct"],
                "ev_score": r["ev_score"],
                "fit_score": tr["score"],
                "field_size": race.get("field_size"),
                "purse": race.get("purse", ""),
                "approved": "",
            })

    # Save daily JSON
    pred_json_path = OUTPUTS / f"predictions_log_{today}.json"
    pred_json_path.write_text(json.dumps(predictions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"predictions_log_{today}.json: {len(predictions)} predictions")

    # Append to CSV (create if not exists)
    csv_path = OUTPUTS / "predictions_log.csv"
    csv_exists = csv_path.exists()
    fieldnames = [
        "generated_at", "horse_name", "race_id", "track", "date", "race_num",
        "distance", "surface", "race_type", "conditions", "form_tag",
        "predicted_win_prob", "predicted_top3_prob", "ev_score", "fit_score",
        "field_size", "purse", "approved",
    ]
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not csv_exists:
            writer.writeheader()
        for p in predictions:
            writer.writerow(p)
    print(f"predictions_log.csv: appended {len(predictions)} rows")

    # ── Summary ────────────────────────────────────────

    counts = {}
    for r in recommendations:
        counts[r["form_cycle"]] = counts.get(r["form_cycle"], 0) + 1
    print(f"\nForm Cycle Summary:")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
