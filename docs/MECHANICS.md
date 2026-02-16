# HRP Mechanics Bible

This directory captures official, explicit HRP mechanics from Help pages.

- Canonical source set:
  - https://www.horseracingpark.com/help/index.aspx
  - https://www.horseracingpark.com/help/handicapping.aspx
  - https://www.horseracingpark.com/help/verifybenefits.aspx

Structured topic files:

- `docs/mechanics/training.md`
- `docs/mechanics/timed_works.md`
- `docs/mechanics/training_vs_racing_mode.md`
- `docs/mechanics/consistency.md`
- `docs/mechanics/race_eligibility_and_scratches.md`
- `docs/mechanics/shipping_and_relocation.md`
- `docs/mechanics/breeding_and_foals.md`
- `docs/mechanics/accessories_and_adds.md`
- `docs/mechanics/handicapping_weight_rules.md`

Index build:

```powershell
py scripts/09_build_mechanics_index.py
```

Output:

- `outputs/mechanics/mechanics_index.json`
