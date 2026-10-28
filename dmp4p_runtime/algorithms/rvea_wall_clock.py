"""Wall-clock progress for RVEA in a time-limited, fixed-budget interface.

The generation horizon stays large to prevent an unrelated termination rule
from ending the task. APD penalties and reference adaptation use elapsed wall
fraction instead. Flat fronts retain valid existing reference directions.
"""
import math
import numpy as np
from pymoo.algorithms.moo.rvea import RVEA,APDSurvival
from pymoo.algorithms.base.genetic import GeneticAlgorithm

class WallClockAPDSurvival(APDSurvival):
    def __init__(self,ref_dirs,budget_clock,alpha=2.0):
        super().__init__(ref_dirs,alpha=alpha)
        self.budget_clock=budget_clock
        self.progress_min=None
        self.progress_max=None
        self.progress_calls=0

    def fraction(self):
        return float(np.clip(self.budget_clock.elapsed()/self.budget_clock.wall_s,0.,1.))

    def _do(self,problem,pop,n_survive,algorithm=None,**kwargs):
        progress=self.fraction()
        self.progress_min=progress if self.progress_min is None else min(self.progress_min,progress)
        self.progress_max=progress if self.progress_max is None else max(self.progress_max,progress)
        self.progress_calls+=1
        kwargs.pop("n_gen",None);kwargs.pop("n_max_gen",None)
        return super()._do(problem,pop,n_survive,algorithm=algorithm,
            n_gen=progress,n_max_gen=1.,**kwargs)

class WallClockRVEA(RVEA):
    def __init__(self,ref_dirs,*,budget_clock,alpha=2.,adapt_freq=.1,**kwargs):
        if budget_clock is None:raise ValueError("WallClockRVEA requires the shared BudgetClock")
        self.budget_clock=budget_clock
        self.adaptation_count=0
        self.adaptation_skipped=0
        self._next_adaptation=float(adapt_freq) if adapt_freq is not None else math.inf
        survival=WallClockAPDSurvival(ref_dirs,budget_clock,alpha=alpha)
        super().__init__(ref_dirs,alpha=alpha,adapt_freq=adapt_freq,survival=survival,**kwargs)

    def _advance(self,**kwargs):
        # Use the ordinary GA update, then the budget-based RVEA schedule.
        GeneticAlgorithm._advance(self,**kwargs)
        progress=self.survival.fraction()
        if self.adapt_freq is not None and progress+1e-12>=self._next_adaptation:
            nadir=self.survival.nadir
            width=None if nadir is None else nadir-self.survival.ideal
            if width is None or not np.isfinite(width).all() or np.any(width<=1e-12):
                self.adaptation_skipped+=1
            else:
                previous_v=self.survival.V.copy();previous_gamma=self.survival.gamma.copy()
                good=False
                try:
                    with np.errstate(divide="raise",invalid="raise"):
                        self.survival.adapt()
                    good=bool(np.isfinite(self.survival.V).all() and np.isfinite(self.survival.gamma).all() and np.all(self.survival.gamma>1e-12))
                except FloatingPointError:
                    good=False
                if good:self.adaptation_count+=1
                else:
                    self.survival.V=previous_v;self.survival.gamma=previous_gamma
                    self.adaptation_skipped+=1
            self._next_adaptation=(math.floor(progress/float(self.adapt_freq))+1)*float(self.adapt_freq)

    @property
    def clock_diagnostics(self):
        return {"schedule":"elapsed_wall_fraction","alpha":float(self.survival.alpha),
            "adapt_freq":self.adapt_freq,"apd_progress_calls":self.survival.progress_calls,
            "apd_progress_min":self.survival.progress_min,"apd_progress_max":self.survival.progress_max,
            "reference_adaptations":self.adaptation_count,
            "reference_adaptations_skipped_flat_or_invalid":self.adaptation_skipped}
