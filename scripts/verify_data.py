#!/usr/bin/env python3
"""Verify confirmatory pool directories match data/instances/manifest.csv."""
from __future__ import annotations

import json
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    with (REPO / "data" / "instances" / "manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
        ids = [r["instance_id"] for r in csv.DictReader(stream)]
    pools = REPO / "data" / "instances" / "pools"
    missing = []
    ok = []
    for iid in ids:
        d = pools / iid
        need = ["pool.pkl", "meta.json", "personal.json"]
        if not d.is_dir() or any(not (d / f).is_file() for f in need):
            missing.append(iid)
        else:
            ok.append(iid)
    extra = sorted({p.name for p in pools.iterdir() if p.is_dir()} - set(ids))
    print(f"expected={len(ids)} present={len(ok)} missing={len(missing)} extra={len(extra)}")
    if missing:
        print("missing:", ", ".join(missing))
        return 1
    if extra:
        print("extra (not in selection):", ", ".join(extra))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
