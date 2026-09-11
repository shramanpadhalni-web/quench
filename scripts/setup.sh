#!/usr/bin/env bash
# One command, working environment. This is a contract - if it ever grows an
# "and then manually..." step, fix the script, not the docs.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

case "$(uname -s)" in
  Linux|Darwin) ;;
  *) echo "ERROR: Quench requires Linux or macOS. On Windows use WSL2."
     echo "See docs/adr/0005-linux-required-for-sandbox-parity.md"; exit 1 ;;
esac

echo "==> Python virtual environment"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q pytest

echo "==> Installing components (editable)"
for c in cast assay vault mill saga kernel pack exchange; do
  ./.venv/bin/pip install -q -e "$ROOT/$c" 2>/dev/null || echo "    skipped $c"
done

echo "==> Trace hooks"
./scripts/install_hooks.sh

echo
echo "Done. Next:"
echo "  kirocrew doctor      verify Crew is healthy"
echo "  kirocrew restart     load the trace hooks"
echo "  ./scripts/build_all.sh"
