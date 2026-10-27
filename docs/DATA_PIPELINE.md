# From NHANES raw files to benchmark inputs

This document is the paper-facing description of how public NHANES/FNDDS artifacts become frozen optimization instances. Counts refer to the reconciled release build used for the confirmatory panel (standalone 2017–2018 excluded in favour of combined 2017–March 2020).

## 0. Upstream files (not redistributed here)

Under each cycle directory (e.g. `0304` … `2123`):

| Role | Typical files |
|------|----------------|
| Demographics | `DEMO_*.xpt` / `P_DEMO` / `DEMO_L` |
| Anthropometry | `BMX_*.xpt` (`BMXWT`, `BMXHT`) |
| Individual foods | `DR1IFF` / `DR2IFF` (+ food code tables) |
| Supplements | Cycle-dependent `DS1TOT`/`DS2TOT` or 30-day `DSQ*` |
| Composition | Merged FNDDS-style food / nutrient / FPED tables |

## 1. Participant export and filters

**Script (research tree):** `scripts/export_nhanes_participants_raw.py`

Order of filters:

1. Age `RIDAGEYR ≥ 19`.
2. Drop dietary-supplement users (24-h or 30-day instruments by cycle).
3. Require exam weight and height `> 0`.
4. Require ≥1 individual-food recall day in `DR1IFF`/`DR2IFF`.

Output: adult food-only cohort tables (demographics + keep flags).

## 2. Health tagging and nutrient targets

1. Tag examination / lab / questionnaire conditions (`tag_participants_health_raw.py`).
2. Map tags + anthropometry + PAL → closed nutrient intervals (`compute_participant_targets.py`).

A **target dictionary** is a map nutrient → `[L, U]`. Many SEQNs share a target; search units are not one-per-respondent.

## 3. Recall export and structure priors

Export item-level recalls and day aggregates. Rebuild:

- meal-share / day-mass summaries;
- meal × FNDDS-major category gram envelopes stratified by sex × BMI class × age band;
- food-frequency tables for uncommon-food soft penalties.

**Reconciled release rule:** retain non-overlapping cycle folders; exclude standalone `1718` when combined `1720` is present (exact body-measure / recall overlap audit).

## 4. Candidate food pools

For each structure×target unit:

1. Apply plate-food exclusions and require FPED coverage.
2. Expand foods only into allowed meal slots.
3. Keep NHANES grams; attach FNDDS display units as labels only.
4. Drop items that alone violate a nutrient upper bound; cap pool size.
5. Lock cells with learned upper envelope `hi ≤ 0` (forbidden types).

Frozen instance snapshot: pool rows + personal envelopes + target + mass cap `G_max`.

## 5. Confirmatory panel sampling

Protocol id: `external_main_v1` / confirmatory panel freeze.

- Unit = structure × nutrient target (not participant hold-out).
- Sample seed `2026102612`; exclude previously exposed canonical IDs.
- Three units per prior difficulty label `{easy, medium, hard, extreme}` → **12 units**.
- Seeds `{0,1,2}`; **no solver screening**; failures retained.

## 6. Runtime budgets (shared by all methods)

| Budget | Value |
|--------|------:|
| Task wall clock | 210 s |
| Per-day / slot wall clock | 30 s |
| Max days per task | 7 |
| Population (MOEA adapters) | 200 |
| Observation mode | top-8 common |

## 7. Outcomes

- **Delivered days:** independently float64-validated plans admitted under BLD minima and deadline.
- **All-band days:** delivered days with no soft category upper-envelope violation (effective lowers were zero on this panel).
- Lexicographic method comparison uses totals over the fixed 36 tasks (12×3), failures kept in denominators.

## Disjoint from NutriOpt-Bench (TEVC)

NutriOpt-Bench/RCFA uses equal evaluation budgets and FHR metrics for single-assembly interval boxes. This pipeline feeds multi-day wall-clock MealRec-Bench instances instead.
