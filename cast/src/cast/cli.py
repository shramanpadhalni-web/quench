"""``quench cast`` — discover candidate workflows and compile them."""

from __future__ import annotations

import argparse
import json
import sys

from .adapters.hook_trace_adapter import HookTraceAdapter
from .compiler.grouping import group_traces
from .compiler.ir_builder import CompilationRejected, build_cast


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="quench cast")
    ap.add_argument(
        "group",
        nargs="?",
        type=int,
        help="index of the group to compile; omit to list all groups",
    )
    ap.add_argument("--min-traces", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    source = HookTraceAdapter()
    traces = source.fetch_traces()

    if not traces:
        print(f"No traces found via {source.describe()}", file=sys.stderr)
        print("Nothing observed yet — run the workflow first.", file=sys.stderr)
        return 1

    groups = group_traces(traces)
    if not groups:
        print("No trace contained a tool call.", file=sys.stderr)
        print(
            "Sessions with zero tool calls are excluded: a narrated run is not "
            "an observed one.",
            file=sys.stderr,
        )
        return 1

    # No group selected — report what was discovered.
    if args.group is None:
        total = sum(len(g) for g in groups)
        print(f"{len(groups)} candidate workflow(s) across {total} traces\n")
        for i, g in enumerate(groups):
            ready = (
                "ready"
                if len(g) >= args.min_traces
                else f"needs {args.min_traces - len(g)} more"
            )
            print(f"  [{i}] {len(g):>3} traces  {g.step_count} steps  ({ready})")
            print(f"      {' -> '.join(g.tool_sequence)}")
            print(f"      {g.label[:70]}")
            print()
        print("Compile one with:  quench cast <index>")
        return 0

    if not 0 <= args.group < len(groups):
        print(f"No group {args.group}; there are {len(groups)}.", file=sys.stderr)
        return 2

    group = groups[args.group]
    try:
        cast = build_cast(
            list(group.traces),
            minimum=args.min_traces,
            source=source.describe(),
        )
    except CompilationRejected as exc:
        print(f"Not a candidate: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "cast_id": cast.cast_id,
                    "signature": cast.signature,
                    "steps": len(cast),
                    "trace_count": cast.trace_count,
                    "tools": list(group.tool_sequence),
                },
                indent=2,
            )
        )
    else:
        print(f"Cast {cast.cast_id}   {len(cast)} steps, {cast.trace_count} traces")
        print(f"  signature {cast.signature[:32]}...\n")
        for step in cast.steps:
            purpose = step.operation.purpose or "-"
            print(f"  {step.index:>3}  {step.operation.tool_name:<16} {purpose[:52]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
