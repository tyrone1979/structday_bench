#!/usr/bin/env python3
"""Install confirmatory pool snapshots into a meal-rec-ai checkout.

Copies ``data/instances/pools/<id>/`` into:
  <runtime-root>/outputs/bronze_search_bench/instances/aging_exact_confirm_v1/pools/<id>/

Also installs ``config/ga_reconciled_v1.yaml`` when missing in the runtime root.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC_POOLS = REPO / "data" / "instances" / "pools"
SRC_CFG = REPO / "config" / "ga_reconciled_v1.yaml"
REL_POOLS = Path("outputs/bronze_search_bench/instances/aging_exact_confirm_v1/pools")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--runtime-root",
        type=Path,
        required=True,
        help="Path to meal-rec-ai checkout that provides dmp4p_runtime",
    )
    ap.add_argument("--force", action="store_true", help="Overwrite existing pool dirs")
    args = ap.parse_args()
    root = args.runtime_root.resolve()
    if not (root / "dmp4p_runtime" / "batch.py").is_file():
        raise SystemExit(f"Not a meal-rec-ai root (missing dmp4p_runtime/batch.py): {root}")

    dest_root = root / REL_POOLS
    dest_root.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in sorted(p for p in SRC_POOLS.iterdir() if p.is_dir()):
        dest = dest_root / src.name
        if dest.exists():
            if not args.force:
                print(f"skip existing {dest}")
                continue
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        n += 1
        print(f"installed {src.name}")

    cfg_dest = root / "config" / "ga_reconciled_v1.yaml"
    if SRC_CFG.is_file() and (args.force or not cfg_dest.is_file()):
        cfg_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC_CFG, cfg_dest)
        print(f"installed {cfg_dest.relative_to(root)}")

    print(f"done: {n} pools -> {dest_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
