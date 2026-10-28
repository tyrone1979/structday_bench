"""P0 breeding structure: overall envelope with documented energy scaling.

E-P protocol: Full uses person-conditioned bands for breeding; P0 uses the
overall (non-stratum) envelope for breeding only. Shared candidate pool,
hi<=0 hard bans and final evaluation against the reference personal bands
must not change.

Energy scale rule (same as ``resolve_personal_category_structure``):
  person_g = expected_total_g from calorie mid (or explicit total_g_ref);
  scale = clip(person_g / ref_total_g, g_scale_clip);
  band endpoints multiplied by scale. For P0, envelope_src is forced to
  ``overall`` by omitting sex/BMI/age stratum keys (``bmi=None``).
"""
from __future__ import annotations

from typing import Any, Optional

from algo.structure_category import resolve_personal_category_structure


def resolve_p0_breeding_structure(
    model: dict[str, Any],
    *,
    calorie_lo: Optional[float] = None,
    calorie_hi: Optional[float] = None,
    total_g_ref: Optional[float] = None,
    g_scale_clip: tuple[float, float] = (0.55, 2.4),
) -> dict[str, Any]:
    """Return overall-envelope bands for breeding selection (not for hard bans)."""
    out = resolve_personal_category_structure(
        model,
        sex=None,
        bmi=None,
        age=None,
        total_g_ref=total_g_ref,
        calorie_lo=calorie_lo,
        calorie_hi=calorie_hi,
        g_scale_clip=g_scale_clip,
    )
    if out.get("stratum") != "overall":
        raise ValueError(
            f"P0 resolver must use overall envelope, got stratum={out.get('stratum')!r}"
        )
    out = dict(out)
    out["p0_breeding"] = True
    out["p0_rule"] = (
        "overall envelope; energy scale from calorie mid / ref_total_g; "
        "evaluation still uses reference personal bands; pool/hi<=0 unchanged"
    )
    return out
