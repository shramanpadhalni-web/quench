#!/usr/bin/env bash
# Build the paper.
#
#   sudo apt-get install texlive-latex-base texlive-latex-recommended \
#                        texlive-fonts-recommended texlive-pictures
#
# texlive-pictures is the one that trips people: TikZ is NOT in
# texlive-latex-recommended, despite the name.
set -euo pipefail
cd "$(dirname "$0")"
pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null
pdflatex -interaction=nonstopmode main.tex >/dev/null
echo "main.pdf  $(grep -oE "\(([0-9]+) pages" main.log | head -1 | tr -d "(")"
