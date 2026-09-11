#!/usr/bin/env bash
# One command, every number in the paper.
set -euo pipefail
cd "$(dirname "$0")/.."
exec ./.venv/bin/python scripts/reproduce_paper.py "$@"
