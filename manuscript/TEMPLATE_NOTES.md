# Template notes (preprint → IEEE Access)

## Current draft

`main.tex` uses the CTAN **IEEEtran** journal class (`\documentclass[journal]{IEEEtran}`), which matches the two-column layout used for preprint and is close to Access formatting.

The official Access zip could not be fetched non-interactively from IEEE Template Selector in this environment (login / selector API). Before Access submission:

1. Open [IEEE Template Selector](https://template-selector.ieee.org/).
2. Choose **IEEE Access → Original Research → LaTeX**.
3. Download the zip; unzip into `manuscript/access_official/`.
4. Move content into `ieeeaccess.cls` + required PNGs; switch the document class to `\documentclass{ieeeaccess}` as in the sample.
5. Ensure author biographies appear after references (Access requirement).
6. Submit matching `.tex`/source bundle and PDF (≤40 MB).

## Checklist pointers

- ORCID for submitting author; short bios for all authors.
- Grammar check (Access desk-rejects weak English).
- Do not claim a new algorithm in this paper.
