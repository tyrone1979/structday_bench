"""Structure-Nutrient-GA: nutrient/band-gap edits + structure-aware lex selection.

Innovation boundary (must not collapse into a pymoo adapter):
- Variation remains domain gap add/drop/replace (nutrient and/or band cells), not
  pymoo bit-flip / SBX operators.
- Soft structure (personal meal×major band deviation) participates in breeding
  selection after hard-proxy feasibility and BLD — this coupling is the method.
- Shared Deb-style ordering idea (feasibility before soft goals) is used only as
  a ranking policy on our own proxies; search operators stay custom.

v2.7 ranking: continuous hard_pen → binary BLD → band.
  Binary hard_ok alone removed the nutrient gradient that soft_fit used to
  provide among infeasible individuals (v2.5/v2.6c → 0 days on easy).
v2.7 variation: nutrient-gap; optional band-gap off by default until days recover.
"""
from __future__ import annotations

import numpy as np
import torch

from dmp4p_runtime.algorithms.nutrient_ga import NutrientGuidedGA
from dmp4p_runtime.score_fields import BLD_MIN_G
from algo.structure_category import UPPER_ONLY_MAJORS

DEFAULT_SN_EXPLORE_RATE = 0.10
# Extra band-gap after nutrient-gap; keep 0 until primary days recover.
DEFAULT_SN_BAND_EDIT_RATE = 0.0
# Continuous BLD in lex hurt primary days; default stays binary.
DEFAULT_SN_BLD_CONTINUOUS = False
SN_METHOD_VARIANT = "structure_nutrient_hardpen_bld_band_v27"
_HARD_OK_EPS = 1e-9


def matched_intensity_random_edit(masks, allowed_mask, rng, owner, indices=None):
    """Same fire-rate and one-edit arity as nutrient mutate; random add/drop/replace."""
    p = len(masks)
    n_elite = max(2, p // 10)
    if indices is None:
        indices = range(n_elite, p)
    mx = int(owner.evaluator.spec.max_combination_size)
    for i in indices:
        if i < n_elite:
            continue
        if rng.random() > max(0.2, owner.mutation_rate * 10):
            continue
        mask = masks[i].copy()
        mask &= allowed_mask
        on = np.flatnonzero(mask)
        off = np.flatnonzero(~mask & allowed_mask)
        ops = []
        if len(off) and int(mask.sum()) < mx:
            ops.append("add")
        if len(on):
            ops.append("drop")
        if len(on) and len(off):
            ops.append("replace")
        if not ops:
            continue
        op = ops[int(rng.integers(0, len(ops)))]
        if op == "add":
            mask[int(rng.choice(off))] = True
        elif op == "drop":
            mask[int(rng.choice(on))] = False
        else:
            mask[int(rng.choice(on))] = False
            mask[int(rng.choice(off))] = True
        masks[i] = mask
    return masks


def band_gap_edit(masks, allowed_mask, rng, owner, indices=None, *, force=False):
    """One-edit band-cell repair: mirror nutrient-gap but on meal×major intervals.

    When ``indices`` is provided (caller already rate-gated), edits always fire
    unless ``force`` is False and the shared nutrient fire-rate check fails.
    """
    cells = getattr(owner, "_band_edit_cells", None)
    if not cells:
        return matched_intensity_random_edit(masks, allowed_mask, rng, owner, indices=indices)
    p = len(masks)
    n_elite = max(2, p // 10)
    explicit = indices is not None
    if indices is None:
        indices = range(n_elite, p)
    mx = int(owner.evaluator.spec.max_combination_size)
    grams = np.asarray(owner._grams, dtype=float)
    for i in indices:
        if i < n_elite:
            continue
        if not explicit and not force:
            if rng.random() > max(0.2, owner.mutation_rate * 10):
                continue
        mask = masks[i].copy()
        mask &= allowed_mask
        unders = []
        overs = []
        for cell in cells:
            total = float((grams * cell["row"] * mask).sum())
            under = max(cell["lo"] - total, 0.0)
            over = max(total - cell["hi"], 0.0)
            if under > 0:
                unders.append((under, cell))
            if over > 0:
                overs.append((over, cell))
        sum_u = sum(u for u, _ in unders)
        sum_o = sum(o for o, _ in overs)
        if sum_u > sum_o and sum_u > 0:
            _, cell = max(unders, key=lambda t: t[0])
            cand = np.flatnonzero(~mask & allowed_mask & cell["row"])
            if len(cand):
                pick = int(cand[int(np.argmax(grams[cand]))])
                if int(mask.sum()) < mx:
                    mask[pick] = True
                else:
                    on = np.flatnonzero(mask)
                    if len(on):
                        mask[int(on[int(rng.integers(0, len(on)))])] = False
                        mask[pick] = True
        elif sum_o > 0:
            _, cell = max(overs, key=lambda t: t[0])
            on_cell = np.flatnonzero(mask & cell["row"])
            if len(on_cell):
                drop = int(on_cell[int(np.argmax(grams[on_cell]))])
                mask[drop] = False
        else:
            on = np.flatnonzero(mask)
            off = np.flatnonzero(~mask & allowed_mask)
            if len(on) and len(off):
                mask[int(on[int(rng.integers(0, len(on)))])] = False
                mask[int(off[int(rng.integers(0, len(off)))])] = True
        masks[i] = mask
    return masks


class StructureNutrientGA(NutrientGuidedGA):
    name = "structure_nutrient_ga"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cfg = self.config or {}
        self.sn_explore_rate = float(np.clip(float(cfg.get("sn_explore_rate", DEFAULT_SN_EXPLORE_RATE)), 0.0, 1.0))
        self.sn_band_edit_rate = float(
            np.clip(float(cfg.get("sn_band_edit_rate", DEFAULT_SN_BAND_EDIT_RATE)), 0.0, 1.0)
        )
        self.sn_bld_continuous = bool(cfg.get("sn_bld_continuous", DEFAULT_SN_BLD_CONTINUOUS))
        self.method_variant = SN_METHOD_VARIANT
        self._band_edit_cells = self._build_band_edit_cells()

    def _build_band_edit_cells(self):
        meals = self.pool["meal"].astype(str).str.lower().to_numpy()
        majors = self.pool["food_group_code"].astype(int).to_numpy()
        upper_only = set((self.personal or {}).get("upper_only_majors") or UPPER_ONLY_MAJORS)
        cells = []
        for key, bounds in ((self.personal or {}).get("bands") or {}).items():
            _, _, major, meal = key.split("_", 3)
            major = int(major)
            hi = float(bounds["hi"])
            lo = 0.0 if major in upper_only else float(bounds["lo"])
            if hi <= 0:
                continue
            row = (meals == meal) & (majors == major)
            if not row.any():
                continue
            cells.append(
                {
                    "key": key,
                    "meal": meal,
                    "major": major,
                    "lo": lo,
                    "hi": hi,
                    "row": row,
                    "idx": np.flatnonzero(row),
                }
            )
        return cells

    def _scaled_hard_penalty(self, pop_t, nut_t, grams_t, banned_t):
        """Per-nutrient scaled hard proxy (CV-like); not a pymoo CV import."""
        if banned_t.any():
            pop_t = pop_t.clone()
            pop_t[:, banned_t] = False
        sel = pop_t.float()
        nut_sums = sel @ nut_t
        lo = torch.as_tensor(self._lo, device=pop_t.device, dtype=nut_sums.dtype)
        hi = torch.as_tensor(self._hi, device=pop_t.device, dtype=nut_sums.dtype)
        scale = torch.maximum(lo.abs(), torch.ones_like(lo))
        below = torch.clamp(lo - nut_sums, min=0) / scale
        above = torch.clamp(nut_sums - hi, min=0) / scale
        nut_pen = (below + above).sum(dim=1)
        n_sel = pop_t.sum(dim=1).float()
        mn = float(self.evaluator.spec.min_foods)
        mx = float(self.evaluator.spec.max_combination_size)
        card_pen = torch.where(
            n_sel < mn,
            (mn - n_sel),
            torch.where(n_sel > mx, (n_sel - mx), torch.zeros_like(n_sel)),
        )
        total_g = (sel * grams_t).sum(dim=1)
        max_g = float(self.evaluator.spec.max_daily_g)
        wt_pen = torch.clamp(total_g - max_g, min=0.0) / 100.0
        return nut_pen + card_pen + wt_pen, pop_t.detach().cpu().numpy()

    def _band_and_bld(self, masks, grams_t, device, *, use_band=True):
        sel = torch.as_tensor(masks, device=device).float()
        band = torch.zeros(len(sel), device=device, dtype=grams_t.dtype)
        meals = self.pool["meal"].astype(str).str.lower().to_numpy()
        majors = self.pool["food_group_code"].astype(int).to_numpy()
        if use_band:
            upper_only = set((self.personal or {}).get("upper_only_majors") or UPPER_ONLY_MAJORS)
            for key, bounds in ((self.personal or {}).get("bands") or {}).items():
                _, _, major, meal = key.split("_", 3)
                major = int(major)
                hi = float(bounds["hi"])
                lo = 0.0 if major in upper_only else float(bounds["lo"])
                if hi <= 0:
                    continue
                cell = torch.as_tensor((meals == meal) & (majors == major), device=device)
                total = sel @ (grams_t * cell)
                band += (lo - total).clamp(min=0) + (total - hi).clamp(min=0)
        # Continuous BLD shortfall (grams), aligned with pymoo bronze F[:,0].
        bld_short = torch.zeros(len(sel), device=device, dtype=grams_t.dtype)
        for meal, minimum in BLD_MIN_G.items():
            meal_mask = torch.as_tensor(meals == meal, device=device)
            meal_g = sel @ (grams_t * meal_mask)
            bld_short += (float(minimum) - meal_g).clamp(min=0)
        return band, bld_short

    def _lex_rank(self, hard_pen, bld_key, band, dtype, device):
        """Lex ranks: continuous hard_pen → BLD key → band."""
        order = torch.argsort(band, stable=True)
        order = order[torch.argsort(bld_key[order], stable=True)]
        order = order[torch.argsort(hard_pen[order], stable=True)]
        ranked = torch.empty(len(hard_pen), device=device, dtype=dtype)
        ranked[order] = torch.arange(len(hard_pen), 0, -1, device=device, dtype=dtype) / len(hard_pen)
        return ranked

    def _fitness_batch(self, pop_t, nut_t, grams_t, banned_t, *, use_band=True):
        # Parent soft_fit unused in lex; continuous hard_pen carries the gradient.
        _soft_fit, penalty, masks = NutrientGuidedGA._fitness_batch(
            self, pop_t, nut_t, grams_t, banned_t
        )
        hard_pen, masks = self._scaled_hard_penalty(pop_t, nut_t, grams_t, banned_t)
        hard_ok = hard_pen <= _HARD_OK_EPS
        band, bld_short = self._band_and_bld(masks, grams_t, pop_t.device, use_band=use_band)
        bld_ok = bld_short <= _HARD_OK_EPS
        bld_key = bld_short if self.sn_bld_continuous else (~bld_ok).to(dtype=hard_pen.dtype)
        ranked = self._lex_rank(
            hard_pen, bld_key, band, dtype=hard_pen.dtype, device=pop_t.device
        )
        ranking = (
            "hard_pen→BLD_shortfall→band"
            if self.sn_bld_continuous
            else "hard_pen→BLD→band"
        )
        self.last_structure_diagnostics = {
            "bld_shortfall": bld_short.detach().cpu().tolist(),
            "bld_ok": bld_ok.detach().cpu().tolist(),
            "band": band.detach().cpu().tolist(),
            "hard_pen": hard_pen.detach().cpu().tolist(),
            "hard_ok": hard_ok.detach().cpu().tolist(),
            "use_band": bool(use_band),
            "ranking": ranking,
            "variation": "nutrient_gap_then_band_gap+matched_random_explore",
            "method_variant": self.method_variant,
            "sn_explore_rate": self.sn_explore_rate,
            "sn_band_edit_rate": self.sn_band_edit_rate,
            "sn_bld_continuous": self.sn_bld_continuous,
        }
        return ranked, penalty, masks

    def _nutrient_mutate(self, masks, dens, allowed_mask, rng):
        """Nutrient-gap first; optional extra band-gap; explore_rate rewrites slots."""
        n_elite = max(2, len(masks) // 10)
        explore_idx = []
        if self.sn_explore_rate > 0:
            explore_idx = [
                i for i in range(n_elite, len(masks)) if rng.random() < self.sn_explore_rate
            ]
        base = masks.copy()
        # Always keep nutrient-gap as primary (v2.6a: do not XOR away nutrient path).
        NutrientGuidedGA._nutrient_mutate(self, masks, dens, allowed_mask, rng)
        if self.sn_band_edit_rate > 0:
            band_idx = [
                i
                for i in range(n_elite, len(masks))
                if i not in explore_idx and rng.random() < self.sn_band_edit_rate
            ]
            if band_idx:
                band_gap_edit(masks, allowed_mask, rng, self, indices=band_idx)
        if explore_idx:
            rnd = base.copy()
            matched_intensity_random_edit(rnd, allowed_mask, rng, self, indices=explore_idx)
            for i in explore_idx:
                masks[i] = rnd[i]
        return masks
