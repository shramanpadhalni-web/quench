"""Drift detection — the check that runs before every Mill execution.

This is what makes sealing a cache rather than a promise. A sealed artifact
records the *shape* of each step's input; before executing, Mill confirms the
live input still has that shape. A new field, a changed type, different nesting
— any of these means the world has moved and the artifact no longer describes
it.

The correct response to drift is never to guess. It is to decline, hand the work
back to the live agent, and let the Kernel demote the artifact so it must earn
its confidence again.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DriftReport:
    """Whether live inputs still match what was sealed."""

    matches: bool
    step_index: int | None = None
    expected: Any = None
    actual: Any = None
    reason: str = ""

    def __bool__(self) -> bool:
        return self.matches

    def describe(self) -> str:
        if self.matches:
            return "no drift"
        return (
            f"drift at step {self.step_index}: {self.reason}\n"
            f"  sealed: {self.expected}\n"
            f"  live:   {self.actual}"
        )


def _diff_shape(expected: Any, actual: Any, path: str = "") -> str | None:
    """Return a human-readable description of the first shape difference."""
    if type(expected) is not type(actual):
        return f"{path or 'input'} type changed: {expected!r} -> {actual!r}"

    if isinstance(expected, dict):
        missing = sorted(set(expected) - set(actual))
        added = sorted(set(actual) - set(expected))
        if missing:
            return f"{path or 'input'} missing field(s): {', '.join(missing)}"
        if added:
            return f"{path or 'input'} new field(s): {', '.join(added)}"
        for key in sorted(expected):
            sub = _diff_shape(expected[key], actual[key], f"{path}.{key}" if path else key)
            if sub:
                return sub
        return None

    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path or 'input'} shape arity changed"
        for i, (e, a) in enumerate(zip(expected, actual)):
            sub = _diff_shape(e, a, f"{path}[{i}]")
            if sub:
                return sub
        return None

    if expected != actual:
        return f"{path or 'input'} changed: {expected!r} -> {actual!r}"
    return None


def check(ingot, live_inputs: list[dict]) -> DriftReport:
    """Compare live step inputs against the sealed shapes.

    ``live_inputs`` is one payload dict per sealed step, in order.
    """
    from cast.compiler.typed_ir import structural_signature

    if len(live_inputs) != len(ingot.steps):
        return DriftReport(
            matches=False,
            reason=(
                f"step count differs: sealed {len(ingot.steps)}, "
                f"live {len(live_inputs)}"
            ),
        )

    for step, payload in zip(ingot.steps, live_inputs):
        actual = structural_signature(payload)
        difference = _diff_shape(step.input_shape, actual)
        if difference:
            return DriftReport(
                matches=False,
                step_index=step.index,
                expected=step.input_shape,
                actual=actual,
                reason=difference,
            )

    return DriftReport(matches=True)
