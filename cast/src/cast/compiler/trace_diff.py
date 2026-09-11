"""Detects whether a set of traces describes one deterministic workflow.

v1 scope is deliberately hard-edged: **linear, non-branching sequences only.**
Anything whose history shows divergent tool calls is left alone. That is a
scope boundary, not a limitation to engineer around - see §13 of the brief.
"""

from __future__ import annotations

from dataclasses import dataclass

from .trace import Trace
from .typed_ir import Operation


@dataclass(frozen=True)
class DiffResult:
    """Why a trace set was or was not accepted as a candidate."""

    converged: bool
    reason: str
    operations: tuple[Operation, ...] = ()
    divergence_index: int | None = None

    def __bool__(self) -> bool:
        return self.converged


def diff_traces(traces: list[Trace], minimum: int = 5) -> DiffResult:
    """Compare N traces; accept only if every one has the same operation shape.

    Errors are phrased so an agent or a human reading agent output can act on
    them directly - see §11 of the brief. Never "verification failed", always
    what is missing and how many more runs it needs.
    """
    if len(traces) < minimum:
        return DiffResult(
            False,
            f"needs {minimum} clean traces to form a candidate, has {len(traces)}; "
            f"{minimum - len(traces)} more required",
        )

    sequences = [t.operations() for t in traces]
    reference = sequences[0]

    for other in sequences[1:]:
        if len(other) != len(reference):
            return DiffResult(
                False,
                f"step count diverges ({len(reference)} vs {len(other)}); "
                "the workflow branches and cannot be sealed in v1",
            )

    for i, ref_op in enumerate(reference):
        for other in sequences[1:]:
            if other[i].signature != ref_op.signature:
                return DiffResult(
                    False,
                    f"step {i} diverges: {ref_op.tool_name} input shape differs "
                    "across runs; the workflow branches and cannot be sealed in v1",
                    divergence_index=i,
                )

    return DiffResult(
        True,
        f"{len(traces)} traces converge on {len(reference)} operations",
        operations=tuple(reference),
    )
