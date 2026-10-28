"""Published pymoo adapters for the shared Bronze V2 task.

Algorithm selection, survival and genetic operators are pymoo implementations.
Only the binary diet representation, shared generic repairs, problem evaluation,
common observation and deadline integration are project adapters. No nutrient-
guided mutation, cell operators or SCORE recovery are imported.

Constraint handling (pymoo 0.6.x docs, feasibility-first / parameter-less):
- Single-objective GA uses TournamentSelection(comp_by_cv_and_fitness) and
  FitnessSurvival (lexicographic CV then F).
- Multi-objective adapters use pymoo survival that prefers feasible individuals
  (split_by_feasibility / constrained dominance) before ranking.
- Inequality CV eps is 0.0; final acceptance remains the shared float64
  evaluator, not pymoo's CV flag.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import torch
from dmp4p_runtime.score_fields import BLD_MIN_G
from .base import BaseAlgorithm,AlgoResult
from .ga_common import init_population_in_range,apply_shared_repairs

# Soft objectives shared by the multi-objective bronze adapters (declared up front).
MULTI_OBJECTIVES=("bld_shortfall_g","band_deviation_g")
GA_SCALAR_OBJECTIVE="complete_bld_then_band_bounded_scalar"
PYMOO_MULTI_METHODS=(
    "pymoo_nsga2_bronze",
    "pymoo_agemoea_bronze",
    "pymoo_agemoea2_bronze",
    "pymoo_smsemoa_bronze",
    "pymoo_sms_spu_bronze",
    "pymoo_sms_aging_bronze",
    "pymoo_r2hca_bronze",
    "pymoo_sms_nd_bronze",
    "pymoo_rvea_bronze",
    "pymoo_nsga3_bronze",
)
CONSTRAINT_HANDLING={
    "pymoo_ga_bronze":"feasibility_first_cv_then_f",
    "pymoo_nsga2_bronze":"feasibility_first_then_nsga2_survival",
    "pymoo_agemoea_bronze":"feasibility_first_then_age_moea_survival",
    "pymoo_agemoea2_bronze":"feasibility_first_then_age_moea2_survival",
    "pymoo_smsemoa_bronze":"feasibility_first_then_sms_emoa_survival",
    "pymoo_sms_spu_bronze":"feasibility_first_then_sms_spu_survival",
    "pymoo_sms_aging_bronze":"feasibility_first_then_sms_aging_survival",
    "pymoo_r2hca_bronze":"feasibility_first_then_r2hca_survival",
    "pymoo_sms_nd_bronze":"feasibility_first_then_sms_band_progress_survival_nutrient_mutation",
    "pymoo_rvea_bronze":"feasibility_first_then_rvea_survival",
    "pymoo_nsga3_bronze":"feasibility_first_then_nsga3_survival",
}
# Aging lifespan τ (generations of protection for new offspring). Practical default.
DEFAULT_SMS_AGING_TAU = 5
# Band-progress protection τ for ND-SMS (rejuvenates on band improvement).
DEFAULT_SMS_ND_TAU = 5
# Fraction of offspring that receive nutrient-gap edit instead of bit-flip.
# 0.5 underperformed Aging on easy band (4 vs 6); keep mild domain bias.
DEFAULT_SMS_ND_NUTRIENT_RATE = 0.2
# Direction count for R2HCA (Shang & Ishibuchi, TEVC 2020).
DEFAULT_R2HCA_N_DIRS = 100

class BronzeBinaryProblemValues:
    """Vectorized production hard proxies; independent evaluator remains final."""
    def __init__(self,owner,allowed):
        self.owner=owner
        self.device=owner.device if not str(owner.device).startswith("cuda") or torch.cuda.is_available() else "cpu"
        self.dtype=torch.float64
        self.pool=owner.pool
        self.allowed=np.asarray(allowed,dtype=bool)
        self.meals=self.pool.meal.astype(str).str.lower().to_numpy()
        self.ids=self.pool.food_id.astype(int).to_numpy()
        self.groups=self.pool.food_group_code.astype(int).to_numpy()
        self.nut_keys=list(owner.target_dict)
        def arr(k):
            if k not in self.pool:raise ValueError("Missing target nutrient: "+k)
            v=pd.to_numeric(self.pool[k],errors="raise").to_numpy(dtype=float)
            if not np.isfinite(v).all():raise ValueError("Nonfinite candidate "+k)
            return v
        self.grams=self.tensor(arr("grams"))
        self.nut=self.tensor(np.column_stack([arr(k) for k in self.nut_keys]))
        self.kcal=self.tensor(arr("calorie"))
        self.lo=self.tensor([owner.target_dict[k][0] for k in self.nut_keys])
        self.hi=self.tensor([owner.target_dict[k][1] for k in self.nut_keys])
        # Per-nutrient scale avoids adding grams and milligrams as raw violations.
        self.scale=torch.maximum(self.lo.abs(),torch.ones_like(self.lo))
        self.meal_masks={m:self.tensor((self.meals==m).astype(float)) for m in ("breakfast","lunch","dinner","snack")}
        _,inverse=np.unique(self.ids,return_inverse=True)
        self.inverse=torch.as_tensor(inverse,device=self.device,dtype=torch.long)
        self.n_ids=int(inverse.max()+1)
        self.allowed_t=self.tensor(self.allowed.astype(float))
        self.bands=[]
        upper_only=set((owner.personal or {}).get("upper_only_majors") or [])
        for key,b in ((owner.personal or {}).get("bands") or {}).items():
            _,_,major,meal=key.split("_",3);major=int(major)
            if float(b["hi"])<=0:continue
            lo=0. if major in upper_only else float(b["lo"])
            mask=self.tensor(((self.groups==major)&(self.meals==meal)).astype(float))
            self.bands.append((mask,lo,float(b["hi"])))

    def tensor(self,x):return torch.as_tensor(x,device=self.device,dtype=self.dtype)

    def evaluate(self,X):
        sel=self.tensor(np.asarray(X,dtype=bool))
        sums=sel@self.nut
        g=[(self.lo-sums).clamp(min=0)/self.scale,(sums-self.hi).clamp(min=0)/self.scale]
        n=sel.sum(1)
        spec=self.owner.evaluator.spec
        g += [(float(spec.min_foods)-n).clamp(min=0)[:,None],(n-float(spec.max_combination_size)).clamp(min=0)[:,None]]
        total=sel@self.grams
        g += [((total-float(spec.max_daily_g)).clamp(min=0)/100.)[:,None] if spec.hard_daily_weight else torch.zeros((len(sel),1),device=self.device,dtype=self.dtype)]
        counts=torch.zeros((len(sel),self.n_ids),device=self.device,dtype=self.dtype)
        counts.scatter_add_(1,self.inverse[None,:].expand(len(sel),-1),sel)
        duplicate=(counts-1).clamp(min=0).sum(1)
        disallowed=sel@(1-self.allowed_t)
        g += [duplicate[:,None],disallowed[:,None]]
        meal_g={m:sel@(self.grams*mask) for m,mask in self.meal_masks.items()}
        bld=sum((float(v)-meal_g[m]).clamp(min=0) for m,v in BLD_MIN_G.items())
        if spec.require_bld:g.append((bld/50.)[:,None])
        hard=self.owner.config.get("hard_operability") or {}
        bad=torch.zeros(len(sel),device=self.device,dtype=self.dtype)
        beverage=bad.clone()
        if spec.check_condiment and hard:
            codes=hard.get("condiment_oil_food_group_codes",[8,9])
            cond=self.tensor(np.isin(self.groups,codes).astype(float))
            ch=float(hard.get("condiment_oil_weight_share_hard",.85))
            bh=float(hard.get("beverage_weight_share_hard",.95))
            min_k=float(hard.get("condiment_min_meal_kcal",200))
            for m in ("breakfast","lunch","dinner"):
                mask=self.meal_masks[m]
                mg=meal_g[m]
                share=torch.where(mg>0,(sel@(self.grams*cond*mask))/mg.clamp(min=1e-30),torch.zeros_like(mg))
                active=(sel@(self.kcal*mask))>=min_k
                bad+=((share>=ch)&active).to(self.dtype)
                beverage=torch.maximum(beverage,((share>=bh)&active).to(self.dtype))
            bad=(bad-float(int(hard.get("condiment_fail_n_meals",2)))+1).clamp(min=0)
        g += [bad[:,None],beverage[:,None]]
        band=torch.zeros(len(sel),device=self.device,dtype=self.dtype)
        for mask,lo,hi in self.bands:
            grams=sel@(self.grams*mask)
            band+=(lo-grams).clamp(min=0)+(grams-hi).clamp(min=0)
        G=torch.cat(g,dim=1).detach().cpu().numpy()
        B=bld.detach().cpu().numpy();D=band.detach().cpu().numpy()
        return G,B,D

def _ref_dirs_for_pop(pop_size:int,n_obj:int=2):
    from pymoo.util.ref_dirs import get_reference_directions
    # 2-obj Das-Dennis: n_partitions = pop_size-1 yields pop_size points.
    parts=max(1,int(pop_size)-1)
    return get_reference_directions("das-dennis",n_obj,n_partitions=parts)

_AGE2_GUARD_INSTALLED=False

def _install_agemoea2_geometry_guards():
    """Guard pymoo AGE-MOEA-II Lp projection against zero-norm fronts.

    Upstream ``project_on_manifold`` does ``1/dist`` with no check; flat or
    all-zero objective fronts (common early / after repair on 2-obj diet) raise
    ZeroDivisionError mid-survival. Rebind a safe projector + pairwise distances.
    """
    global _AGE2_GUARD_INSTALLED
    if _AGE2_GUARD_INSTALLED:
        return
    import numba
    from numba import jit
    import pymoo.algorithms.moo.age2 as age2_mod

    @jit(nopython=True, fastmath=True)
    def project_on_manifold(point, p):
        s = 0.0
        for i in range(point.shape[0]):
            v = point[i]
            if v > 0.0:
                s += v ** p
        if s <= 0.0:
            return point
        dist = s ** (1.0 / p)
        if (not np.isfinite(dist)) or dist <= 0.0:
            return point
        out = np.empty_like(point)
        inv = 1.0 / dist
        for i in range(point.shape[0]):
            out[i] = point[i] * inv
        return out

    @jit(nopython=True, fastmath=True)
    def pairwise_distances(front, p):
        m, _n = front.shape
        projected_front = np.empty_like(front)
        for index in range(m):
            projected_front[index] = project_on_manifold(front[index], p)
        distances = np.zeros((m, m), dtype=numba.float64)
        if 0.95 < p < 1.05:
            for row in range(0, m - 1):
                for column in range(row + 1, m):
                    distances[row][column] = (
                        np.sum(np.abs(projected_front[row] - projected_front[column]) ** 2) ** 0.5
                    )
        else:
            for row in range(0, m - 1):
                for column in range(row + 1, m):
                    mid_point = projected_front[row] * 0.5 + projected_front[column] * 0.5
                    mid_point = project_on_manifold(mid_point, p)
                    distances[row][column] = (
                        np.sum(np.abs(projected_front[row] - mid_point) ** 2) ** 0.5
                        + np.sum(np.abs(projected_front[column] - mid_point) ** 2) ** 0.5
                    )
        return distances + distances.T

    age2_mod.project_on_manifold = project_on_manifold
    age2_mod.AGEMOEA2Survival.pairwise_distances = staticmethod(pairwise_distances)
    _AGE2_GUARD_INSTALLED = True

def _sms_hv_survive(algorithm, problem, pop, n_survive, ideal, nadir, random_state):
    """Delegate to SMS LeastHypervolumeContributionSurvival."""
    return algorithm.survival.do(
        problem,
        pop,
        n_survive=n_survive,
        algorithm=algorithm,
        ideal=ideal,
        nadir=nadir,
        random_state=random_state,
    )


def _r2hca_scores(F, W, ref, n_obj):
    """R2-based HV contribution approx (Shang et al.); lower = worse for removal.

    For each solution s and direction w: take min over other points of
    max_k((f_k(other)-f_k(s))/w_k) and the ref length min_k(|r_k-f_k(s)|/w_k);
    score_s = sum_w (that min)^n_obj. Matches CalR2HVC + InitializeUtilityTensor.
    """
    F = np.asarray(F, dtype=float)
    W = np.maximum(np.asarray(W, dtype=float), 1e-32)
    ref = np.asarray(ref, dtype=float)
    n = len(F)
    scores = np.zeros(n, dtype=float)
    for i in range(n):
        s = F[i]
        others = np.concatenate([F[:i], F[i + 1 :]], axis=0) if n > 1 else np.zeros((0, F.shape[1]))
        ref_len = np.min(np.abs(ref - s) / W, axis=1)  # (d,)
        if len(others) == 0:
            scores[i] = float(np.sum(np.maximum(ref_len, 0.0) ** n_obj))
            continue
        diff = (others[None, :, :] - s[None, None, :]) / W[:, None, :]
        mx = diff.max(axis=2)  # (d, n-1)
        mns = np.minimum(mx.min(axis=1), ref_len)
        scores[i] = float(np.sum(np.maximum(mns, 0.0) ** n_obj))
    return scores


def _build_sms_variant_classes():
    """Lazy class factory so pymoo imports stay inside build_pymoo_adapter."""
    from pymoo.algorithms.moo.sms import SMSEMOA
    from pymoo.core.population import Population
    from pymoo.core.survival import Survival
    from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
    from pymoo.util.normalization import normalize as pymoo_normalize

    class SPUSMSEMOA(SMSEMOA):
        """SMS-EMOA + stochastic population update (Bian et al., IJCAI 2023).

        Roughly half of the merged population is protected; HV removal runs only
        on the contested half (generalized from (μ+1) to (μ+λ)).
        """

        def _advance(self, infills=None, **kwargs):
            ideal, nadir = None, None
            if self.normalize:
                F = self.pop.get("F")
                ideal, nadir = F.min(axis=0), F.max(axis=0) + 1e-32
            pop = Population.merge(self.pop, infills) if infills is not None else self.pop
            n_survive = int(self.pop_size)
            n = len(pop)
            if n <= n_survive:
                self.pop = pop
                return
            n_remove = n - n_survive
            rng = self.random_state
            contested_n = max(n_remove, n // 2)
            contested_n = min(contested_n, n)
            idx = np.arange(n)
            rng.shuffle(idx)
            contested_idx = np.sort(idx[:contested_n])
            protected_idx = np.sort(idx[contested_n:])
            protected = pop[protected_idx] if len(protected_idx) else Population()
            contested = pop[contested_idx]
            keep_contested = len(contested) - n_remove
            if keep_contested < 0:
                # Need to remove more than contested size: classic SMS fallback.
                self.pop = _sms_hv_survive(
                    self, self.problem, pop, n_survive, ideal, nadir, rng
                )
                return
            if keep_contested == 0:
                # Remove entire contested half; protected alone forms next pop.
                self.pop = (
                    protected
                    if len(protected_idx) == n_survive
                    else _sms_hv_survive(
                        self, self.problem, protected, n_survive, ideal, nadir, rng
                    )
                )
                return
            survived_c = _sms_hv_survive(
                self, self.problem, contested, keep_contested, ideal, nadir, rng
            )
            self.pop = (
                Population.merge(protected, survived_c)
                if len(protected_idx)
                else survived_c
            )
            if len(self.pop) > n_survive:
                self.pop = _sms_hv_survive(
                    self, self.problem, self.pop, n_survive, ideal, nadir, rng
                )

    class AgingSMSEMOA(SMSEMOA):
        """SMS-EMOA + aging protection (Li, Zheng, Doerr, 2025).

        Offspring start at age 0; only age≥τ enter HV removal; survivors age+=1.
        """

        def __init__(self, *args, aging_tau=DEFAULT_SMS_AGING_TAU, **kwargs):
            super().__init__(*args, **kwargs)
            self.aging_tau = int(max(1, aging_tau))
            self._aging_initialized = False

        def _ensure_ages(self, pop, default_age):
            # Correctness: missing/nonfinite ages become default_age; finite ages kept.
            # Historical calib may have used nonfinite initials — keep those results labelled separately.
            raw = pop.get("age")
            try:
                ages = np.asarray(raw, dtype=float).reshape(-1)
            except (TypeError, ValueError):
                ages = np.full(len(pop), np.nan)
            if len(ages) != len(pop):
                ages = np.full(len(pop), np.nan)
            ages = np.where(np.isfinite(ages), ages, float(default_age))
            pop.set("age", ages)
            return pop

        def _advance(self, infills=None, **kwargs):
            tau = self.aging_tau
            if not self._aging_initialized and self.pop is not None:
                self.pop = self._ensure_ages(self.pop, tau)
                self._aging_initialized = True
            ideal, nadir = None, None
            if self.normalize:
                F = self.pop.get("F")
                ideal, nadir = F.min(axis=0), F.max(axis=0) + 1e-32
            if infills is not None:
                infills = self._ensure_ages(infills, 0.0)
                # Fresh offspring always age 0 this generation.
                infills.set("age", np.zeros(len(infills), dtype=float))
                pop = Population.merge(self.pop, infills)
            else:
                pop = self.pop
            n_survive = int(self.pop_size)
            n = len(pop)
            if n <= n_survive:
                ages = np.asarray(pop.get("age"), dtype=float).reshape(-1) + 1.0
                pop.set("age", ages)
                self.pop = pop
                return
            n_remove = n - n_survive
            ages = np.asarray(pop.get("age"), dtype=float).reshape(-1)
            contested_mask = ages >= float(tau)
            contested_idx = np.flatnonzero(contested_mask)
            protected_idx = np.flatnonzero(~contested_mask)
            if len(contested_idx) < n_remove:
                # Not enough old individuals: classic SMS fallback.
                self.pop = _sms_hv_survive(
                    self, self.problem, pop, n_survive, ideal, nadir, self.random_state
                )
            else:
                protected = pop[protected_idx] if len(protected_idx) else Population()
                contested = pop[contested_idx]
                keep_c = len(contested) - n_remove
                survived_c = _sms_hv_survive(
                    self, self.problem, contested, keep_c, ideal, nadir, self.random_state
                )
                self.pop = (
                    Population.merge(protected, survived_c)
                    if len(protected_idx)
                    else survived_c
                )
                if len(self.pop) > n_survive:
                    self.pop = _sms_hv_survive(
                        self, self.problem, self.pop, n_survive, ideal, nadir, self.random_state
                    )
            ages = np.asarray(self.pop.get("age"), dtype=float).reshape(-1) + 1.0
            self.pop.set("age", ages)

    class R2HCASurvival(Survival):
        """SMS-style fronts + R2HCA last-front removal (Shang & Ishibuchi 2020)."""

        def __init__(self, n_dirs=DEFAULT_R2HCA_N_DIRS, eps=1.0):
            super().__init__(filter_infeasible=True)
            self.n_dirs = int(max(8, n_dirs))
            self.eps = float(eps)
            self._W = None

        def _weights(self, n_obj, random_state):
            if self._W is not None and self._W.shape[1] == n_obj:
                return self._W
            rng = random_state if random_state is not None else np.random.default_rng(0)
            R = rng.normal(size=(self.n_dirs, n_obj))
            V = np.abs(R) / np.maximum(np.linalg.norm(R, axis=1, keepdims=True), 1e-32)
            self._W = V
            return self._W

        def _do(self, problem, pop, *args, n_survive=None, ideal=None, nadir=None, random_state=None, **kwargs):
            F = pop.get("F").astype(float, copy=False)
            if ideal is None:
                ideal = F.min(axis=0)
            if nadir is None:
                nadir = F.max(axis=0)
            survivors = []
            fronts = NonDominatedSorting().do(F, n_stop_if_ranked=n_survive)
            W = self._weights(problem.n_obj, random_state)
            for k, front_idx in enumerate(fronts):
                front = pop[front_idx]
                front.set("rank", k)
                if len(survivors) + len(front) <= n_survive:
                    survivors.extend(front)
                    continue
                # Split last front with R2HCA (one-shot drop of worst k for (μ+λ) speed).
                Fn = pymoo_normalize(front.get("F"), ideal, nadir)
                ref = np.full(problem.n_obj, 1.0 + self.eps)
                need_drop = len(survivors) + len(front) - int(n_survive)
                scores = _r2hca_scores(Fn, W, ref, problem.n_obj)
                order = np.argsort(scores)  # ascending: smallest contribution first
                keep = np.sort(order[need_drop:])
                survivors.extend(front[keep])
            return Population.create(*survivors)

    class R2HCAEMOA(SMSEMOA):
        """R2HCA-EMOA: SMS framework, R2 approx HV contribution (TEVC 2020)."""

        def __init__(self, *args, n_dirs=DEFAULT_R2HCA_N_DIRS, **kwargs):
            kwargs = dict(kwargs)
            kwargs["survival"] = R2HCASurvival(n_dirs=n_dirs)
            super().__init__(*args, **kwargs)

    class BandProgressSMSEMOA(SMSEMOA):
        """SMS-EMOA + band-progress protection (ND-SMS survival half).

        Unlike chronological Aging: age resets to 0 whenever band objective
        (F[:,1]) strictly improves for that individual. Only age≥τ enter HV
        removal. Keyed to the diet band metric, not wall-clock generation count.
        """

        def __init__(self, *args, nd_tau=DEFAULT_SMS_ND_TAU, **kwargs):
            super().__init__(*args, **kwargs)
            self.nd_tau = int(max(1, nd_tau))
            self._nd_initialized = False

        def _ensure_attrs(self, pop, default_age, default_band):
            ages = pop.get("age")
            bands = pop.get("band_best")
            n = len(pop)
            if ages is None or len(np.asarray(ages).reshape(-1)) != n:
                pop.set("age", np.full(n, float(default_age)))
            if bands is None or len(np.asarray(bands).reshape(-1)) != n:
                F = pop.get("F")
                if F is not None and F.shape[1] > 1:
                    pop.set("band_best", np.asarray(F[:, 1], dtype=float).copy())
                else:
                    pop.set("band_best", np.full(n, float(default_band)))
            return pop

        def _rejuvenate_on_band_progress(self, pop):
            F = pop.get("F")
            if F is None or F.shape[1] < 2:
                return pop
            ages = np.asarray(pop.get("age"), dtype=float).reshape(-1)
            best = np.asarray(pop.get("band_best"), dtype=float).reshape(-1)
            cur = np.asarray(F[:, 1], dtype=float).reshape(-1)
            improved = cur < (best - 1e-12)
            ages = ages.copy()
            best = best.copy()
            ages[improved] = 0.0
            best[improved] = cur[improved]
            pop.set("age", ages)
            pop.set("band_best", best)
            return pop

        def _advance(self, infills=None, **kwargs):
            tau = self.nd_tau
            if not self._nd_initialized and self.pop is not None:
                self.pop = self._ensure_attrs(self.pop, tau, 1e30)
                self.pop = self._rejuvenate_on_band_progress(self.pop)
                self._nd_initialized = True
            ideal, nadir = None, None
            if self.normalize:
                F = self.pop.get("F")
                ideal, nadir = F.min(axis=0), F.max(axis=0) + 1e-32
            if infills is not None:
                infills = self._ensure_attrs(infills, 0.0, 1e30)
                # Fresh offspring: age 0; band_best = current band F.
                Fi = infills.get("F")
                n_i = len(infills)
                infills.set("age", np.zeros(n_i, dtype=float))
                if Fi is not None and Fi.shape[1] > 1:
                    infills.set("band_best", np.asarray(Fi[:, 1], dtype=float).copy())
                pop = Population.merge(self.pop, infills)
            else:
                pop = self.pop
            pop = self._rejuvenate_on_band_progress(pop)
            n_survive = int(self.pop_size)
            n = len(pop)
            if n <= n_survive:
                ages = np.asarray(pop.get("age"), dtype=float).reshape(-1) + 1.0
                pop.set("age", ages)
                self.pop = pop
                return
            n_remove = n - n_survive
            ages = np.asarray(pop.get("age"), dtype=float).reshape(-1)
            contested_mask = ages >= float(tau)
            contested_idx = np.flatnonzero(contested_mask)
            protected_idx = np.flatnonzero(~contested_mask)
            if len(contested_idx) < n_remove:
                self.pop = _sms_hv_survive(
                    self, self.problem, pop, n_survive, ideal, nadir, self.random_state
                )
            else:
                protected = pop[protected_idx] if len(protected_idx) else Population()
                contested = pop[contested_idx]
                keep_c = len(contested) - n_remove
                survived_c = _sms_hv_survive(
                    self, self.problem, contested, keep_c, ideal, nadir, self.random_state
                )
                self.pop = (
                    Population.merge(protected, survived_c)
                    if len(protected_idx)
                    else survived_c
                )
                if len(self.pop) > n_survive:
                    self.pop = _sms_hv_survive(
                        self, self.problem, self.pop, n_survive, ideal, nadir, self.random_state
                    )
            ages = np.asarray(self.pop.get("age"), dtype=float).reshape(-1) + 1.0
            self.pop.set("age", ages)

    return SPUSMSEMOA, AgingSMSEMOA, R2HCAEMOA, BandProgressSMSEMOA


def _nutrient_gap_mutate_row(mask, nut, dens, lo, hi, allowed_mask, max_foods, rng):
    """One nutrient-gap add/drop/replace on a boolean row (SN/NutrientGA operator)."""
    mask = mask.copy()
    mask &= allowed_mask
    totals = mask @ nut
    deficit = np.clip(lo - totals, 0, None)
    excess = np.clip(totals - hi, 0, None)
    if deficit.sum() > excess.sum() and deficit.sum() > 0:
        k = int(np.argmax(deficit))
        off = np.flatnonzero(~mask & allowed_mask)
        if len(off):
            pick = int(off[int(np.argmax(dens[off, k]))])
            if int(mask.sum()) < max_foods:
                mask[pick] = True
            else:
                on = np.flatnonzero(mask)
                if len(on):
                    mask[int(on[int(rng.integers(0, len(on)))])] = False
                    mask[pick] = True
    elif excess.sum() > 0:
        k = int(np.argmax(excess))
        on = np.flatnonzero(mask)
        if len(on):
            mask[int(on[int(np.argmax(nut[on, k]))])] = False
    else:
        on = np.flatnonzero(mask)
        off = np.flatnonzero(~mask & allowed_mask)
        if len(on) and len(off):
            mask[int(on[int(rng.integers(0, len(on)))])] = False
            mask[int(off[int(rng.integers(0, len(off)))])] = True
    return mask


def build_pymoo_adapter(owner,allowed,seed):
    from pymoo.core.individual import Individual
    from pymoo.core.problem import Problem
    from pymoo.core.repair import Repair
    from pymoo.algorithms.moo.age import AGEMOEA
    from pymoo.algorithms.moo.age2 import AGEMOEA2
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.algorithms.moo.nsga3 import NSGA3
    from pymoo.algorithms.moo.sms import SMSEMOA
    from pymoo.algorithms.moo.rvea import RVEA
    from pymoo.algorithms.soo.nonconvex.ga import GA,FitnessSurvival,comp_by_cv_and_fitness
    from pymoo.operators.crossover.pntx import SinglePointCrossover
    from pymoo.operators.mutation.bitflip import BitflipMutation
    from pymoo.operators.selection.tournament import TournamentSelection
    if owner.name=="pymoo_agemoea2_bronze":
        _install_agemoea2_geometry_guards()
    values=BronzeBinaryProblemValues(owner,allowed)
    n=owner.n_rows
    G,_,_=values.evaluate(np.zeros((1,n),dtype=bool))
    multi=owner.name in PYMOO_MULTI_METHODS
    class DietProblem(Problem):
        def __init__(self):
            super().__init__(n_var=n,n_obj=2 if multi else 1,n_ieq_constr=G.shape[1],xl=0,xu=1,vtype=bool)
        def _evaluate(self,X,out,*args,**kwargs):
            gs,b,d=values.evaluate(X)
            out["G"]=gs
            # GA: complete-BLD-first scalar. MOEA: declared conflicting soft
            # objectives (BLD shortfall vs band deviation). Shared delivery uses
            # the common observer, not method-native Pareto archives.
            out["F"]=np.column_stack((b,d)) if multi else ((b>0).astype(float)+d/(1.+d))[:,None]
    class GenericRepair(Repair):
        def _do(self,problem,X,random_state=None,**kwargs):
            rng=random_state if random_state is not None else np.random.default_rng(seed+17)
            return apply_shared_repairs(np.asarray(X,dtype=bool),food_ids=values.ids,allowed_mask=allowed,
                min_foods=owner.evaluator.spec.min_foods,max_foods=owner.evaluator.spec.max_combination_size,rng=rng)[0]
    rng=np.random.default_rng(seed+17)
    pop=init_population_in_range(owner.population_size,n,np.flatnonzero(allowed),
        min_foods=owner.evaluator.spec.min_foods,max_foods=owner.evaluator.spec.max_combination_size,rng=rng)
    pop=apply_shared_repairs(pop,food_ids=values.ids,allowed_mask=allowed,min_foods=owner.evaluator.spec.min_foods,
        max_foods=owner.evaluator.spec.max_combination_size,rng=rng)[0]
    bitflip_pvar=1./max(1,int(np.sum(allowed)))
    mutation=BitflipMutation(prob=1.,prob_var=bitflip_pvar)
    kwargs=dict(pop_size=owner.population_size,sampling=pop,repair=GenericRepair(),
        crossover=SinglePointCrossover(prob=.8),mutation=mutation,eliminate_duplicates=True)
    name=owner.name
    if name=="pymoo_ga_bronze":
        kwargs.update(selection=TournamentSelection(func_comp=comp_by_cv_and_fitness),survival=FitnessSurvival())
        algorithm=GA(**kwargs)
    elif name=="pymoo_nsga2_bronze":
        algorithm=NSGA2(**kwargs)
    elif name=="pymoo_agemoea_bronze":
        algorithm=AGEMOEA(**kwargs)
    elif name=="pymoo_agemoea2_bronze":
        algorithm=AGEMOEA2(**kwargs)
    elif name=="pymoo_smsemoa_bronze":
        algorithm=SMSEMOA(**kwargs)
    elif name in (
        "pymoo_sms_spu_bronze",
        "pymoo_sms_aging_bronze",
        "pymoo_r2hca_bronze",
        "pymoo_sms_nd_bronze",
    ):
        SPUSMSEMOA, AgingSMSEMOA, R2HCAEMOA, BandProgressSMSEMOA = _build_sms_variant_classes()
        if name=="pymoo_sms_spu_bronze":
            algorithm=SPUSMSEMOA(**kwargs)
        elif name == "pymoo_sms_aging_bronze":
            tau=int((owner.config or {}).get("sms_aging_tau", DEFAULT_SMS_AGING_TAU))
            algorithm=AgingSMSEMOA(aging_tau=tau, **kwargs)
        elif name=="pymoo_r2hca_bronze":
            n_dirs=int((owner.config or {}).get("r2hca_n_dirs", DEFAULT_R2HCA_N_DIRS))
            algorithm=R2HCAEMOA(n_dirs=n_dirs, **kwargs)
        else:
            # ND-SMS: band-progress protection + nutrient-gap mutation (domain operators).
            from pymoo.core.mutation import Mutation
            nut=values.nut.detach().cpu().numpy()
            grams=np.maximum(values.grams.detach().cpu().numpy(), 1e-9)
            dens=nut/grams[:,None]
            lo=values.lo.detach().cpu().numpy()
            hi=values.hi.detach().cpu().numpy()
            allowed_np=np.asarray(allowed,dtype=bool)
            max_foods=int(owner.evaluator.spec.max_combination_size)
            nd_rate=float((owner.config or {}).get(
                "sms_nd_nutrient_rate", DEFAULT_SMS_ND_NUTRIENT_RATE
            ))
            nd_rate=min(1.0, max(0.0, nd_rate))
            class NutrientDirectedMutation(Mutation):
                """Mix nutrient-gap edits with bit-flip; diet-domain variation for ND-SMS."""
                def __init__(self):
                    super().__init__()
                def _do(self, problem, X, random_state=None, **kw):
                    rng = random_state if random_state is not None else np.random.default_rng(seed+31)
                    Xp = np.asarray(X, dtype=bool).copy()
                    for i in range(len(Xp)):
                        if rng.random() < nd_rate:
                            Xp[i] = _nutrient_gap_mutate_row(
                                Xp[i], nut, dens, lo, hi, allowed_np, max_foods, rng
                            )
                        else:
                            # Bit-flip fallback (same intensity as BitflipMutation).
                            flip = rng.random(Xp.shape[1]) < bitflip_pvar
                            flip &= allowed_np
                            Xp[i] = np.logical_xor(Xp[i], flip)
                    return Xp
            kwargs = dict(kwargs)
            kwargs["mutation"] = NutrientDirectedMutation()
            tau=int((owner.config or {}).get("sms_nd_tau", DEFAULT_SMS_ND_TAU))
            algorithm=BandProgressSMSEMOA(nd_tau=tau, **kwargs)
    elif name in ("pymoo_rvea_bronze","pymoo_nsga3_bronze"):
        ref_dirs=_ref_dirs_for_pop(owner.population_size,n_obj=2)
        # Match population to reference set size (Das-Dennis 2-obj => pop_size points).
        kwargs["pop_size"]=len(ref_dirs)
        if name=="pymoo_rvea_bronze":
            from .rvea_wall_clock import WallClockRVEA
            algorithm=WallClockRVEA(ref_dirs,budget_clock=getattr(owner,"budget_clock",None),**kwargs)
        else:
            algorithm=NSGA3(ref_dirs,**kwargs)
    else:
        raise ValueError(f"Unsupported pymoo bronze method: {name}")
    # Inequality CV uses Individual default cv_eps=0.0 (no positive slack).
    assert float(Individual.default_config()["cv_eps"])==0.0
    algorithm.setup(DietProblem(),seed=int(seed),termination=("n_gen",10**9),verbose=False)
    return algorithm,values

class PymooBronzeGA(BaseAlgorithm):
    name="pymoo_ga_bronze"
    handles_common_observation=True
    def __init__(self,*args,population_size=200,**kwargs):
        super().__init__(*args,**kwargs)
        self.population_size=int(population_size)
    def _allowed(self,banned):
        ok=self.pool.bench_placement_allowed.astype(bool).to_numpy().copy()
        ids=self.pool.food_id.astype(int).to_numpy()
        ok &= ~np.isin(ids,list(banned))
        meals=self.pool.meal.astype(str).str.lower().to_numpy()
        groups=self.pool.food_group_code.astype(int).to_numpy()
        if self.evaluator.spec.category_presence_hard:
            for key,b in ((self.personal or {}).get("bands") or {}).items():
                if float(b["hi"])<=0:
                    _,_,major,meal=key.split("_",3)
                    ok &= ~((groups==int(major))&(meals==meal))
        return ok
    def solve(self,budget,*,banned_food_ids=None):
        from dmp4p_runtime.budget_clock import BudgetClock
        from dmp4p_runtime.observation_control import CommonTopK
        import pymoo
        clock=getattr(self,"budget_clock",None) or BudgetClock(wall_s=float(budget.wall_s));self.budget_clock=clock
        start=clock.now()
        try:
            if self.config.get("evidence_observation_mode")!="top8_common":
                raise ValueError("Published adapters require top8_common observation in this protocol")
            if getattr(self,"dual_observers",None) is None:
                raise ValueError("Published adapters require DualObservers on the shared deadline clock")
            allowed=self._allowed(banned_food_ids or set())
            if len(np.unique(self.pool.loc[allowed,"food_id"]))<self.evaluator.spec.min_foods:
                return AlgoResult(self.name,"incomplete","insufficient_unbanned_food_ids")
            algorithm,values=build_pymoo_adapter(self,allowed,self.seed)
            # The shared observer uses this real evaluator, not pymoo feasibility.
            self._evidence_real_observer=self.dual_observers
            sampler=CommonTopK(self,self.pool);self._evidence_sampler=sampler
            initialized=clock.now()
            generations=0
            age2_geometry_skips=0
            while clock.in_budget() and algorithm.has_next():
                infills=algorithm.ask()
                if infills is None:break
                algorithm.evaluator.eval(algorithm.problem,infills)
                try:
                    algorithm.tell(infills=infills)
                except ZeroDivisionError:
                    # Belt-and-suspenders if upstream geometry still singularities.
                    if self.name!="pymoo_agemoea2_bronze":
                        raise
                    age2_geometry_skips+=1
                    generations+=1
                    if algorithm.pop is not None:
                        sampler.observe(torch.as_tensor(np.asarray(algorithm.pop.get("X"),dtype=bool),device=values.device))
                    if budget.stop_at_first_feasible and self.dual_observers.n_in_budget_feasible:break
                    continue
                generations+=1
                if algorithm.pop is None:continue
                pop=np.asarray(algorithm.pop.get("X"),dtype=bool)
                # Same generation-level top-eight observation rule as custom GAs.
                sampler.observe(torch.as_tensor(pop,device=values.device))
                if budget.max_evaluations and algorithm.evaluator.n_eval>=budget.max_evaluations:break
                if budget.stop_at_first_feasible and self.dual_observers.n_in_budget_feasible:break
            clock.mark_search_end();clock.mark_finalization_end()
            success=bool(self.dual_observers.n_in_budget_feasible)
            multi=self.name in PYMOO_MULTI_METHODS
            return AlgoResult(self.name,"ok" if success else "timeout",None if success else "no_feasible_in_budget",
                timings={"init_s":initialized-start,"search_s":clock.last_search_end-initialized,"budget_overflow_s":clock.budget_overflow_s()},
                evaluation_count=int(algorithm.evaluator.n_eval),solver_version=pymoo.__version__,
                extra={"generations":generations,"implementation":"pymoo","pymoo_version":pymoo.__version__,
                    "adapter":"bronze_binary_v1","observation_scope":"shared_generation_top8_structural_order",
                    "common_observe_generations":sampler.calls,"common_observe_evaluations":sampler.checked,
                    "numeric_dtype":"float64","device":str(values.device),"budget_clock":clock.to_dict(),
                    "delivery":"common online observer; method-native Pareto/archive not used for return",
                    "constraint_handling":CONSTRAINT_HANDLING[self.name],
                    "cpu_gpu_roles":{"search_tensors":str(values.device),"pymoo_operators":"cpu","final_acceptance":"float64_evaluator"},
                    "objectives":list(MULTI_OBJECTIVES) if multi else [GA_SCALAR_OBJECTIVE],
                    "variation":"pymoo SinglePointCrossover(p=.8), BitflipMutation(prob=1,prob_var=1/n_allowed), shared generic repair",
                    "age2_geometry_skips":age2_geometry_skips,"rvea_wallclock":getattr(algorithm,"clock_diagnostics",None)})
        except Exception as e:
            # If AGE2 geometry still blows up after a ready feasible was observed, prefer ok.
            if (
                self.name=="pymoo_agemoea2_bronze"
                and isinstance(e,ZeroDivisionError)
                and getattr(self,"dual_observers",None) is not None
                and self.dual_observers.n_in_budget_feasible
            ):
                return AlgoResult(self.name,"ok",None,extra={"age2_geometry_recovered_after_feasible":True,
                    "exception":f"ZeroDivisionError:{e}"})
            return AlgoResult(self.name,"error",f"exception:{type(e).__name__}:{e}")

class PymooBronzeNSGA2(PymooBronzeGA):
    name="pymoo_nsga2_bronze"

class PymooBronzeAGEMOEA(PymooBronzeGA):
    name="pymoo_agemoea_bronze"

class PymooBronzeAGEMOEA2(PymooBronzeGA):
    name="pymoo_agemoea2_bronze"

class PymooBronzeSMSEMOA(PymooBronzeGA):
    name="pymoo_smsemoa_bronze"

class PymooBronzeSMSSPU(PymooBronzeGA):
    name="pymoo_sms_spu_bronze"

class PymooBronzeSMSAging(PymooBronzeGA):
    name="pymoo_sms_aging_bronze"

class PymooBronzeR2HCA(PymooBronzeGA):
    name="pymoo_r2hca_bronze"

class PymooBronzeSMSND(PymooBronzeGA):
    """Nutrient-Directed SMS: band-progress protection + nutrient-gap mutation."""
    name="pymoo_sms_nd_bronze"

class PymooBronzeRVEA(PymooBronzeGA):
    name="pymoo_rvea_bronze"

class PymooBronzeNSGA3(PymooBronzeGA):
    name="pymoo_nsga3_bronze"
