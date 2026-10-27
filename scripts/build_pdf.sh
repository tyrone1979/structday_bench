#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../manuscript"
pdflatex -interaction=nonstopmode main.tex
# bibliography is embedded as thebibliography; second pass for refs/labels
pdflatex -interaction=nonstopmode main.tex
echo "Built manuscript/main.pdf"
