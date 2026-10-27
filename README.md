# StructDay-Bench

Public **benchmark artifacts** for structure-conditioned, fixed-portion, **multi-day** dietary optimization under a wall-clock protocol. **No new algorithm.**

Paper / LaTeX / Access template / paper-build scripts are **not** hosted here. They live in the private research tree on Gitee (`meal-rec-ai`, path `manuscript/structday_bench_access_v1/`).

## Contents

| Path | Content |
|------|---------|
| `data/instances/pools/` | Frozen confirmatory panel (~30 MB, 12 units × pool/meta/personal) |
| `protocol/` | Panel selection, wall-clock protocol JSON, default `job_plan.json` |
| `config/ga_reconciled_v1.yaml` | Shared GA / evaluator config used by the confirmatory runs |
| `scripts/` | Install pools, build job plan, run batch, verify data |
| `results/` | Aggregate baseline tables + official summary JSON (existing algos only) |
| `docs/DATA_PIPELINE.md` | NHANES raw XPT → cohort → targets → pools → instances |

## Quick start (reproduce confirmatory panel)

You need a separate **meal-rec-ai** checkout that provides `dmp4p_runtime` (solvers, CUDA optional).

```bash
# 1) Check the 12 frozen pools match protocol/selection.json
python3 scripts/verify_data.py

# 2) Install pools + config into the runtime tree, then dry-run the batch
export MEAL_REC_AI_ROOT=/path/to/meal-rec-ai
python3 scripts/run_benchmark.py --runtime-root "$MEAL_REC_AI_ROOT" --dry-run

# 3) Full confirmatory rerun (long wall-clock; resume-safe)
python3 scripts/run_benchmark.py --runtime-root "$MEAL_REC_AI_ROOT" \
  --out outputs/confirm_rerun --resume
```

Helpers:

```bash
python3 scripts/install_pools.py --runtime-root "$MEAL_REC_AI_ROOT"
python3 scripts/build_job_plan.py -o protocol/job_plan.json
```

Default panel: **12 units × 10 methods × 3 seeds** (see `protocol/job_plan.json`). Budgets: 210 s task / 30 s slot / 7 days.

## Published results

Aggregate tables under `results/tables/` (no new solvers):

- `method_summary_noblex.csv` — method totals (days / all-band / ge7)
- `run_level_noblex.csv` — per-run rows
- `by_difficulty.csv`, `panel_units.csv`, `panel_meta.csv`
- `results/official/` — confirmatory summary + dominance / RVEA recheck JSON

## Benchmark claim (protocol + comparison)

1. NHANES raw files → optimization **inputs** (documented pipeline).
2. Frozen evaluation **protocol** (budgets, panel, metrics).
3. **Existing** MOEA / GA / CP baselines on the same instances.
4. Compare delivered days and all-band conformity; retain failures.

## License

- Aggregate evaluation tables: CC BY 4.0.
- Frozen confirmatory pools: research reuse under the same terms as this repo’s LICENSE; upstream NHANES / FNDDS remain under NCHS / USDA terms (raw XPT not redistributed).
