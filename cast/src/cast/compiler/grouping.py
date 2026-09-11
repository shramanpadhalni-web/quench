"""Cluster traces into candidate workflows before compiling.

A trace source hands us every session it ever recorded. It does not know which
sessions belong to which workflow — that is not information the runtime has.
So the compiler must discover the grouping itself.

Two traces belong to the same candidate workflow when their **operation
signature sequence** is identical: same length, same per-position signature.
That is the same equivalence relation `trace_diff` uses to accept a candidate,
applied one level up to partition the corpus.

This matters in practice. Our first real corpus contained 23 sessions: 20 from
the lease extractor (6 operations each) and 3 left over from failed test runs
(1 and 2 operations). Compiling them as one set correctly reported divergence
and produced nothing. Clustering first yields the real candidate.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .trace import Trace
from .typed_ir import stable_hash


@dataclass(frozen=True)
class TraceGroup:
    """A set of traces sharing one operation signature sequence."""

    key: str
    traces: tuple[Trace, ...]

    @property
    def step_count(self) -> int:
        return len(self.traces[0].operations()) if self.traces else 0

    @property
    def tool_sequence(self) -> tuple[str, ...]:
        if not self.traces:
            return ()
        return tuple(op.tool_name for op in self.traces[0].operations())

    @property
    def label(self) -> str:
        """Human-readable name, taken from the agent's own stated intent."""
        for op in self.traces[0].operations():
            if op.purpose:
                return op.purpose
        return " -> ".join(self.tool_sequence) or "(empty)"

    def __len__(self) -> int:
        return len(self.traces)


def group_traces(traces: list[Trace]) -> list[TraceGroup]:
    """Partition traces by operation signature sequence, largest group first.

    Traces with no operations are dropped: a session that recorded no tool call
    is either a narrated (fabricated) run or a pure conversation, and neither is
    a workflow. This implements the corpus exclusion rule directly.
    """
    buckets: dict[str, list[Trace]] = defaultdict(list)

    for trace in traces:
        operations = trace.operations()
        if not operations:
            continue
        key = stable_hash([op.signature for op in operations])
        buckets[key].append(trace)

    groups = [TraceGroup(key=k, traces=tuple(v)) for k, v in buckets.items()]
    groups.sort(key=len, reverse=True)
    return groups
