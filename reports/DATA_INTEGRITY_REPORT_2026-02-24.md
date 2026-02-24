# Data Integrity Report — 2026-02-24

## Roster Reconciliation

| Source | Count |
|--------|-------|
| Roster HTML | 36 |
| Exported dirs | 35 |
| Snapshot JSON | 35 |
| Tracker Stable | 35 |

### Mismatches Found
| Horse | In Roster | Exported | Snapshot | Tracker | Notes |
|-------|-----------|----------|----------|---------|-------|
| Averys Pluck | ✅ | ❌ | ❌ | ❌ | Has `horse.aspx` link but exporter discovery missed it |
| Shebas Briar | ✅ | ❌ | ❌ | ❌ | Same issue — URL pattern `AllRaces=No` variant |

**Root cause:** The `discover_horse_urls()` function in `02_export_stable.py` may use a link pattern that doesn't match these two horses. They have valid profile links in the roster page. **Recommendation:** Fix discovery to also capture `AllRaces=No` links, or re-export these two manually.

> All other 34 horses match across all 4 data sources.

---

## Nominations Fix

### Before
| Metric | Dashboard | Weekly Plan |
|--------|-----------|-------------|
| With Nominations | **0** | 0 horses |
| Upcoming Races | *(empty)* | *(empty)* |

### After
| Metric | Dashboard | Weekly Plan |
|--------|-----------|-------------|
| With Nominations | **8** | 8 horses |
| Upcoming Races | 8 entries with Horse/Date/Track/Race#/Class | Full schedule table |

**Root cause:** `06_generate_reports.py` counted nominations only from `stable_snapshot.json` (per-horse profile page parsing), which is unreliable in daily mode. The real nominations live in the tracker XLSX `Nominations` sheet (populated by `04_parse_and_fill.py`).

**Fix:** Updated `06_generate_reports.py` to load tracker Nominations sheet as source of truth for nomination counts and race schedules.

### Example Horses (tracker nominations)
| Horse | Date | Track | Race# | Class |
|-------|------|-------|-------|-------|
| Hardline Anvil | 03/04/2026 | CT | 3 | Clm6.25N3L |
| Hydration | 03/04/2026 | HOU | 4 | Clm5.00N2X |
| Strike King | 03/04/2026 | TUP | 7 | OClm10/N2X-N |

---

## Race Calendar

- **Parsed:** `inputs/2026-02-24/race_calendar.json`
- **Races found:** 9+ structured entries
- **Fields:** raw_text, race_class, track, date, distance, surface

---

## Audit Script
`scripts/00_data_integrity_audit.py` — cross-checks roster/exports/snapshot/tracker. Currently exits 1 due to the 2 missing horses (known issue, not a parser bug).

---

## Files Changed
| File | Change |
|------|--------|
| `scripts/00_data_integrity_audit.py` | **NEW** — roster reconciliation script |
| `scripts/06_generate_reports.py` | Fixed nominations to use tracker sheet |
| `scripts/07_parse_race_calendar.py` | **NEW** — structured race calendar parser |
