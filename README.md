# MealRec-Bench: NHANES-derived multi-day dietary optimization benchmark

Public benchmark artifact for **structure-conditioned, fixed-portion, multi-day dietary optimization** under a wall-clock protocol.

**Intended venue path:** preprint (arXiv / TechRxiv) → **IEEE Access** (benchmark / comparative study; **no new algorithm**).

## What this repository contains

| Path | Content |
|------|---------|
| `manuscript/` | IEEE journal-format LaTeX draft (`main.tex`) + bibliography |
| `docs/DATA_PIPELINE.md` | NHANES raw XPT → cohort → targets → pools → instances |
| `protocol/` | Frozen protocol JSON and confirmatory panel selection |
| `results/` | Aggregated baseline totals (existing algorithms only) |
| `scripts/` | Helper scripts for tables / PDF build |

This repository **does not redistributing NHANES/FNDDS raw files**. Obtain upstream data from NCHS/USDA under their terms. Generated evaluation aggregates here use CC BY 4.0 where applicable.

## Manuscript claim (Access / preprint)

1. Describe how NHANES raw files become optimization **inputs**.
2. Freeze an evaluation **protocol** (budgets, panel, metrics).
3. Run **existing** MOEA / GA / CP baselines on the same instances.
4. Compare delivered days and all-band conformity; retain failures.

Method papers that introduce new search operators (e.g. BELEX) are **out of scope** for this benchmark manuscript.

## Quick build (preprint PDF)

```bash
cd manuscript
pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex
```

Before IEEE Access submission, replace the bundled `IEEEtran.cls` workflow with the official **IEEE Access** LaTeX package from the [IEEE Template Selector](https://template-selector.ieee.org/) (`ieeeaccess.cls` + logo assets). See `manuscript/TEMPLATE_NOTES.md`.

## Upstream implementation

Runtime and export scripts currently live in the research codebase `meal-rec-ai` (private / working tree). This benchmark repo holds the paper-facing protocol, tables, and manuscript. Public code extraction can be linked here when released.

## License

- Manuscript text: CC BY 4.0 (intended).
- Aggregated JSON/CSV results: CC BY 4.0.
- Upstream NHANES / FNDDS: retain NCHS / USDA terms.
