# SRF / Speed Rating Mechanics

## Overview
SRF (SimRacingForm) is a third-party speed rating system available at simracingform.com and integrated into HRP via the "SRF Charts" and "Purchase SRF" menu options. It is separate from HRP's internal "speed rating" used in the handicapping formula.

---

## HRP's Internal Speed Rating (Handicapping Formula)

Topic: HRP Handicapping Speed Rating Formula
Claim: HRP uses a weight-based handicapping system, NOT a raw speed rating in the traditional sense. The handicapping formula uses a points-based rating system:
- Points are earned from race finishes (GI win=20pts, GII win=15pts, GIII win=10pts, etc.)
- Points are time-decayed (100% if <2 months, down to 25% at 10-12 months)
- Points are calculated per surface/distance category and cross-weighted
- Final weight formula: 130-((61-pts)/2), then converted to carried weight based on grade level
Source URL: https://www.horseracingpark.com/help/handicapping.aspx
Snippet: "The number of points for each horse is then plugged into the following formula: 130-((61-pts)/2) and rounded to the nearest integer."
Confidence: High

---

## Is SRF the Same as HRP's Speed Rating?

Topic: SRF vs HRP Speed Rating
Claim: SRF is NOT the same as HRP's internal "speed rating" used in the handicapping formula. SRF is a third-party calculation from SimRacingForm. HRP's handicapping uses a points-based system derived from race finishes, not raw speed figures. The formula "Adjusted Speed = speed rating + ((126 - weight) × 0.10)" may refer to SimRacingForm's own adjusted speed calculation, not an official HRP formula.
Source URL: https://www.horseracingpark.com/help/handicapping.aspx
Confidence: High

---

## SRF Calculation Method

Topic: How SRF is Calculated
Claim: SimRacingForm calculates SRF using race times, but the exact proprietary formula is not publicly documented. Based on SimRacingForm articles, SRF appears to factor in:
- Raw race time / final time
- Distance of the race
- Track and surface conditions
- The quality/depth of the field is likely NOT part of the SRF itself but is considered in separate analysis
SRF is presented as a per-race speed figure that can be compared across distances.
Source URL: https://simracingform.com/maximizing-your-horses-potential-by-using-race-conditions-and-horse-assessment/
Confidence: Medium (exact formula is proprietary)

---

## SRF Benchmarks by Class Level (5f Maidens)

Topic: SRF Class Level Benchmarks
Claim: SimRacingForm provides the following SRF benchmarks for 5f maiden races:
- Bottom Level: Winners typically have SRF 78-89
- Low Level: Winners typically have SRF 79-88
- Mid Level: Winners typically have SRF 82-89
- High Level: Winners typically have SRF 82-90
Note: These are maiden benchmarks only. Higher class levels (allowance, stakes) would have higher SRFs.
Source URL: https://simracingform.com/maximizing-your-horses-potential-by-using-race-conditions-and-horse-assessment/
Confidence: High (for SRF topics)

---

## Track Condition Adjustment

Topic: SRF Track Condition Adjustment
Claim: It is likely that SRF adjusts for track condition (fast vs sloppy) since the tool's purpose is to compare performances across different race days. However, the exact adjustment methodology is not publicly documented. HRP itself confirms that "Some horses run better under certain track conditions" — so any speed rating system needs to account for this.
Source URL: https://www.horseracingpark.com/help/index.aspx (Section 36), https://simracingform.com/
Confidence: Low (not confirmed)

---

## Work Quality Benchmarks

Topic: SRF-Adjacent Work Time Benchmarks
Claim: SimRacingForm provides work quality benchmarks:
- 5f work benchmarks for free-side horses: :59.3 to 1:01.0H
- 5f work benchmarks for pay-side horses: :58.4 to 1:00.0H
- A "top 25%" work time is the goal for race-ready horses
- Breezing (B) work at the farm is considered superior to Handily (H) work at the track for the same raw time
Source URL: https://simracingform.com/horse-racing-park-prepping-new-foals-for-races/
Confidence: High (for SRF topics)

---

## Speed Rating in Unverified Stable Restrictions

Topic: Speed Rating Average in Claiming Restrictions
Claim: HRP uses "speed rating avg" in unverified stable claiming restrictions:
- Speed rating avg under 50 → Any claiming price
- Speed rating avg under 55 → Claiming price $10+
- Speed rating avg under 60 → $15+
- ... up to under 95 → $50+
This suggests HRP has its own internal "speed rating" that may or may not be the same as SRF.
Source URL: https://www.horseracingpark.com/help/index.aspx (Section 3)
Confidence: High
