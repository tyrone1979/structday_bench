import numpy as np
from pymoo.core.population import Population
from pymoo.core.problem import Problem
from pymoo.algorithms.moo.rvea import APDSurvival
from dmp4p_runtime.algorithms.rvea_wall_clock import WallClockAPDSurvival,WallClockRVEA
class Clock:
 wall_s=30.
 value=0.
 def elapsed(self):return self.value

def test_apd_uses_elapsed_fraction_not_dummy_generation(monkeypatch):
 clock=Clock();clock.value=15.;survival=WallClockAPDSurvival(np.array([[1.,0.],[0.,1.]]),clock)
 captured={}
 def probe(self,problem,pop,n_survive,**kw):captured.update(kw);return pop
 monkeypatch.setattr(APDSurvival,"_do",probe)
 population=Population.new(F=np.array([[1.,2.],[2.,1.]]))
 survival._do(Problem(n_var=1,n_obj=2),population,2)
 assert captured["n_gen"]==.5 and captured["n_max_gen"]==1.
 assert survival.progress_max==.5

def test_wall_fraction_is_clamped_and_requires_clock():
 clock=Clock();survival=WallClockAPDSurvival(np.array([[1.,0.],[0.,1.]]),clock)
 clock.value=50.;assert survival.fraction()==1.
 clock.value=-5.;assert survival.fraction()==0.
 try:WallClockRVEA(np.array([[1.,0.],[0.,1.]]),budget_clock=None)
 except ValueError:pass
 else:raise AssertionError("shared clock is required")
