"""End to end with no Kiro anywhere: OTel in, Mill out.

A framework-agnostic claims workflow. The "agent" here stands in for LangChain,
LlamaIndex, AgentSquad or a hand-written loop — all that matters is that it
calls tools and emits OTel GenAI spans, which every instrumented framework does.

    python examples/claims-mesh/demo.py

What it demonstrates:

    1. an agent runs a claims workflow 12 times, emitting OTel spans
    2. Quench observes the spans and discovers the workflow unsupervised
    3. Quench infers the data flow between steps from the spans alone
    4. Assay verifies it; Hallmark signs it; the Vault stores it
    5. Mill executes it against the SAME tool functions, with no model

No Kiro, no MCP, no hooks. Two adapters and the core.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for component in ("cast", "assay", "vault", "mill", "kernel"):
    sys.path.insert(0, str(ROOT / component / "src"))

from assay.hallmark.signer import Signer                                # noqa: E402
from assay.purity import oracle                                         # noqa: E402
from assay.strategies import baseline_controlflow_strategy as baseline  # noqa: E402
from cast.adapters.otel_trace_adapter import OtelTraceAdapter           # noqa: E402
from cast.compiler.grouping import group_traces                         # noqa: E402
from cast.compiler.ir_builder import build_cast                         # noqa: E402
from mill.adapters.callable_invoker import CallableInvoker              # noqa: E402
from mill.executor import Mill                                          # noqa: E402
from vault.adapters.filesystem_repository import FilesystemRepository   # noqa: E402
from vault.models.ingot_artifact import from_cast                       # noqa: E402

# --------------------------------------------------------------------------
# The host's tools. Ordinary functions -- no Quench types, no decorators.
# --------------------------------------------------------------------------
CLAIMS = {
    f"CLM-{1000 + i}": {"claim_id": f"CLM-{1000 + i}", "amount": 4000 + i * 50,
                        "policy_id": f"POL-{500 + i}", "state": "KA"}
    for i in range(12)
}
POLICIES = {
    f"POL-{500 + i}": {"policy_id": f"POL-{500 + i}", "deductible": 500,
                       "active": True, "ceiling": 50_000}
    for i in range(12)
}


def fetch_claim(claim_id: str) -> dict:
    return CLAIMS[claim_id]


def lookup_policy(policy_id: str) -> dict:
    return POLICIES[policy_id]


def evaluate_coverage(amount: int, deductible: int, ceiling: int) -> dict:
    payable = max(0, min(amount - deductible, ceiling))
    return {"covered": payable > 0, "payable": payable}


def route_claim(claim_id: str, payable: int) -> dict:
    queue = "auto-approve" if payable < 10_000 else "manual-review"
    return {"claim_id": claim_id, "queue": queue, "payable": payable}


TOOLS = {
    "fetch_claim": fetch_claim,
    "lookup_policy": lookup_policy,
    "evaluate_coverage": evaluate_coverage,
    "route_claim": route_claim,
}

# --------------------------------------------------------------------------
# The agent. Stands in for whatever framework you use.
# --------------------------------------------------------------------------
def _span(trace_id, seq, tool, args, result):
    def attr(key, value):
        return {"key": key, "value": {"stringValue": value}}
    return {
        "traceId": trace_id,
        "spanId": f"{trace_id[:8]}{seq}",
        "name": f"execute_tool {tool}",
        "startTimeUnixNano": str(time.time_ns() + seq * 1000),
        "attributes": [
            attr("gen_ai.operation.name", "execute_tool"),
            attr("gen_ai.tool.name", tool),
            attr("gen_ai.tool.call.arguments", json.dumps(args)),
            attr("gen_ai.tool.call.result", json.dumps(result, default=str)),
        ],
    }


def run_agent(claim_id: str, trace_id: str) -> dict:
    """One agent run. In production a model decides each step; here the
    sequence is fixed, which is what makes it a Quench candidate at all."""
    spans = []

    claim = fetch_claim(claim_id)
    spans.append(_span(trace_id, 0, "fetch_claim", {"claim_id": claim_id}, claim))

    policy = lookup_policy(claim["policy_id"])
    spans.append(_span(trace_id, 1, "lookup_policy",
                       {"policy_id": claim["policy_id"]}, policy))

    coverage_args = {"amount": claim["amount"], "deductible": policy["deductible"],
                     "ceiling": policy["ceiling"]}
    coverage = evaluate_coverage(**coverage_args)
    spans.append(_span(trace_id, 2, "evaluate_coverage", coverage_args, coverage))

    route_args = {"claim_id": claim_id, "payable": coverage["payable"]}
    routed = route_claim(**route_args)
    spans.append(_span(trace_id, 3, "route_claim", route_args, routed))

    return {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}


def main() -> int:
    print("=" * 68)
    print("1. AGENT RUNS  (12 claims, emitting OTel GenAI spans)")
    print("=" * 68)
    payloads = []
    for i, claim_id in enumerate(list(CLAIMS)[:12]):
        payloads.append(run_agent(claim_id, f"{i:032x}"))
    print(f"   12 runs, {sum(len(p['resourceSpans'][0]['scopeSpans'][0]['spans']) for p in payloads)} spans")
    print("   each run: 4 model decisions in production\n")

    print("=" * 68)
    print("2. QUENCH OBSERVES  (from spans alone - no agent integration)")
    print("=" * 68)
    source = OtelTraceAdapter(payloads=payloads)
    print(f"   readiness: {source.describe_readiness()['advice']}")
    groups = group_traces(source.fetch_traces())
    group = groups[0]
    print(f"   discovered: {' -> '.join(group.tool_sequence)}")
    print(f"   {len(group)} traces, {group.step_count} steps\n")

    print("=" * 68)
    print("3. COMPILE  (data flow inferred, not declared)")
    print("=" * 68)
    cast = build_cast(list(group.traces), minimum=10, source=source.describe())
    for step in cast.steps:
        edges = ", ".join(f"{b.field} <- step {b.from_step}" for b in step.bindings)
        print(f"   [{step.index}] {step.operation.tool_name:<20} {edges or '(caller supplies)'}")
    print()

    print("=" * 68)
    print("4. VERIFY AND SIGN")
    print("=" * 68)
    traces = list(group.traces)
    passed = []
    if baseline.evaluate(traces):
        passed.append("no_branching")
    verdict = oracle.evaluate(traces)
    if verdict.impure_steps:
        pass
    elif not verdict.observable_steps:
        # Every claim id is distinct here, so no input ever recurs and purity
        # is not observable. Claiming it would be an overclaim in a signed
        # provenance record.
        passed.append("purity:not-observable")
    else:
        passed.append("purity")
    print(f"   verified by: {', '.join(passed)}")
    print(f"   observable steps: {len(verdict.observable_steps)}, "
          f"impure: {len(verdict.impure_steps)}")
    if not verdict.observable_steps:
        print("   note: no input value recurred across runs, so purity could")
        print("         not be tested. Recorded as not-observable, not passed.")

    vault = FilesystemRepository(root=Path("/tmp/quench-claims-vault"))
    hallmark = Signer(key_dir=Path("/tmp/quench-claims-trust")).sign(
        cast, verified_by=tuple(passed), trace_source=source.describe())
    ingot = from_cast(cast, hallmark)
    vault.put(ingot)
    print(f"   ingot {ingot.ingot_id}  signed {hallmark.provenance.sealed_at}\n")

    print("=" * 68)
    print("5. MILL EXECUTES  (same tools, no model)")
    print("=" * 68)
    # The caller supplies only what is not bound from an earlier step.
    live = [
        {"claim_id": "CLM-1007"},   # the only real input
        {},                          # policy_id  <- step 0
        {"deductible": 0},           # amount, ceiling <- steps 0, 1
        {},                          # claim_id, payable <- steps 0, 2
    ]
    started = time.perf_counter()
    result = Mill(invoker=CallableInvoker(TOOLS, name="claims-mesh")).execute(
        ingot, live)
    elapsed = (time.perf_counter() - started) * 1000

    print(f"   {result.describe()}")
    for step in result.steps:
        body = step.error or json.dumps(step.output, default=str)
        print(f"   [{step.index}] {'ok ' if step.ok else 'ERR'} "
              f"{step.tool_name:<20} {body[:60]}")

    print(f"\n   agent path:  4 model calls")
    print(f"   Mill path:   {result.model_calls} model calls, {elapsed:.1f}ms")
    return 0 if result.executed and all(s.ok for s in result.steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
