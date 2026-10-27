#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../manuscript"
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
echo "Built manuscript/main.pdf"
