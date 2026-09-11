"""Faithful reimplementation of the published control-flow-only criterion.

**This is the comparison baseline for the paper, not a Quench component.** It
exists to be run against the same corpus as our own verification so we can
report what a control-flow-only criterion would promote that output-purity
checking rejects.

Source criterion — Malik, *Progressive Crystallization*, arXiv 2607.07052,
Table II, Type 3 -> Type 2 promotion:

    >= 10 successful runs
    zero safety violations
    >= 90% of runs produce the same action sequence
    all auto-generated acceptance tests pass

Operationalised here as the preregistration (§7) commits:

    >= 10 successful traces
    identical step count across traces
    >= 90% of traces share the same per-position input structural signature

**Written 2026-09-11, before any purity statistic was computed**, per the
preregistration's requirement that the baseline cannot be tuned after the
result is known. See `docs/paper/PREREGISTRATION.md`.

Ambiguities in the published description, and our reading:

1. *"the same action sequence"* — we read "action" as one operation and compare
   input structural signatures, not raw input values. Comparing raw values would
   make the criterion trivially strict (no two runs share a document id) and no
   system could promote anything. The structural reading is the charitable one.
2. *"zero safety violations"* — not reproducible outside the original
   environment. We treat every corpus trace as violation-free, which makes the
   baseline *more* permissive. Stated in the paper.
3. *">= 90%"* — applied per step position independently: a step passes if at
   least 90% of traces agree on its signature. A workflow passes if every
   position passes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

#: Published thresholds. Do not tune.
MIN_TRACES = 10
AGREEMENT_THRESHOLD = 0.90


@dataclass(frozen=True)
class BaselineVerdict:
    """What the control-flow-only criterion decides, and why."""

    promoted: bool
    reason: str
    trace_count: int = 0
    step_count: int = 0
    #: Positions that met the agreement threshold — the steps this criterion
    #: would seal. Purity is never consulted.
    stable_positions: tuple[int, ...] = ()

    def __bool__(self) -> bool:
        return self.promoted


def evaluate(traces: list) -> BaselineVerdict:
    """Apply the published criterion to a set of traces of one workflow.

    ``traces`` are ``cast.compiler.trace.Trace`` objects. Imported lazily by the
    caller so this module has no dependency on Quench's own compiler beyond the
    duck-typed ``operations()`` method.
    """
    if len(traces) < MIN_TRACES:
        return BaselineVerdict(
            False,
            f"needs >= {MIN_TRACES} traces, has {len(traces)}",
            trace_count=len(traces),
        )

    sequences = [t.operations() for t in traces]

    counts = Counter(len(s) for s in sequences)
    modal_length, modal_count = counts.most_common(1)[0]
    if modal_count < len(sequences):
        # The published criterion says "same action sequence" — a differing step
        # count cannot be the same sequence at any agreement level.
        return BaselineVerdict(
            False,
            f"step count diverges: {dict(counts)}",
            trace_count=len(traces),
        )

    stable: list[int] = []
    for position in range(modal_length):
        signatures = Counter(seq[position].signature for seq in sequences)
        _, top = signatures.most_common(1)[0]
        if top / len(sequences) >= AGREEMENT_THRESHOLD:
            stable.append(position)

    if len(stable) < modal_length:
        unstable = [i for i in range(modal_length) if i not in stable]
        return BaselineVerdict(
            False,
            f"positions {unstable} below {AGREEMENT_THRESHOLD:.0%} agreement",
            trace_count=len(traces),
            step_count=modal_length,
            stable_positions=tuple(stable),
        )

    return BaselineVerdict(
        True,
        f"{len(traces)} traces, {modal_length} steps, all positions "
        f">= {AGREEMENT_THRESHOLD:.0%} agreement",
        trace_count=len(traces),
        step_count=modal_length,
        stable_positions=tuple(stable),
    )
