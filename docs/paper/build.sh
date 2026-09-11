#!/usr/bin/env bash
# Build the paper. Requires: texlive-latex-base texlive-latex-recommended
#                            texlive-fonts-recommended
set -euo pipefail
cd "$(dirname "$0")"
pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null
pdflatex -interaction=nonstopmode main.tex >/dev/null
echo "main.pdf  $(grep -oE "\(([0-9]+) pages" main.log | head -1 | tr -d "(")"
