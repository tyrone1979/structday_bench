# StructDay-Bench

Public **benchmark artifacts** for structure-conditioned, fixed-portion, **multi-day** dietary optimization under a wall-clock protocol. **No new algorithm.**

Paper / LaTeX / Access template / paper-build scripts are **not** hosted in this GitHub repository. They live in the private research tree on Gitee (`meal-rec-ai`, path `manuscript/structday_bench_access_v1/`).

## Contents

| Path | Content |
|------|---------|
| `protocol/` | Frozen protocol JSON and confirmatory panel selection |
| `results/` | Aggregate baseline tables (existing algorithms only; no new solvers) |
| `docs/DATA_PIPELINE.md` | NHANES raw XPT → cohort → targets → pools → instances |
| `data/` | Manifests only (no NHANES/FNDDS redistribution) |

## Benchmark claim (protocol + comparison)

1. NHANES raw files → optimization **inputs** (documented pipeline).
2. Frozen evaluation **protocol** (budgets, panel, metrics).
3. **Existing** MOEA / GA / CP baselines on the same instances.
4. Compare delivered days and all-band conformity; retain failures.

## License

- Aggregate evaluation tables: CC BY 4.0.
- Upstream NHANES / FNDDS: NCHS / USDA terms (not redistributed here).
