"""External main comparison protocol constants, freeze payload and stratified sampling.

Gate-5 helper: freeze methods/budgets/observation before one-shot unit draw.
Does not invoke solvers. Sampling never filters on search success.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

PROTOCOL_ID = "external_main_v1"
SAMPLE_SEED = 202610230
N_PER_DIFFICULTY = 6
DIFFICULTIES = ("easy", "medium", "hard", "extreme")
PAIRED_SEEDS = (0, 1, 2)
TASK_SECONDS = 210.0
SLOT_SECONDS = 30.0
MAX_DAYS = 7
GA_POPULATION = 200
OBSERVATION_MODE = "top8_common"

# External ranking family (SCORE / production / Nutrient-GA excluded).
EXTERNAL_METHODS = (
    "structure_nutrient_ga",
    "pymoo_ga_bronze",
    "pymoo_nsga2_bronze",
    "pymoo_agemoea_bronze",
    "cpsat_band",
)

# Internal mechanism family (separate Holm family; not external ranking).
NS_ABLATION_METHODS = (
    "structure_nutrient_n1s1",
    "structure_nutrient_n0s1",
    "structure_nutrient_n1s0",
    "structure_nutrient_n0s0",
)

# Code/config paths hashed into the declared freeze (relative to repo root).
FREEZE_PATHS = (
    "dmp4p_runtime/algorithms/pymoo_bronze.py",
    "dmp4p_runtime/algorithms/structure_nutrient_ga.py",
    "dmp4p_runtime/algorithms/structure_nutrient_ablation.py",
    "dmp4p_runtime/algorithms/cpsat_band.py",
    "dmp4p_runtime/algorithms/nutrient_ga.py",
    "dmp4p_runtime/algorithms/ga_common.py",
    "dmp4p_runtime/factory.py",
    "dmp4p_runtime/multiday_common.py",
    "dmp4p_runtime/observation_control.py",
    "dmp4p_runtime/score_fields.py",
    "dmp4p_runtime/p0_overall_envelope.py",
    "dmp4p_runtime/external_main_protocol.py",
    "dmp4p_runtime/batch.py",
    "dmp4p_runtime/cli.py",
    "config/external_main_protocol_v1.json",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def protocol_declaration() -> dict[str, Any]:
    return {
        "protocol_id": PROTOCOL_ID,
        "unit": "structure×target optimization unit (not individual participant hold-out)",
        "external_methods": list(EXTERNAL_METHODS),
        "ns_ablation_methods": list(NS_ABLATION_METHODS),
        "excluded_from_external_ranking": [
            "v2_quality_recovery",
            "v2_production",
            "nutrient_ga",
        ],
        "budgets": {
            "task_seconds": TASK_SECONDS,
            "slot_seconds": SLOT_SECONDS,
            "max_days": MAX_DAYS,
        },
        "ga": {
            "evidence_population_size": GA_POPULATION,
            "evidence_observation_mode": OBSERVATION_MODE,
        },
        "sampling": {
            "seed": SAMPLE_SEED,
            "n_per_difficulty": N_PER_DIFFICULTY,
            "difficulties": list(DIFFICULTIES),
            "no_solver_screening": True,
            "difficulty_source": "classify_bronze_difficulty on priors/demographics",
        },
        "paired_seeds": list(PAIRED_SEEDS),
        "primary_endpoints": [
            "seven_day_delivery_rate",
            "n_all_reference_band_pass_days_0_to_7",
        ],
        "return_policy": "common online observer + shared lexicographic delivery; native Pareto not used for return",
        "bld_delivery_g": {"breakfast": 30.0, "lunch": 50.0, "dinner": 50.0},
        "cell_policy": "hi<=0 hard ban; gram intervals soft; no entree-required gate",
        "state": "inputs_declared_freeze; independent draw required before long runs",
    }


def file_digest(root: Path, rel_paths: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in rel_paths:
        p = root / rel
        if p.is_file():
            out[rel] = sha256_file(p)
    return out


def freeze_payload(root: Path, *, ga_config: str, extra_files: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Deterministic freeze record for gate-5 (no solver invocation)."""
    files = file_digest(root, FREEZE_PATHS)
    cfg = root / ga_config
    if cfg.is_file():
        files[ga_config] = sha256_file(cfg)
    if extra_files:
        files.update(extra_files)
    decl = protocol_declaration()
    payload = {
        "declaration": decl,
        "ga_config": ga_config,
        "files": dict(sorted(files.items())),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "fingerprint": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "payload": payload,
    }


def canonical_unit(structure_key: str, target_dict: dict) -> str:
    return (
        str(structure_key)
        + "|"
        + json.dumps(target_dict, sort_keys=True, separators=(",", ":"))
    )


def sample_stratified_units(
    eligible: pd.DataFrame,
    *,
    seed: int = SAMPLE_SEED,
    n_per: int = N_PER_DIFFICULTY,
    difficulties: Iterable[str] = DIFFICULTIES,
    difficulty_col: str = "difficulty",
    id_col: str = "instance_id",
) -> pd.DataFrame:
    """Equal-stratum draw; sorts by id within stratum; no outcome columns allowed."""
    forbidden = {"ge7", "n_days_delivered", "n_all_bands_days", "feasible", "success"}
    overlap = forbidden.intersection(set(eligible.columns))
    if overlap:
        raise ValueError(f"eligible frame must not carry outcome columns: {sorted(overlap)}")
    if difficulty_col not in eligible.columns or id_col not in eligible.columns:
        raise ValueError("eligible needs difficulty and instance_id")
    rng = __import__("numpy").random.default_rng(int(seed))
    parts = []
    for d in difficulties:
        g = eligible.loc[eligible[difficulty_col].astype(str) == d].sort_values(id_col)
        if len(g) < n_per:
            raise ValueError(f"difficulty {d}: need {n_per}, have {len(g)}")
        pick = g.iloc[rng.choice(len(g), size=int(n_per), replace=False)].copy()
        parts.append(pick)
    out = pd.concat(parts, ignore_index=True)
    out["set"] = "external_main_confirmation"
    out["protocol_id"] = PROTOCOL_ID
    return out


def build_job_plan(
    units: pd.DataFrame,
    methods: Iterable[str],
    seeds: Iterable[int],
    *,
    phase: str,
    ga_config: str,
    snapshot_root: str,
    device: str = "cuda:0",
    task_seconds: float = TASK_SECONDS,
    slot_seconds: float = SLOT_SECONDS,
    max_days: int = MAX_DAYS,
    population: int = GA_POPULATION,
    input_files: Optional[list[str]] = None,
) -> dict[str, Any]:
    methods = list(methods)
    seeds = list(seeds)
    jobs = []
    for n, (_, row) in enumerate(units.iterrows()):
        for seed in seeds:
            rot = (n + int(seed)) % len(methods)
            order = methods[rot:] + methods[:rot]
            for method in order:
                iid = str(row["instance_id"])
                jobs.append(
                    {
                        "key": f"{iid}__{method}__s{seed}",
                        "instance_id": iid,
                        "difficulty": str(row["difficulty"]),
                        "snapshot": f"{snapshot_root.rstrip('/')}/{iid}",
                        "seed": int(seed),
                        "method": method,
                    }
                )
    return {
        "phase": phase,
        "protocol_id": PROTOCOL_ID,
        "ga_config": ga_config,
        "device": device,
        "task_seconds": float(task_seconds),
        "slot_seconds": float(slot_seconds),
        "max_days": int(max_days),
        "config_overrides": {
            "evidence_population_size": int(population),
            "evidence_observation_mode": OBSERVATION_MODE,
        },
        "input_files": list(input_files or []),
        "jobs": jobs,
    }
