#!/usr/bin/env python3
"""Run the StructDay-Bench confirmatory panel via meal-rec-ai dmp4p_runtime.batch.

Requires a local meal-rec-ai checkout with solvers installed (pymoo, torch/CUDA
optional depending on methods). This repo ships frozen pools + protocol only.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--runtime-root",
        type=Path,
        default=Path(os.environ.get("MEAL_REC_AI_ROOT", "")),
        help="meal-rec-ai checkout (or set MEAL_REC_AI_ROOT)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO / "outputs" / "confirm_rerun",
        help="Batch output directory (created under this tree by default)",
    )
    ap.add_argument(
        "--plan",
        type=Path,
        default=REPO / "protocol" / "job_plan.json",
        help="Job plan JSON (built if missing)",
    )
    ap.add_argument("--methods", default=None, help="Override methods CSV for plan build")
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-install", action="store_true")
    ap.add_argument("--force-install", action="store_true")
    args = ap.parse_args()

    root = args.runtime_root.resolve() if str(args.runtime_root) else Path()
    if not root or not (root / "dmp4p_runtime" / "batch.py").is_file():
        raise SystemExit(
            "Pass --runtime-root /path/to/meal-rec-ai or set MEAL_REC_AI_ROOT"
        )

    py = sys.executable
    if not args.skip_install:
        cmd = [py, str(REPO / "scripts" / "install_pools.py"), "--runtime-root", str(root)]
        if args.force_install:
            cmd.append("--force")
        subprocess.check_call(cmd)

    if not args.plan.is_file() or args.methods:
        build = [
            py,
            str(REPO / "scripts" / "build_job_plan.py"),
            "--selection",
            str(REPO / "protocol" / "selection.json"),
            "--seeds",
            args.seeds,
            "--device",
            args.device,
            "-o",
            str(args.plan),
        ]
        if args.methods:
            build.extend(["--methods", args.methods])
        subprocess.check_call(build)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    batch = [
        py,
        "-m",
        "dmp4p_runtime.batch",
        "--plan",
        str(args.plan.resolve()),
        "--out",
        str(args.out.resolve()),
    ]
    if args.dry_run:
        batch.append("--dry-run")
    if args.resume:
        batch.append("--resume")
    print("EXEC", " ".join(batch), flush=True)
    return subprocess.call(batch, cwd=str(root), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
