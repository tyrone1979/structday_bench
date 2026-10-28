#!/usr/bin/env python3
"""Run the released StructDay-Bench confirmatory panel.

The repository contains the frozen pools, released baseline adapters, and the
independent evaluation runtime.  CUDA is optional; timing is recorded for the
selected device.
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
        "--out",
        type=Path,
        default=REPO / "outputs" / "confirm_rerun",
        help="Batch output directory (created under this tree by default)",
    )
    ap.add_argument(
        "--plan",
        type=Path,
        default=REPO / "outputs" / "job_plan.json",
        help="Job plan JSON (built if missing)",
    )
    ap.add_argument("--methods", default=None, help="Override methods CSV for plan build")
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    root = REPO
    if not (root / "dmp4p_runtime" / "batch.py").is_file():
        raise SystemExit("Released runtime is missing dmp4p_runtime/batch.py")

    py = sys.executable
    if not args.plan.is_file() or args.methods:
        build = [
            py,
            str(REPO / "scripts" / "build_job_plan.py"),
            "--selection",
            str(REPO / "data" / "instances" / "manifest.csv"),
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
