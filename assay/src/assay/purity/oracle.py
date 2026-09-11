"""Ground truth for output purity, determined empirically from a corpus.

The oracle answers: **given N traces of one workflow, does this step produce
byte-identical output every time?**

It requires a corpus and so cannot run in production — that is the detector's
job (`detector.py`). The oracle establishes the truth the detector is measured
against, and the gap between them is one of the paper's two results.

Definitions are fixed by `docs/paper/PREREGISTRATION.md` §2 and must not drift:

- **Control-flow-stable step** — a position whose input structural signature is
  identical across *all* traces in a convergent set.
- **Impure step** — a control-flow-stable step whose serialised output is not
  byte-identical across all traces in that set.

Note the asymmetry, and that it is deliberate: a step is judged impure only when
its *input shape is stable*. A step whose inputs differ is expected to produce
differing output, and calling that impure would be meaningless.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def serialise(value: Any) -> str:
    """Canonical serialisation for output comparison.

    Sorted keys and no whitespace, so formatting differences never masquerade as
    impurity. Anything unserialisable falls back to ``repr``.
    """
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=repr)
    except (TypeError, ValueError):
        return repr(value)


def _input_repeats(sequences: list, position: int, key: str) -> bool:
    """True when this exact input value occurs in more than one trace.

    Purity is only observable where an input recurs: a single occurrence gives
    nothing to compare against. See DEVIATION D1.
    """
    seen = 0
    for sequence in sequences:
        if serialise(sequence[position].payload) == key:
            seen += 1
            if seen > 1:
                return True
    return False


@dataclass(frozen=True)
class StepVerdict:
    """The oracle's judgement on one step position."""

    position: int
    tool_name: str
    control_flow_stable: bool
    impure: bool
    distinct_outputs: int
    trace_count: int
    #: Whether any input value recurred, making purity observable at all.
    observable: bool = False
    #: How many distinct input values recurred across traces.
    repeated_inputs: int = 0
    purpose: str | None = None
    #: Two differing outputs for the SAME input, for the paper's examples.
    sample_a: str = ""
    sample_b: str = ""

    @property
    def classification(self) -> str:
        if not self.control_flow_stable:
            return "unstable"
        if not self.observable:
            return "unobservable"
        return "impure" if self.impure else "pure"


@dataclass(frozen=True)
class WorkflowVerdict:
    """The oracle's judgement on one workflow."""

    trace_count: int
    step_count: int
    steps: tuple[StepVerdict, ...] = field(default_factory=tuple)

    @property
    def control_flow_stable_steps(self) -> tuple[StepVerdict, ...]:
        return tuple(s for s in self.steps if s.control_flow_stable)

    @property
    def observable_steps(self) -> tuple[StepVerdict, ...]:
        """Control-flow-stable steps where some input value recurred.

        The H1 denominator, per DEVIATION D1: purity cannot be judged for a step
        whose inputs never repeat.
        """
        return tuple(s for s in self.steps if s.control_flow_stable and s.observable)

    @property
    def impure_steps(self) -> tuple[StepVerdict, ...]:
        return tuple(s for s in self.steps if s.impure)

    @property
    def impurity_rate(self) -> float:
        """Impure steps as a fraction of *observable* steps. H1 predicts 20%."""
        observable = self.observable_steps
        if not observable:
            return 0.0
        return len(self.impure_steps) / len(observable)


def evaluate(traces: list) -> WorkflowVerdict:
    """Apply the oracle to a set of traces of one workflow."""
    if not traces:
        return WorkflowVerdict(trace_count=0, step_count=0)

    sequences = [t.operations() for t in traces]
    outputs = [[c.tool_response for c in t.calls] for t in traces]

    lengths = {len(s) for s in sequences}
    if len(lengths) != 1:
        # Not a convergent set; the oracle is undefined. Callers group first.
        return WorkflowVerdict(trace_count=len(traces), step_count=0)
    step_count = lengths.pop()

    # A tool call may expand into several operations; map operation index back
    # to the call that produced it, so output comparison uses the right response.
    call_of_operation: list[int] = []
    for call_index, call in enumerate(traces[0].calls):
        for _ in call.operations():
            call_of_operation.append(call_index)

    steps: list[StepVerdict] = []
    for position in range(step_count):
        signatures = {seq[position].signature for seq in sequences}
        stable = len(signatures) == 1

        call_index = (
            call_of_operation[position]
            if position < len(call_of_operation)
            else position
        )

        # DEVIATION D1 (2026-09-11): impurity is judged within groups of traces
        # sharing identical input VALUES, not merely identical input shape.
        # Different inputs legitimately produce different outputs; scoring that
        # as impurity measures the corpus's diversity, not the step's purity.
        by_input: dict[str, set[str]] = {}
        for trace_index, sequence in enumerate(sequences):
            key = serialise(sequence[position].payload)
            out = (
                serialise(outputs[trace_index][call_index])
                if call_index < len(outputs[trace_index])
                else ""
            )
            by_input.setdefault(key, set()).add(out)

        # Only inputs seen more than once can reveal impurity.
        repeated = {k: v for k, v in by_input.items() if len(v) >= 1}
        observable = [k for k in by_input if _input_repeats(sequences, position, k)]

        impure = stable and any(len(by_input[k]) > 1 for k in observable)
        distinct = sorted({o for outs in by_input.values() for o in outs})

        # Surface a differing pair from a single input group, not across groups.
        sample_a = sample_b = ""
        for key in observable:
            outs = sorted(by_input[key])
            if len(outs) > 1:
                sample_a, sample_b = outs[0], outs[1]
                break
        steps.append(
            StepVerdict(
                position=position,
                tool_name=sequences[0][position].tool_name,
                purpose=sequences[0][position].purpose,
                control_flow_stable=stable,
                impure=impure,
                observable=bool(observable),
                repeated_inputs=len(observable),
                distinct_outputs=len(distinct),
                trace_count=len(traces),
                sample_a=(sample_a or (distinct[0] if distinct else ""))[:300],
                sample_b=sample_b[:300],
            )
        )

    return WorkflowVerdict(
        trace_count=len(traces), step_count=step_count, steps=tuple(steps)
    )
