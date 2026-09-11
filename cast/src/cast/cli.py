"""``quench cast`` - compile a candidate Cast from observed traces."""

from __future__ import annotations

import argparse
import json
import sys

from .adapters.hook_trace_adapter import HookTraceAdapter
from .compiler.ir_builder import CompilationRejected, build_cast


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="quench cast")
    ap.add_argument("skill_id", nargs="?", help="session/skill id; omit for all")
    ap.add_argument("--min-traces", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    source = HookTraceAdapter()
    traces = source.fetch_traces(args.skill_id)

    if not traces:
        print(f"No traces found via {source.describe()}", file=sys.stderr)
        print("Nothing has been observed yet - run the workflow first.", file=sys.stderr)
        return 1

    try:
        cast = build_cast(traces, minimum=args.min_traces, source=source.describe())
    except CompilationRejected as exc:
        print(f"Not a candidate: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "cast_id": cast.cast_id,
            "signature": cast.signature,
            "steps": len(cast),
            "trace_count": cast.trace_count,
        }, indent=2))
    else:
        print(f"Cast {cast.cast_id}  ({len(cast)} steps, {cast.trace_count} traces)")
        for step in cast.steps:
            purpose = step.operation.purpose or "-"
            print(f"  {step.index:>3}  {step.operation.tool_name:<12} {purpose[:56]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
