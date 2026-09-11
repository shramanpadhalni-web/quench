#!/usr/bin/env bash
# Reproduce every claim in docs/paper/RESULTS.md.
#
# One command. No agent runs, no API keys, no credits — the corpus is committed
# to this repository. If a number in the paper is not produced here, it does not
# belong in the paper.
#
#   ./scripts/reproduce.sh            full run
#   ./scripts/reproduce.sh --quiet    results only, skip the demonstrations
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="./.venv/bin/python"
QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

[ -x "$PY" ] || { echo "Run ./scripts/setup.sh first."; exit 1; }

# The corpus ships with the repo. Fall back to a live capture only if a
# developer has one and the committed copy is missing.
CORPUS="$ROOT/docs/paper/corpus/traces.jsonl"
if [ ! -f "$CORPUS" ]; then
  LIVE="${QUENCH_TRACE_FILE:-$HOME/.kiro/quench-traces/raw.jsonl}"
  if [ -f "$LIVE" ]; then
    echo "note: committed corpus missing; using live capture at $LIVE"
    CORPUS="$LIVE"
  else
    echo "FATAL: no corpus at $CORPUS and no live capture." >&2
    exit 1
  fi
fi
export QUENCH_TRACE_FILE="$CORPUS"

banner() { printf '\n%s\n%s\n%s\n' "########################################################################" "# $1" "########################################################################"; }

banner "1. CORPUS"
$PY - <<'EOF'
import json, os, collections
path = os.environ["QUENCH_TRACE_FILE"]
rows = [json.loads(l) for l in open(path) if l.strip()]
rows = [r for r in rows if r.get("hook_event_name")]
sessions = {r.get("session_id") for r in rows if r.get("session_id")}
kinds = collections.Counter(r["hook_event_name"] for r in rows)
print(f"  file       {path}")
print(f"  events     {len(rows)}")
print(f"  sessions   {len(sessions)}")
for k, v in sorted(kinds.items()):
    print(f"    {k:<20} {v}")
EOF

banner "2. HYPOTHESES (H1, H2, H3)"
$PY scripts/reproduce_paper.py

if [ "$QUIET" = 0 ]; then
  banner "3. SEAL / REFUSE"
  echo "Verification is not a paper artifact - it runs. Three workflows seal;"
  echo "one is refused because a step's output is not reproducible."
  echo
  # Seal into a scratch vault so a reproduction never touches a real one.
  export QUENCH_VAULT="$(mktemp -d)/ingots"
  export QUENCH_TRUST_DIR="$(mktemp -d)/trust"
  $PY scripts/quench_seal.py

  banner "4. MILL EXECUTION — zero model calls"
  echo "The same workflow the agent ran, executed without a model. Data-flow"
  echo "bindings were inferred from traces, not declared."
  echo
  $PY - <<'EOF'
import json, os, sys
from pathlib import Path
ROOT = Path.cwd()
for c in ("cast", "assay", "vault", "mill"):
    sys.path.insert(0, str(ROOT / c / "src"))
from mill.adapters.mcp_invoker import McpToolInvoker
from mill.executor import Mill
from vault.adapters.filesystem_repository import FilesystemRepository

LEASE = ROOT / "examples" / "lease-abstraction"
vault = FilesystemRepository()
target = next((i for i in vault.list() if len(i) == 6), None)
if target is None:
    print("  no six-step ingot in the scratch vault; skipping")
    raise SystemExit(0)

print(f"  ingot {target.ingot_id}  ({len(target)} steps)")
for s in target.steps:
    edges = ", ".join(f"{b.field}<-s{b.from_step}" for b in s.bindings) or "-"
    print(f"    [{s.index}] {s.tool_name.split('/')[-1]:<16} bindings: {edges}")

invoker = McpToolInvoker(
    command=[str(ROOT / ".venv/bin/python"), str(LEASE / "backend/mcp_tools.py")],
    server_name="lease-tools",
)
# The caller supplies only unbound fields; the rest resolve from earlier steps.
inputs = [
    {"document_id": "lease-007"},
    {"clause_type": "term"},
    {"clause_type": "annual_rent"},
    {"clause_type": "escalation"},
    {"clause_type": "renewal"},
    {"record": {"term": 0, "annual_rent": 0, "escalation": 0.0, "renewal": ""}},
]
result = Mill(invoker=invoker).execute(target, inputs)
print()
print(f"  {result.describe()}")
for step in result.steps:
    body = step.error or ""
    if step.ok:
        try:
            body = json.dumps(
                json.loads(step.output["items"][0]["Json"]["content"][0]["text"])
            )
        except Exception:
            body = str(step.output)[:70]
    print(f"    [{step.index}] {step.duration_ms:7.1f}ms  {body[:78]}")
print()
print("  ground truth (lease-007):")
for line in (LEASE / "synthetic_data/lease-007.txt").read_text().splitlines():
    if any(k in line for k in ("TERM:", "ANNUAL RENT:", "ESCALATION:", "RENEWAL")):
        print(f"    {line.strip()}")
invoker.close()
EOF

  banner "5. REFUSALS"
  $PY - <<'EOF'
import sys
from pathlib import Path
ROOT = Path.cwd()
for c in ("cast", "assay", "vault", "mill"):
    sys.path.insert(0, str(ROOT / c / "src"))
from mill.executor import Mill
from mill.ports.tool_invoker import ToolInvoker
from vault.adapters.filesystem_repository import FilesystemRepository
from vault.models.ingot_artifact import Ingot


class NeverCalled(ToolInvoker):
    def invoke(self, tool_name, payload):
        raise AssertionError("a refused execution must not reach a tool")

    def describe(self):
        return "never-called"


vault = FilesystemRepository()
ingot = next((i for i in vault.list() if len(i) == 6), None)
if ingot is None:
    raise SystemExit(0)
mill = Mill(invoker=NeverCalled())
good = [{"document_id": "lease-007"}] + [{"clause_type": "term"}] * 4 + [{"record": {}}]

import copy

# deepcopy each time: to_dict() shares nested dicts with the source ingot, so
# mutating one leaks into every later check.
tampered = copy.deepcopy(ingot.to_dict())
tampered["hallmark"]["provenance"]["trace_count"] = 9999
print("  tampered provenance :", mill.execute(Ingot.from_dict(tampered), good).refusal)

drifted = [dict(good[0], unexpected_field="x")] + good[1:]
report = mill.execute(Ingot.from_dict(copy.deepcopy(ingot.to_dict())), drifted)
print("  drifted input shape :", report.refusal.splitlines()[0])

revoked = copy.deepcopy(ingot.to_dict())
revoked["revoked"] = True
print("  revoked artifact    :", mill.execute(Ingot.from_dict(revoked), good).refusal)
EOF
fi

banner "DONE"
echo "  Narrative:        docs/paper/RESULTS.md"
echo "  Machine-readable: docs/paper/RESULTS.json"
echo "  Preregistration:  docs/paper/PREREGISTRATION.md  (frozen before collection)"
echo "  Deviations:       docs/paper/DEVIATIONS.md"
