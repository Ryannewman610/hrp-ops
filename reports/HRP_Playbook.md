# HRP Playbook
> Living knowledge base — updated every session. Source: [HRP Help](https://www.horseracingpark.com/help/index.aspx)

---

## 1. Core Rules & Systems

### 1.1 Training Options
| Mode | Condition ↑ | Stamina ↓ | When to Use |
|------|-------------|-----------|-------------|
| **Heavy Train** | ★★★★ | ★★★★ | Short sprint to peak condition; watch stamina closely |
| **Standard Train** | ★★★ | ★★★ | Default daily training for active racers |
| **Standard-Short** | ★★½ | ★★½ | Fine-tuning condition without overdrawing stamina |
| **Standard-Long** | ★★★ | ★★★ | Distance prep / endurance building |
| **Light Train** | ★★ | ★ | Maintaining condition while conserving stamina |
| **Rest** | — | — | Recovery mode; no condition added, no stamina taken |

### 1.2 Timed Works
- **Max per day:** 2 timed works
- **Prerequisite:** Stamina > 0
- **Start options:** Conservative · Normal · Aggressive
- **Pace options:** Horse Lead · Heavy Push · Push · Restrain · Heavy Restrain
- **Effort options:** Breezing · Handily
- **Eligibility rule:** A horse must have a timed work at its track within the last **90 days** or it becomes ineligible to race there

### 1.3 Training Mode vs Racing Mode
| | Training Mode | Racing Mode |
|---|---|---|
| **Schedule** | 1–8 quarters | Indefinite |
| **Consistency** | Protected (does not drop during maintenance) | Normal decay rules apply |
| **Transition penalty** | — | After switching FROM training → racing: penalty decreases by 1 each maintenance for 3 periods |

> **Rule of thumb:** Use Training Mode for young horses, rehab, or off-season prep. Switch to Racing Mode ≥3 maintenance periods before target race to clear the penalty.

### 1.4 Consistency Rules
Consistency changes per maintenance period based on total **works + races** that period:

| Works + Races | Consistency Change |
|---|---|
| 0 or 1 | **−1** |
| 2, 3, or 4 | **+1** |
| 5 | No change |
| 6+ | **−1** |

- **What counts:** Races, timed works in company, timed works > 1 mile
- **Sweet spot:** Keep total activity at **2–4 per maintenance period**

### 1.5 Race Eligibility & Scratches
- **Minimum to race:** Condition ≥ 75 **AND** Stamina ≥ 75
- **Auto-scratch:** If either drops below 75 at cutoff
- **Scratch window:** Up to **1 hour before post time**
- **Track eligibility:** Must have a timed work at the track within the last 90 days

### 1.6 Shipping & Relocation
| Ship Mode | Stamina Hit | Travel Time |
|-----------|-------------|-------------|
| **Regular** | Possible stamina penalty | Immediate |
| **Slow** | No stamina hit | 1 day (same region) · 2 days (cross-region) |

> **Best practice:** Use Slow when stamina is tight or there's no urgency. Use Regular only when race timing demands it.

### 1.7 Breeding & Foals
- **Stallion requirements:** Retired, age ≥ 4, age ≤ 20
- **Mare limits:** 1 breeding per quarter, age ≤ 20
- **Stallion cap:** 25 offspring per quarter
- **Foal delivery:** ~3 days after quarter start

### 1.8 Accessories & Medications
- Owners can assign: **Blinkers**, **Front Wraps**, **Bute** from horse pages
- ⚠️ **Lock rule:** Changing accessories/meds is **blocked** if the horse has an active entry or nomination
- **Action required:** Make accessory/med changes *before* entering a race

### 1.9 Handicapping & Weight
- **Adjusted Speed Formula:** `Adj Speed = Speed Rating + ((126 − Weight Carried) × 0.10)`
- **Allowance range:** 100–140 lbs
- **Key takeaway:** Lighter weight = higher adjusted speed. A 10-lb drop ≈ +1.0 speed-rating boost

---

## 2. Competitive Strategy

### 2.1 Pre-Race Decision Tree
```
Has timed work at track in last 90 days?
├─ NO → Schedule work first, THEN enter
└─ YES
   └─ Condition ≥ 80 AND Stamina ≥ 80?
      ├─ NO → Train/Rest until thresholds met (75 min, 80 safer)
      └─ YES
         └─ Does race class match horse's recent form?
            ├─ NO → Consider up/down-classing or skip
            └─ YES → ENTER (requires owner approval if credits involved)
```

### 2.2 Stamina / Condition Management
- **Never hover near 75.** Race-day maintenance can push you below → auto-scratch.
- **Target:** Enter races with ≥ 80 in both; prefer ≥ 85 for stakes.
- **Post-race:** Switch to Light Train or Rest for 1–2 maintenance periods to recover stamina.

### 2.3 Consistency Sweet Spot
- Aim for **2–4** works+races per maintenance period.
- If a horse isn't racing, schedule **2 timed works** to maintain consistency.
- Avoid 6+ activities in a period — that *decreases* consistency.

### 2.4 Shipping Strategy
- Ship early using **Slow mode** when possible (plan 1–2 days ahead).
- Only use Regular if race timing requires same-day arrival.
- Cross-region ships need 2-day lead time in Slow mode.

---

## 3. Practical Workflows

### 3.1 Daily Checklist (Semi-Autonomous)
1. **Review meters** — Check condition, stamina, consistency for all active horses
2. **Check entries** — Any upcoming races within 24–48 hours?
3. **Check eligibility** — All entered horses still ≥ 75/75? Any at risk?
4. **Adjust training** — Set training mode for non-racing horses to hit 2–4 activity sweet spot
5. **Log decisions** — Any entry/scratch/breeding decisions → `Decisions_Log.md`
6. **Update dashboard** — Refresh `Stable_Dashboard.md` with current state

### 3.2 Weekly Checklist
1. Review week's results → update Win/Place/Show record
2. Identify horses needing rest (stamina < 85)
3. Plan next week's race targets → `Weekly_Plan.md`
4. Check breeding windows (quarter timing)
5. Review bankroll and purse income
6. Audit consistency trends — any horse at 0–1 activity?

### 3.3 Approval Triggers
These actions **always require explicit owner approval:**
- [ ] Entering a race (costs credits)
- [ ] Claiming a horse
- [ ] Breeding decisions
- [ ] Selling/retiring a horse
- [ ] Purchasing at auction
- [ ] Any spend > 0 credits

### 3.4 Semi-Autonomous Actions (No Approval Needed)
- ✅ Adjusting training mode (Heavy/Standard/Light/Rest)
- ✅ Scheduling timed works
- ✅ Updating dashboard and logs
- ✅ Analyzing race conditions and making recommendations
- ✅ Shipping via Slow mode (no stamina cost, no credits)

---

## 4. Empirical Discoveries

| # | Hypothesis | Status | Evidence |
|---|-----------|--------|----------|
| 1 | "2–4 works+races per period is the consistency sweet spot" | ✅ Confirmed | Official help page |
| 2 | "Training mode → racing mode penalty lasts exactly 3 maintenance periods" | ✅ Confirmed | Official help page |
| 3 | "Adj Speed formula: SR + ((126 − wt) × 0.10)" | ✅ Confirmed | Handicapping help page |

> *Add new discoveries here as we test hypotheses against real race data.*

---

## 5. Reference Links
- [HRP Help Index](https://www.horseracingpark.com/help/index.aspx)
- [Handicapping Guide](https://www.horseracingpark.com/help/handicapping.aspx)
- [Verify Benefits](https://www.horseracingpark.com/help/verifybenefits.aspx)
