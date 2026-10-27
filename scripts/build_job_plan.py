#!/usr/bin/env python3
"""Build a StructDay-Bench confirmatory job plan (JSON) from protocol + instance list.

Snapshot paths are written relative to --runtime-root (meal-rec-ai checkout),
where pools are installed under:
  outputs/bronze_search_bench/instances/aging_exact_confirm_v1/pools/<id>/
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Logical label -> dmp4p_runtime method name
METHODS = {
    "aging": "pymoo_sms_aging_bronze",
    "smsemoa": "pymoo_smsemoa_bronze",
    "r2hca": "pymoo_r2hca_bronze",
    "nsga2": "pymoo_nsga2_bronze",
    "nsga3": "pymoo_nsga3_bronze",
    "agemoea": "pymoo_agemoea_bronze",
    "agemoea2": "pymoo_agemoea2_bronze",
    "rvea": "pymoo_rvea_bronze",
    "rvea_wallclock": "pymoo_rvea_wallclock_bronze",
    "ga": "pymoo_ga_bronze",
    "cpsat_band": "cpsat_band",
}

DEFAULT_METHODS = (
    "aging",
    "smsemoa",
    "r2hca",
    "nsga2",
    "nsga3",
    "agemoea",
    "agemoea2",
    "rvea",
    "ga",
    "cpsat_band",
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--selection",
        type=Path,
        default=REPO / "protocol" / "selection.json",
    )
    ap.add_argument(
        "--methods",
        default=",".join(DEFAULT_METHODS),
        help="Comma-separated logical method labels",
    )
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--task-seconds", type=float, default=210.0)
    ap.add_argument("--slot-seconds", type=float, default=30.0)
    ap.add_argument("--max-days", type=int, default=7)
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument(
        "--snapshot-prefix",
        default="outputs/bronze_search_bench/instances/aging_exact_confirm_v1/pools",
        help="Path prefix relative to meal-rec-ai runtime root",
    )
    ap.add_argument(
        "--ga-config",
        default="config/ga_reconciled_v1.yaml",
        help="GA YAML relative to runtime root (copy from this repo's config/ if needed)",
    )
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()

    sel = json.loads(args.selection.read_text(encoding="utf-8"))
    rows = sel["rows"]
    seeds = [int(x) for x in args.seeds.split(",") if x.strip() != ""]
    method_labels = [m.strip() for m in args.methods.split(",") if m.strip()]
    for m in method_labels:
        if m not in METHODS:
            raise SystemExit(f"Unknown method {m!r}; choose from {sorted(METHODS)}")

    jobs = []
    for row in rows:
        iid = str(row["instance_id"])
        snap = f"{args.snapshot_prefix.rstrip('/')}/{iid}"
        for seed in seeds:
            for label in method_labels:
                jobs.append(
                    {
                        "key": f"{iid}__{label}__s{seed}",
                        "instance_id": iid,
                        "difficulty": row["difficulty"],
                        "snapshot": snap,
                        "seed": seed,
                        "method": METHODS[label],
                        "logical_method": label,
                    }
                )

    plan = {
        "phase": "structday_bench_confirmatory",
        "protocol_id": "external_main_v1",
        "ga_config": args.ga_config,
        "task_seconds": args.task_seconds,
        "slot_seconds": args.slot_seconds,
        "max_days": args.max_days,
        "device": args.device,
        "config_overrides": {
            "evidence_population_size": 200,
            "evidence_observation_mode": "top8_common",
        },
        "jobs": jobs,
        "n_jobs": len(jobs),
        "n_units": len(rows),
        "seeds": seeds,
        "methods": method_labels,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} with {len(jobs)} jobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
