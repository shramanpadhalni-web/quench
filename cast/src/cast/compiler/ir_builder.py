"""Builds a Cast from a converged trace set."""

from __future__ import annotations

from .bindings import infer as infer_bindings
from .trace import Trace
from .trace_diff import diff_traces
from .typed_ir import Cast, CastStep, stable_hash


class CompilationRejected(Exception):
    """Raised when a trace set is not a valid Cast candidate.

    Carries an actionable message. Never blocks the agent - a rejection means
    "keep observing", not "something broke".
    """


def build_cast(traces: list[Trace], minimum: int = 5, source: str = "unknown") -> Cast:
    diff = diff_traces(traces, minimum=minimum)
    if not diff:
        raise CompilationRejected(diff.reason)

    # Data flow is discovered from the traces, not declared. A binding that
    # does not hold in every trace is not kept.
    edges = infer_bindings(traces)
    steps = tuple(
        CastStep(index=i, operation=op, bindings=edges.get(i, ()))
        for i, op in enumerate(diff.operations)
    )
    skill_signature = stable_hash([s.signature for s in steps])

    return Cast(
        cast_id=skill_signature[:16],
        skill_signature=skill_signature,
        steps=steps,
        trace_count=len(traces),
        source=source,
        metadata={"sessions": [t.session_id for t in traces], "diff": diff.reason},
    )
