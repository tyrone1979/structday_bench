# StructDay-Bench

Public **benchmark artifacts and executable baseline runtime** for structure-conditioned, fixed-portion, **multi-day** dietary optimization under a wall-clock protocol. **No new algorithm.**

Paper / LaTeX / Access template / paper-build scripts are **not** hosted here. They live in the private research tree on Gitee (`meal-rec-ai`, path `manuscript/structday_bench_access_v1/`).

## Contents

| Path | Content |
|------|---------|
| `data/instances/pools/` | Frozen confirmatory panel (~30 MB, 12 units × pool/meta/personal) |
| `protocol/` | Wall-clock evaluation protocol; panel IDs are in `data/instances/manifest.csv` |
| `config/ga_reconciled_v1.yaml` | Shared GA / evaluator config used by the confirmatory runs |
| `dmp4p_runtime/` | Validator, shared evaluation layer, released baseline adapters, and resumable batch runtime |
| `algo/` | Minimal dependency modules required by the released runtime |
| `scripts/` | Build job plan, run batch, verify data, and rebuild tables |
| `environment.yml` | Reproducible runtime environment |
| `results/` | Aggregate baseline tables + official summary JSON (existing algos only) |
| `docs/DATA_PIPELINE.md` | NHANES raw XPT → cohort → targets → pools → instances |

## Quick start (reproduce confirmatory panel)

Use Linux (the batch runner uses POSIX file locks and signals). CUDA is optional; the ledger records the selected device and timing. A 10-method short CPU execution check and two RVEA schedule tests passed on the reference Linux environment. A complete rerun is hardware-dependent.

```bash
conda env create -f environment.yml
conda activate structday-bench

# 1) Check the 12 frozen pools match data/instances/manifest.csv
python3 scripts/verify_data.py

# 2) Check the plan without invoking a solver
python3 scripts/run_benchmark.py --dry-run

# 3) Full confirmatory rerun (long wall-clock; resume-safe)
python3 scripts/run_benchmark.py --out outputs/confirm_rerun --resume
```

Helpers:

```bash
python3 scripts/build_job_plan.py -o outputs/job_plan.json
```

The packaged default is **12 units × 10 methods × 3 seeds** (360 jobs). Budgets: 210 s task / 30 s slot / 7 days; nominal serial upper bound is 21 hours before overhead. Checkpoints are written per committed day and run. Restart the same command with `--resume`; code, configuration, pools, and plan must match the saved fingerprint.

**RVEA implementation:** `rvea` invokes wall-clock APD progress and reference adaptation. Its module matches the SHA256 stored in the completed experiment's freeze record (see `protocol/rvea_source_provenance.json`). The generation-fraction results remain a stored diagnostic; the released default uses the wall-clock schedule. A short execution check is available as `python scripts/smoke_runtime.py`; it does not repeat the complete published ledger.

The reference execution environment was Linux with Python 3.11.10, NumPy
2.0.2, pandas 2.2.3, OR-Tools 9.15.6755, and PyTorch 2.9.0/CUDA 12.8. CPU
execution is supported for verification and reruns, but wall-clock outcomes
are hardware-dependent and must not be substituted for the reported ledger.

## Published results

Aggregate tables under `results/tables/` (no new solvers):

- `method_summary_noblex.csv` — method totals (days / all-band / ge7)
- `run_level_noblex.csv` — per-run rows
- `by_difficulty.csv`, `panel_units.csv`, `panel_meta.csv`

## Benchmark claim (protocol + comparison)

1. NHANES raw files → optimization **inputs** (documented pipeline).
2. Frozen evaluation **protocol** (budgets, panel, metrics).
3. **Existing** MOEA / GA / CP baselines on the same instances.
4. Compare delivered days and all-band conformity; retain failures.

## License

- Aggregate evaluation tables: CC BY 4.0.
- Frozen confirmatory pools: research reuse under the same terms as this repo’s LICENSE; upstream NHANES / FNDDS remain under NCHS / USDA terms (raw XPT not redistributed).

## Scope of the code release

This repository contains only the common benchmark runtime and the baseline
adapters selected by `scripts/build_job_plan.py`. It excludes unrelated
research algorithms from the parent development tree.  The released runtime is
enough to validate stored plans and to execute the complete confirmatory ledger
from the frozen snapshots.
