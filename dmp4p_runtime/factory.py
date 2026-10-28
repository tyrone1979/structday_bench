"""Construction of the released StructDay-Bench baseline adapters.

This public module deliberately contains only the adapters listed in the
StructDay-Bench protocol.  It is not a distribution of unrelated research
algorithms from the parent development repository.
"""
from dmp4p_runtime.algorithms.cpsat_band import CPSATBand
from dmp4p_runtime.algorithms.pymoo_bronze import (
    PymooBronzeGA,PymooBronzeNSGA2,PymooBronzeAGEMOEA,
    PymooBronzeAGEMOEA2,PymooBronzeSMSEMOA,PymooBronzeSMSSPU,PymooBronzeSMSAging,
    PymooBronzeR2HCA,PymooBronzeSMSND,
    PymooBronzeRVEA,PymooBronzeNSGA3,
)
PYMOO_METHODS=(
    "pymoo_ga_bronze","pymoo_nsga2_bronze","pymoo_agemoea_bronze",
    "pymoo_agemoea2_bronze","pymoo_smsemoa_bronze","pymoo_sms_spu_bronze",
    "pymoo_sms_aging_bronze","pymoo_r2hca_bronze","pymoo_sms_nd_bronze",
    "pymoo_rvea_bronze","pymoo_nsga3_bronze",
)
_PYMOO_CLS={
    "pymoo_ga_bronze":PymooBronzeGA,
    "pymoo_nsga2_bronze":PymooBronzeNSGA2,
    "pymoo_agemoea_bronze":PymooBronzeAGEMOEA,
    "pymoo_agemoea2_bronze":PymooBronzeAGEMOEA2,
    "pymoo_smsemoa_bronze":PymooBronzeSMSEMOA,
    "pymoo_sms_spu_bronze":PymooBronzeSMSSPU,
    "pymoo_sms_aging_bronze":PymooBronzeSMSAging,
    "pymoo_r2hca_bronze":PymooBronzeR2HCA,
    "pymoo_sms_nd_bronze":PymooBronzeSMSND,
    "pymoo_rvea_bronze":PymooBronzeRVEA,
    "pymoo_nsga3_bronze":PymooBronzeNSGA3,
}
SUPPORTED_METHODS=("cpsat_band",*PYMOO_METHODS)

def make_e1a_algorithm(name,*,snap,evaluator,cfg,device,seed,v2_population_size=1000,ga_population_size=200,cpsat_workers=1):
    if cfg.get("evidence_population_size") is not None:
        ga_population_size=int(cfg["evidence_population_size"])
    kwargs=dict(pool=snap["pool"],target_dict=snap["target"],evaluator=evaluator,config=cfg,cell_ranges=snap.get("cell_ranges_restored"),personal=snap.get("personal"),device=device,seed=int(seed))
    if name in _PYMOO_CLS:
        algo=_PYMOO_CLS[name](population_size=ga_population_size,**kwargs)
    elif name == "cpsat_band":
        algo=CPSATBand(num_search_workers=cpsat_workers,**kwargs)
    else:raise ValueError("Unknown method: "+name)
    algo.name=name;algo._forbidden=snap.get("forbidden_cells") or []
    if cfg.get("evidence_observation_mode")=="top8_common" and not name.startswith("cpsat") and not getattr(algo,"handles_common_observation",False):
        from dmp4p_runtime.observation_control import install_common_observation
        algo=install_common_observation(algo)
    return algo
