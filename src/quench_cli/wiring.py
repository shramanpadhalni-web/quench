"""The composition root, as a library.

`app/backend/main.py` is the Kiro Crew App's composition root; this is the same
wiring for anyone using Quench directly — a Python project, the CLI, or the MCP
server. Both exist because Quench has two front doors, and neither should reach
into the other's.

This is still the only place (outside `app/`) permitted to import a concrete
adapter and bind it to a port.
"""

from __future__ import annotations

import os

from assay.hallmark.signer import Signer
from assay.purity import oracle
from assay.strategies import baseline_controlflow_strategy as baseline
from cast.adapters.hook_trace_adapter import HookTraceAdapter
from cast.compiler.grouping import group_traces
from cast.compiler.ir_builder import CompilationRejected, build_cast
from cast.ports.trace_source import TraceSource
from kernel.kernel import Kernel
from kernel.ports.promotion_policy import POLICIES, DefaultPolicy
from vault.adapters.filesystem_repository import FilesystemRepository
from vault.models.ingot_artifact import from_cast

MIN_TRACES = int(os.environ.get("QUENCH_MIN_TRACES", "10"))


class Quench:
    """Everything wired together. The one object a host application needs."""

    def __init__(
        self,
        traces: TraceSource | None = None,
        vault=None,
        kernel: Kernel | None = None,
        min_traces: int = MIN_TRACES,
    ) -> None:
        # Defaults are conveniences, not requirements. A host embedding Quench
        # supplies its own TraceSource -- that is the whole point of the port.
        self.traces = traces or HookTraceAdapter()
        self.vault = vault or FilesystemRepository()
        self.kernel = kernel or Kernel(policy=_policy_from_env())
        self.signer = Signer()
        self.min_traces = min_traces

    # ---------------------------------------------------------------- reads
    def candidates(self) -> list[dict]:
        rows = []
        for index, group in enumerate(group_traces(self.traces.fetch_traces())):
            record = self.kernel.observe(group.key, len(group))
            rows.append({
                "index": index,
                "skill_id": group.key,
                "state": record.state.value,
                "traces": len(group),
                "steps": group.step_count,
                "tools": [t.split("/")[-1] for t in group.tool_sequence],
                "label": group.label,
                "eligible": len(group) >= self.min_traces,
                "needs": max(0, self.min_traces - len(group)),
                "ingot_id": record.ingot_id,
                "consecutive_matches": record.consecutive_matches,
                "drift_events": record.drift_events,
            })
        return rows

    def ingots(self) -> list[dict]:
        out = []
        for i in self.vault.list():
            p = i.hallmark.get("provenance", {})
            out.append({
                "ingot_id": i.ingot_id,
                "steps": len(i),
                "revoked": i.revoked,
                "sealed_at": p.get("sealed_at"),
                "verified_by": p.get("verified_by", []),
                "trace_count": p.get("trace_count"),
                "tools": [s.tool_name.split("/")[-1] for s in i.steps],
            })
        return out

    def state(self) -> dict:
        return {
            "summary": self.kernel.summary(),
            "skills": [r.to_dict() for r in self.kernel.all()],
        }

    # --------------------------------------------------------------- verify
    def assess(self, traces) -> tuple[list[str], list[str]]:
        """Run both gates independently. Returns (passed, refusals)."""
        passed, refusals = [], []

        verdict = baseline.evaluate(traces)
        if verdict:
            passed.append("no_branching")
        else:
            refusals.append(f"branching: {verdict.reason}")

        purity = oracle.evaluate(traces)
        if purity.impure_steps:
            for step in purity.impure_steps:
                refusals.append(
                    f"purity: step {step.position} "
                    f"({step.tool_name.split('/')[-1]}) produced "
                    f"{step.distinct_outputs} distinct outputs for identical input "
                    f"across {step.trace_count} traces"
                )
        elif not purity.observable_steps:
            # No input value recurred, so purity was never actually tested.
            # Claiming it here would put "verified by: purity" in a signed
            # provenance record on the strength of zero observations -- the
            # exact overclaim this project exists to avoid.
            passed.append("purity:not-observable")
        else:
            passed.append("purity")
        return passed, refusals

    # --------------------------------------------------------------- writes
    def seal(self, index: int) -> dict:
        groups = group_traces(self.traces.fetch_traces())
        if not 0 <= index < len(groups):
            return {"error": f"no candidate {index}"}
        group = groups[index]
        traces = list(group.traces)

        passed, refusals = self.assess(traces)
        if refusals:
            return {"sealed": False, "refusals": refusals, "passed": passed}

        try:
            cast = build_cast(
                traces, minimum=self.min_traces, source=self.traces.describe()
            )
        except CompilationRejected as exc:
            return {"sealed": False, "refusals": [str(exc)], "passed": passed}

        hallmark = self.signer.sign(
            cast, verified_by=tuple(passed), trace_source=self.traces.describe()
        )
        ingot = from_cast(cast, hallmark, {"tools": list(group.tool_sequence)})
        path = self.vault.put(ingot)
        self.kernel.enter_shadow(group.key, ingot.ingot_id)

        return {
            "sealed": True,
            "ingot_id": ingot.ingot_id,
            "steps": len(ingot),
            "verified_by": passed,
            "state": "shadow",
            "path": path,
            "note": "registered for shadow comparison; not yet authorised to execute",
        }

    def shadow_result(self, skill_id: str, matched: bool) -> dict:
        r = self.kernel.record_shadow_run(skill_id, matched)
        return {"skill_id": skill_id, "state": r.state.value,
                "consecutive": r.consecutive_matches, "note": r.note}

    def drift(self, skill_id: str, reason: str = "") -> dict:
        r = self.kernel.record_drift(skill_id, reason)
        return {"skill_id": skill_id, "state": r.state.value,
                "drift_events": r.drift_events}

    def revoke(self, skill_id: str) -> dict:
        r = self.kernel.revoke(skill_id)
        if r.ingot_id:
            self.vault.revoke(r.ingot_id)
        return {"skill_id": skill_id, "state": r.state.value}


def _policy_from_env():
    name = os.environ.get("QUENCH_POLICY", "default")
    cls = POLICIES.get(name, DefaultPolicy)
    threshold = int(os.environ.get("QUENCH_PROMOTE_AFTER", "10"))
    return cls(threshold=threshold)


_APP: Quench | None = None


def build() -> Quench:
    """Process-wide instance. Callers embedding Quench should construct their
    own with their own TraceSource rather than using this."""
    global _APP
    if _APP is None:
        _APP = Quench()
    return _APP
