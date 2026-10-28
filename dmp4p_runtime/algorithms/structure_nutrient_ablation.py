"""Clean N×S ablations for Structure-Nutrient-GA (internal mechanism evidence).

N1S1 = full method (alias of structure_nutrient_ga behavior).
N0S1 = matched-intensity random add/drop/replace; keep BLD+band selection.
N1S0 = nutrient-guided edits; keep BLD ranking; drop band from breeding sort.
N0S0 = random edits; BLD ranking only.

Shared with the full method: init, crossover, elite fraction, repairs,
hard-OK → BLD → band lex ranking, pool, hard gates, observation, return policy.
"""
from __future__ import annotations

from dmp4p_runtime.algorithms.structure_nutrient_ga import (
    StructureNutrientGA,
    matched_intensity_random_edit,
)

# Back-compat alias (tests monkeypatch this name for N0).
matched_random_edit = matched_intensity_random_edit

# name -> (nutrient_guided, band_selection)
NS_FLAGS = {
    "structure_nutrient_n1s1": (True, True),
    "structure_nutrient_n0s1": (False, True),
    "structure_nutrient_n1s0": (True, False),
    "structure_nutrient_n0s0": (False, False),
}
NS_VARIANTS = tuple(NS_FLAGS)


class StructureNutrientAblation(StructureNutrientGA):
    """Parameterized N/S ablation; ``name`` selects the flag pair."""

    def __init__(self, *args, nutrient_guided: bool = True, band_selection: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.nutrient_guided = bool(nutrient_guided)
        self.band_selection = bool(band_selection)
        self.name = {
            (True, True): "structure_nutrient_n1s1",
            (False, True): "structure_nutrient_n0s1",
            (True, False): "structure_nutrient_n1s0",
            (False, False): "structure_nutrient_n0s0",
        }[(self.nutrient_guided, self.band_selection)]

    def _fitness_batch(self, pop_t, nut_t, grams_t, banned_t):
        ranked, penalty, masks = StructureNutrientGA._fitness_batch(
            self, pop_t, nut_t, grams_t, banned_t, use_band=self.band_selection
        )
        diag = dict(self.last_structure_diagnostics or {})
        diag.update(
            {
                "nutrient_guided": self.nutrient_guided,
                "band_selection": self.band_selection,
            }
        )
        self.last_structure_diagnostics = diag
        return ranked, penalty, masks

    def _nutrient_mutate(self, masks, dens, allowed_mask, rng):
        if self.nutrient_guided:
            return StructureNutrientGA._nutrient_mutate(self, masks, dens, allowed_mask, rng)
        # N0: matched-intensity random only (alias keeps tests/monkeypatch stable).
        return matched_random_edit(masks, allowed_mask, rng, self)


def make_ns_ablation(name, **kwargs):
    if name not in NS_FLAGS:
        raise ValueError(f"Unknown N/S ablation: {name}")
    n, s = NS_FLAGS[name]
    algo = StructureNutrientAblation(nutrient_guided=n, band_selection=s, **kwargs)
    algo.name = name
    return algo
