# Official HRP Rules Reference — Complete Game Mechanics

> Source: https://www.horseracingpark.com/help/index.aspx (fetched 2026-02-26)
> This is the **authoritative** rules reference distilled from the official page.

---

## Meter Ranges & Optimal Values

| Meter | Range | Optimal | Notes |
|-------|-------|---------|-------|
| **Condition** | 0–110 | 95–105 (equivalent) | Goes UP with train/work/race, DOWN during maintenance |
| **Stamina** | 0–110 | 95–105 (equivalent) | Goes UP during maintenance, DOWN with train/work/race |
| **Consistency** | 0–5 | Higher = more consistent | Does NOT make horse faster, just less volatile |
| **Distance** | 5S–5L | Depends on horse | S=shorter, L=longer; drifts toward 0 during maintenance |

### Consistency Deep Dive
- **2–4 works+races in 30 days** → consistency goes UP
- **5 works+races** → no change
- **0, 1, or 6+** → consistency goes DOWN
- Drops after a race, WIC, or work >1 mile; can take abnormal hit if horse performs badly
- `0(5)` means deep into zero — takes longer to recover
- **Training mode:** consistency does NOT drop during maintenance

### Condition Degradation (CRITICAL — OFFICIAL, NOT FORUM LORE)
> **If condition drops below 50, the horse actively DEGRADES.**
> You must keep condition ≥95 for as long as it was <50 to regain lost ability.
> This is OFFICIALLY stated on the HRP help page (Section 37), not forum conjecture.

**Official Quote:** "If the condition meter drops below 50 your horse will actually start degrading. On average you will have to keep the condition meter at or above 95 for as long as it was below 50 to regain anything that was lost provided the horse is not past its prime."

**Key Details:**
- The degradation is described as loss of ability, not merely a meter penalty
- Recovery requires condition at 95+ for an equivalent duration
- If the horse is "past its prime," the lost ability may NOT be recoverable
- This is a permanent ability loss that must be actively recovered from

Source URL: https://www.horseracingpark.com/help/index.aspx (Section 37)
Confidence: High

---

## Training Mode vs Racing Mode (Farms Only)

| Aspect | Racing Mode | Training Mode |
|--------|-------------|---------------|
| Condition | Normal (drops during maintenance) | Moves toward 100, stops at 100 |
| Stamina | Normal (rises during maintenance) | Moves toward 100, stops at 100 |
| Consistency | Normal rules | Does NOT drop during maintenance |
| **Penalty** | None | Must switch to racing 3 maintenance periods before race |

### Training Mode Consistency Penalty (exiting training mode)

| Maintenance Periods After Switch | Penalty |
|----------------------------------|---------|
| 0 (race immediately) | **100%** — consistency treated as 0 |
| 1 period passed | **66%** penalty |
| 2 periods passed | **33%** penalty |
| 3+ periods passed | No penalty |

---

## Filly/Mare Weight Allowances (vs Males)

| Age | Before Sept 1 | On/After Sept 1 |
|-----|---------------|-----------------|
| 2yo | 3 lbs | 3 lbs |
| 3+  | **5 lbs** | **3 lbs** |

*Does NOT apply to handicap races (already factored in).*

---

## Meter Movement Tables (Official)

### Maintenance (Nightly)

| Age | Condition Loss | Stamina Gain |
|-----|---------------|-------------|
| 1yo | 1–10 | 6–14 |
| 2yo | 1–8 | 6–14 |
| 3yo | 1–6 | 6–14 |
| 4+  | 1–4 | 6–14 |

### Training

| Type | Condition Gain | Stamina Loss | Distance |
|------|---------------|-------------|----------|
| Std-Short | 10–14 | 7–11 | 0–2 Short |
| Standard | 10–14 | 8–12 | 0 |
| Std-Long | 10–14 | 9–13 | 0–2 Long |
| Hvy-Short | 16–20 | 24–30 | 1–3 Short |
| Heavy | 16–20 | 27–33 | 0 |
| Hvy-Long | 16–20 | 30–36 | 1–3 Long |

### Works (Breezing vs Handily — Key Distances)

| Distance | Breeze Cond | Breeze Stam | Handily Cond | Handily Stam |
|----------|------------|------------|-------------|-------------|
| 3f | 9–12 | 20–23 | 9–13 | 23–26 |
| 4f | 9–13 | 22–25 | 9–14 | 25–28 |
| 5f | 10–14 | 24–27 | 10–15 | 27–30 |
| 6f | 11–14 | 26–29 | 11–15 | 29–32 |
| 1m | 12–16 | 30–33 | 12–17 | 33–36 |

### Race Stamina Loss

| Distance | Stamina Loss | Condition Gain |
|----------|-------------|---------------|
| 5f | 53–64 | 2–4 |
| 6f | 54–65 | 2–4 |
| 7f | 55–66 | 2–4 |
| 1m | 56–67 | 2–4 |
| 1 1/8m | 57–68 | 2–4 |
| 1 1/4m | 58–69 | 2–4 |

---

## Racing Eligibility Requirements

1. Horse must be **named**
2. Must be at track or in transit (unless track checking off)
3. **Timed work at a track within 90 days**
4. **Condition ≥75 AND Stamina ≥75** or auto-scratched
5. After 5 races: must have work meeting time requirement in last 90 days

### Minimum Work Times (After 5 Races)

| Distance | Max Time |
|----------|----------|
| 2f | <25s |
| 3f | <39s |
| 4f | <53s (52s SA downhill turf) |
| 5f | <67s (65s SA downhill turf) |
| 6f | <81s (78s SA downhill turf) |
| 7f | <95s |
| 1m | <109s |

---

## Stakes Weight Penalties

### Ungraded Stakes (<$100 purse)
- Graded stakes winner in last 6 months: **INELIGIBLE**
- Graded stakes winner in last 9 months: +6 lbs
- Graded stakes winner in last 12 months: +4 lbs
- Stakes winner in last 12 months: +2 lbs

### Ungraded Stakes ($100–$249 purse)
- Graded stakes winner in last 9 months: +6 lbs
- Graded stakes winner in last 12 months: +4 lbs
- Stakes winner in last 12 months: +2 lbs

### Graded Stakes
- GIII <$250: GI win in 3mo +6, GII win +4, GIII win +2
- GII <$250: GI win in 3mo +4, GII win +2
- GI, $250+, BC qualifiers, turf sprints: **No penalties**

---

## State-Bred Bonus Percentages (Official)

| State | Restricted | Bonus (Sire Out/In) | Race Types |
|-------|-----------|---------------------|------------|
| **CA** | Yes | 15/30% | MSW, CL30+, sALW, OCL30+, ALW |
| **NY** | Yes | 7.5/15% | MCL30+, MSW, CL30+, sALW, OCL30+, ALW, STK |
| **FL** | Yes | 10/20% | MCL15+, MSW, CL15+, sALW15+, ALW |
| **KY** | No | 20/40% | MSW, OCLN, ALW |
| **ON** | Yes | 7.5/15% | MCL20+, MSW, CL20+, sALW20+, OCL20+, ALW, STK |
| **PA** | Yes | 10/20% | MCL, MSW, CL, sALW, OCL, ALW |
| **LA** | Yes | 7.5/15% | MCL, MSW, CL, sALW, OCL, ALW, STK |
| **NJ** | Yes | 7.5/15% | MCL, MSW, CL, sALW, OCL, ALW, STK |
| **NM** | Yes | 10/20% | MCL, MSW, CL, sALW, OCL, ALW |
| **TX** | Yes | 7.5/15% | MCL, MSW, CL, sALW, OCL, ALW, STK |
| **BC** | Yes | 15/30% | MCL, MSW, CL |
| **WV/AZ** | Yes | None | Restricted races only |

- Max single-race bonus: **$12 (owner+breeder)** or **$20 (owner+breeder+sire)**
- Sire owner bonus requires foal bred after 7/1/07
- **KY has NO restricted races** — bonuses only (20/40% is the highest!)
- Must be **pay stable (Platinum)** to receive bonuses

---

## Race Priority Rules (Oversubscribed)

### Overnights (non-2yo maiden)
1. One entry per owner first
2. Horses WITH wins get preference over horses WITHOUT
3. Earliest nomination time
4. Coin toss

### 2yo Maiden Overnights
1. One entry per owner first
2. **Preference date system** (oldest date first)
3. Coin toss

### Stakes
1. Any listed race preferences
2. Earnings per race (last 2 years)
3. Wins → Places → Shows (last 2 years)
4. Coin toss

---

## Key Performance Tips (Official)

- Keep condition ≥95 as much as possible for continued improvement
- Horses need **at least 1 timed work every 1–2 months** or they degrade
- **Weight** is a fitness indicator: too low = overworked, too high = needs more work
- Watch for **cyclical up/down patterns**
- Horses can become **fatigued over long periods** — need months off
- Too much OR too little total distance traveled affects performance
- Race distance has more impact than work distance
- Handily works have more impact than breezing works

---

## Purse Distribution

| Place | Percentage |
|-------|-----------|
| 1st | 60% |
| 2nd | 20% |
| 3rd | 16% |
| 4th | 4% |

---

## 2yo Race Availability by Month

| Month | Race Types | Max Dirt Dist | Max Turf Dist |
|-------|-----------|---------------|---------------|
| Apr | Md, Stk | ≤4.5f | — |
| May | Md, MC, Stk | ≤5f | — |
| Jun | Md, MC, NW2, Stk | ≤5.5f | — |
| Jul+ | Md, MC, Cl, sAlw, NW2, Stk | ≤6f dirt, ≤7.5f turf | Jul |
| Aug+ | All above | ≤1m | ≤1 1/16m |

## Relocating / Shipping
- **Nearby tracks:** Same day, no stamina hit (if not worked/raced that day)
- **Other tracks:** 1 maintenance period; may incur stamina hit
- **Slow transit:** No stamina hit, but takes extra days
- **Stamina hit = 8–9% per day** of transit
