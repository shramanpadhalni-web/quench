"""`quench run` — execute a sealed ingot through Mill, with no model in the loop.

Demonstrates the three outcomes that matter:

    1. inputs match the sealed shape  -> Mill executes, zero model calls
    2. inputs have drifted            -> Mill declines, caller uses the agent
    3. artifact altered or revoked    -> Mill declines

Usage:
    python3 scripts/quench_run.py <ingot_id> lease-003
    python3 scripts/quench_run.py <ingot_id> lease-003 --drift
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for component in ("cast", "assay", "vault", "mill"):
    sys.path.insert(0, str(ROOT / component / "src"))

from mill.adapters.mcp_invoker import McpToolInvoker  # noqa: E402
from mill.executor import Mill  # noqa: E402
from vault.adapters.filesystem_repository import FilesystemRepository  # noqa: E402

LEASE = ROOT / "examples" / "lease-abstraction"
VENV_PY = str(ROOT / ".venv" / "bin" / "python")

#: Live inputs for the six-step lease workflow, built from the sealed shapes.
def lease_inputs(document_id: str, drift: bool = False) -> list[dict]:
    text_placeholder = (LEASE / "synthetic_data" / f"{document_id}.txt").read_text()
    steps = [
        {"document_id": document_id},
        {"text": text_placeholder, "clause_type": "term"},
        {"text": text_placeholder, "clause_type": "annual_rent"},
        {"text": text_placeholder, "clause_type": "escalation"},
        {"text": text_placeholder, "clause_type": "renewal"},
        {"document_id": document_id, "record": {}},
    ]
    if drift:
        # Exactly the kind of change that should stop execution: a new field
        # appears in step 0's input. The value is harmless; the *shape* is not.
        steps[0] = {"document_id": document_id, "tenant_hint": "acme"}
    return steps


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2

    ingot_id, document_id = argv[1], argv[2]
    drift = "--drift" in argv

    vault = FilesystemRepository()
    ingot = vault.get(ingot_id)
    if ingot is None:
        print(f"No ingot {ingot_id}. Available:", file=sys.stderr)
        for candidate in vault.list():
            print(f"  {candidate.ingot_id}  ({len(candidate)} steps)", file=sys.stderr)
        return 1

    invoker = McpToolInvoker(
        command=[VENV_PY, str(LEASE / "backend" / "mcp_tools.py")],
        server_name="lease-tools",
    )
    mill = Mill(invoker=invoker)

    inputs = lease_inputs(document_id, drift=drift)
    # Step 5 writes the record the earlier steps extracted.
    print(f"ingot     {ingot.ingot_id}  ({len(ingot)} steps)")
    print(f"invoker   {invoker.describe()}")
    print(f"inputs    {document_id}{'  [MUTATED - expect drift]' if drift else ''}")
    print()

    result = mill.execute(ingot, inputs)
    print(result.describe())

    if result.drift_report and not result.drift_report.matches:
        print()
        print(result.drift_report.describe())
        print()
        print("-> falling through to the live agent; Kernel would demote to Shadow.")
        return 0

    if result.executed:
        print()
        for step in result.steps:
            status = "ok " if step.ok else "ERR"
            summary = step.error or json.dumps(step.output, default=str)[:90]
            print(
                f"  [{step.index}] {status} {step.tool_name.split('/')[-1]:<16} "
                f"{step.duration_ms:6.1f}ms  {summary}"
            )
        print()
        print(f"model calls: {result.model_calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
