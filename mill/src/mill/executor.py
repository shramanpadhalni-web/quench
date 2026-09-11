"""Mill — executes a sealed artifact with no model in the loop.

The order of operations here is the security model, and it is not negotiable:

    1. refuse if revoked
    2. verify the Hallmark signature
    3. drift-check live inputs against the sealed shapes
    4. only then execute, through the same tool surface an agent would use

Mill is a shortcut around the **model call**, never around the policy check.
Every step still goes out through a `ToolInvoker`, which is where governance,
sandboxing and output redaction live. An implementation that executed steps
directly — bypassing the invoker — would be faster and would void the entire
security argument.

Python for v1 (see ADR-0002 as revised). Mill walks a handful of shell and file
operations; there is no performance pressure, and a Rust binary is a per-platform
distribution problem to take on once the interface has stopped moving.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from cast.compiler import bindings

from . import drift
from .ports.tool_invoker import ToolInvoker


@dataclass(frozen=True)
class StepResult:
    index: int
    tool_name: str
    output: Any
    duration_ms: float
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class ExecutionResult:
    """What happened, and whether the caller must fall back to the agent."""

    executed: bool
    steps: tuple[StepResult, ...] = ()
    refusal: str = ""
    drift_report: drift.DriftReport | None = None
    model_calls: int = 0  # always zero; recorded so the claim is auditable
    duration_ms: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def should_fall_back(self) -> bool:
        """True when the caller must hand this work to the live agent."""
        return not self.executed or any(not s.ok for s in self.steps)

    def describe(self) -> str:
        if not self.executed:
            return f"Mill declined: {self.refusal}"
        failed = [s for s in self.steps if not s.ok]
        if failed:
            return (
                f"Mill ran {len(self.steps)} steps, {len(failed)} failed "
                f"(first: step {failed[0].index} — {failed[0].error})"
            )
        return (
            f"Mill executed {len(self.steps)} steps in {self.duration_ms:.0f}ms, "
            f"{self.model_calls} model calls"
        )


class Mill:
    """The model-free executor."""

    def __init__(self, invoker: ToolInvoker, verify_signature: bool = True) -> None:
        self.invoker = invoker
        self.verify_signature = verify_signature

    def execute(self, ingot, live_inputs: list[dict]) -> ExecutionResult:
        """Run a sealed artifact against live inputs.

        Declining is a normal outcome, not an error: it means the caller should
        use the agent path, exactly as it did before the artifact existed.
        """
        if getattr(ingot, "revoked", False):
            return ExecutionResult(
                executed=False, refusal="artifact is revoked"
            )

        if self.verify_signature:
            from assay.hallmark.signer import Hallmark, verify

            try:
                hallmark = Hallmark.from_dict(ingot.hallmark)
            except (KeyError, TypeError) as exc:
                return ExecutionResult(
                    executed=False, refusal=f"malformed hallmark: {exc}"
                )
            if not verify(hallmark):
                return ExecutionResult(
                    executed=False,
                    refusal="Hallmark signature does not verify — artifact altered",
                )
            if hallmark.provenance.skill_signature != ingot.skill_signature:
                return ExecutionResult(
                    executed=False,
                    refusal="signature covers a different Cast than this ingot holds",
                )

        started = time.perf_counter()
        results: list[StepResult] = []
        outputs: list[Any] = []

        for step, supplied in zip(ingot.steps, live_inputs):
            # Resolve data-flow bindings from earlier outputs, then merge with
            # what the caller supplied. Bound fields win: their value is defined
            # by the workflow, not by the caller.
            payload = dict(supplied)
            binding_error: str | None = None
            for binding in getattr(step, "bindings", ()):
                try:
                    payload[binding.field] = bindings.resolve(
                        outputs[binding.from_step], binding.path
                    )
                except (KeyError, IndexError, ValueError, TypeError) as exc:
                    binding_error = (
                        f"binding {binding.field} <- step {binding.from_step} "
                        f"failed: {exc}"
                    )
                    break

            if binding_error:
                results.append(
                    StepResult(
                        index=step.index,
                        tool_name=step.tool_name,
                        output=None,
                        duration_ms=0.0,
                        error=binding_error,
                    )
                )
                break

            # Drift is checked per step, on the COMPLETE payload — after
            # bindings are resolved, since a bound field is not supplied by the
            # caller and would otherwise read as a missing field.
            report = drift.check_step(step, payload)
            if not report:
                return ExecutionResult(
                    executed=False,
                    refusal=report.describe(),
                    drift_report=report,
                    steps=tuple(results),
                )

            step_started = time.perf_counter()
            try:
                output = self.invoker.invoke(step.tool_name, payload)
                error = None
            except Exception as exc:  # an invoker failure is a step failure
                output, error = None, f"{type(exc).__name__}: {exc}"

            outputs.append(output)
            results.append(
                StepResult(
                    index=step.index,
                    tool_name=step.tool_name,
                    output=output,
                    duration_ms=(time.perf_counter() - step_started) * 1000,
                    error=error,
                )
            )
            if error:
                break  # do not continue a workflow whose earlier step failed

        report = drift.DriftReport(matches=True)

        return ExecutionResult(
            executed=True,
            steps=tuple(results),
            drift_report=report,
            model_calls=0,
            duration_ms=(time.perf_counter() - started) * 1000,
            metadata={"executor": "mill", "cast_id": ingot.cast_id},
        )
