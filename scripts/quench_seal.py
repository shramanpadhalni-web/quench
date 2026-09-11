"""`quench seal` — verify a candidate workflow and, if it passes, sign it.

Demonstrates the full pipeline on the real corpus:

    discover -> verify (branching AND purity) -> sign -> store

The interesting outcome is a **refusal**. The governance workflow passes the
published control-flow-only criterion and is rejected here, because step 4's
output carries a timestamp that differs on every run for identical input.
Sealing it would produce an artifact that replays a frozen timestamp forever.

Usage:
    python3 scripts/quench_seal.py            # report on every candidate
    python3 scripts/quench_seal.py 0          # seal candidate 0
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for component in ("cast", "assay", "vault", "mill"):
    sys.path.insert(0, str(ROOT / component / "src"))

from assay.hallmark.signer import Signer  # noqa: E402
from assay.purity import oracle  # noqa: E402
from assay.strategies import baseline_controlflow_strategy as baseline  # noqa: E402
from cast.adapters.hook_trace_adapter import HookTraceAdapter  # noqa: E402
from cast.compiler.grouping import group_traces  # noqa: E402
from cast.compiler.ir_builder import CompilationRejected, build_cast  # noqa: E402
from vault.adapters.filesystem_repository import FilesystemRepository  # noqa: E402
from vault.models.ingot_artifact import from_cast  # noqa: E402

MIN_TRACES = 10


def assess(group) -> tuple[bool, list[str], list[str]]:
    """Run both gates. Returns (sealable, passed_strategies, refusals)."""
    traces = list(group.traces)
    passed: list[str] = []
    refusals: list[str] = []

    control_flow = baseline.evaluate(traces)
    if control_flow:
        passed.append("no_branching")
    else:
        refusals.append(f"branching: {control_flow.reason}")

    verdict = oracle.evaluate(traces)
    impure = verdict.impure_steps
    if impure:
        for step in impure:
            refusals.append(
                f"purity: step {step.position} ({step.tool_name.split('/')[-1]}) "
                f"produced {step.distinct_outputs} distinct outputs for identical "
                f"input across {step.trace_count} traces"
            )
    else:
        passed.append("purity")

    return (not refusals), passed, refusals


def main(argv: list[str]) -> int:
    source = HookTraceAdapter()
    groups = [g for g in group_traces(source.fetch_traces()) if len(g) >= MIN_TRACES]

    if not groups:
        print("No candidate workflow has enough traces.", file=sys.stderr)
        return 1

    selected = int(argv[1]) if len(argv) > 1 else None

    for index, group in enumerate(groups):
        if selected is not None and index != selected:
            continue

        name = " -> ".join(t.split("/")[-1] for t in group.tool_sequence)
        sealable, passed, refusals = assess(group)

        print("=" * 70)
        print(f"CANDIDATE [{index}]  {len(group)} traces, {group.step_count} steps")
        print(f"  {name}")
        print()

        if not sealable:
            print("  REFUSED — not sealed")
            for refusal in refusals:
                print(f"    {refusal}")
            if passed:
                print(f"  (passed: {', '.join(passed)})")
            print()
            print("  A control-flow-only criterion would promote this workflow.")
            print("  Output purity is what stops it.")
            print()
            continue

        try:
            cast = build_cast(
                list(group.traces), minimum=MIN_TRACES, source=source.describe()
            )
        except CompilationRejected as exc:
            print(f"  REFUSED — {exc}\n")
            continue

        hallmark = Signer().sign(
            cast, verified_by=tuple(passed), trace_source=source.describe()
        )
        ingot = from_cast(cast, hallmark, metadata={"tools": list(group.tool_sequence)})
        path = FilesystemRepository().put(ingot)

        print(f"  SEALED — verified by {', '.join(passed)}")
        print(f"    ingot     {ingot.ingot_id}")
        print(f"    steps     {len(ingot)}")
        print(f"    signature {hallmark.signature_hex[:32]}...")
        print(f"    sealed at {hallmark.provenance.sealed_at}")
        print(f"    written   {path}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
