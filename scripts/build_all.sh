#!/usr/bin/env bash
# Lint, typecheck, test everything.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="./.venv/bin/python"
[ -x "$PY" ] || { echo "Run ./scripts/setup.sh first."; exit 1; }

failed=0
for c in cast assay vault mill saga kernel pack exchange; do
  [ -d "$c/tests" ] || continue
  echo "==> $c"
  (cd "$c" && PYTHONPATH=src ../.venv/bin/python -m pytest tests/ -q) || failed=1
done

exit $failed
