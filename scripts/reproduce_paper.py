"""Produce every number the paper prints, from the captured corpus.

One command, one source of truth. No figure in the paper is computed by hand.

    ./scripts/reproduce_paper.sh

Implements the analysis plan fixed in `docs/paper/PREREGISTRATION.md` §8:

    1. group captured events into traces by session_id
    2. cluster traces into workflows by operation signature sequence
    3. discard workflows with < 10 traces
    4. oracle: are outputs byte-identical across the set?          (H1)
    5. detector v1 on a single trace's output                      (H2)
    6. baseline (control-flow-only) criterion                      (H3)
    7. per-workflow figures as well as pooled
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for component in ("cast", "assay"):
    sys.path.insert(0, str(ROOT / component / "src"))

from assay.purity import detector, oracle  # noqa: E402
from assay.strategies import baseline_controlflow_strategy as baseline  # noqa: E402
from cast.adapters.hook_trace_adapter import HookTraceAdapter  # noqa: E402
from cast.compiler.grouping import group_traces  # noqa: E402

MIN_TRACES = 10  # preregistration §6


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval at 95%. Fixed by preregistration §8."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = (
        z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    )
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def main() -> int:
    source = HookTraceAdapter()
    traces = source.fetch_traces()
    groups = group_traces(traces)
    eligible = [g for g in groups if len(g) >= MIN_TRACES]

    print("=" * 72)
    print("QUENCH — PAPER RESULTS")
    print("=" * 72)
    print(f"source            {source.describe()}")
    print(f"traces captured   {len(traces)}")
    print(f"workflows found   {len(groups)}")
    print(f"workflows >= {MIN_TRACES}   {len(eligible)}  (smaller sets excluded, §6)")

    if not eligible:
        print("\nNo workflow has enough traces. Collect more before analysing.")
        return 1

    pooled_stable = 0
    pooled_impure = 0
    matrix = detector.ConfusionMatrix()
    baseline_wrong: list[tuple[str, oracle.StepVerdict]] = []
    per_workflow: list[dict] = []

    for index, group in enumerate(eligible):
        traces_in_group = list(group.traces)
        verdict = oracle.evaluate(traces_in_group)
        base = baseline.evaluate(traces_in_group)

        name = " -> ".join(t.split("/")[-1] for t in group.tool_sequence)
        print("\n" + "-" * 72)
        print(f"WORKFLOW [{index}]  {len(group)} traces, {verdict.step_count} steps")
        print(f"  {name}")
        print(f"  baseline: {'PROMOTE' if base else 'reject'} — {base.reason}")

        stable = verdict.control_flow_stable_steps
        impure = verdict.impure_steps
        pooled_stable += len(stable)
        pooled_impure += len(impure)

        print(f"  oracle:   {len(stable)} control-flow-stable, {len(impure)} impure")

        for step in verdict.steps:
            if not step.control_flow_stable:
                continue
            sample = step.sample_a
            detected = detector.inspect(sample)
            matrix = matrix.plus(step.impure, bool(detected))

            flag = "IMPURE" if step.impure else "pure  "
            seen = ",".join(detected.classes) if detected.classes else "-"
            print(
                f"    [{step.position}] {flag}  {step.tool_name.split('/')[-1]:<16}"
                f" outputs={step.distinct_outputs:<3} detector={seen}"
            )
            if step.impure and base and step.position in base.stable_positions:
                baseline_wrong.append((name, step))

        per_workflow.append(
            {
                "workflow": name,
                "traces": len(group),
                "steps": verdict.step_count,
                "control_flow_stable": len(stable),
                "impure": len(impure),
                "impurity_rate": verdict.impurity_rate,
                "baseline_promotes": bool(base),
            }
        )

    # ---------------------------------------------------------------- results
    print("\n" + "=" * 72)
    print("H1 — impurity among control-flow-stable steps")
    print("=" * 72)
    rate = pooled_impure / pooled_stable if pooled_stable else 0.0
    low, high = wilson(pooled_impure, pooled_stable)
    print(f"  impure / stable   {pooled_impure} / {pooled_stable}")
    print(f"  rate              {rate:.1%}   95% CI [{low:.1%}, {high:.1%}]")
    print("  predicted         20.0%   interval 8-40%   (registered 2026-09-11)")
    if rate < 0.05:
        print("  VERDICT           H1 FALSIFIED (< 5%). Report as a negative result.")
    elif 0.08 <= rate <= 0.40:
        print("  VERDICT           within the registered prediction interval")
    else:
        print("  VERDICT           outside the registered interval — report plainly")

    print("\n" + "=" * 72)
    print("H2 — detector v1 against the oracle")
    print("=" * 72)
    print(
        f"  TP {matrix.true_positive}  FP {matrix.false_positive}  "
        f"TN {matrix.true_negative}  FN {matrix.false_negative}"
    )
    print(f"  precision         {matrix.precision:.2f}   (target >= 0.80)")
    print(f"  recall            {matrix.recall:.2f}   (target >= 0.70)")
    if matrix.precision < 0.5 or matrix.recall < 0.4:
        print("  VERDICT           H2 FALSIFIED. Report as a negative result.")
    elif matrix.precision >= 0.80 and matrix.recall >= 0.70:
        print("  VERDICT           meets the registered target")
    else:
        print("  VERDICT           below target but not falsified — report plainly")

    print("\n" + "=" * 72)
    print("H3 — steps the baseline would wrongly promote")
    print("=" * 72)
    if baseline_wrong:
        print(f"  {len(baseline_wrong)} step(s) promoted by the control-flow-only")
        print("  criterion that the oracle classifies as impure:\n")
        for name, step in baseline_wrong:
            print(f"    {name}")
            print(f"      step {step.position} ({step.tool_name.split('/')[-1]})")
            print(f"      {step.distinct_outputs} distinct outputs across traces")
            if step.sample_a and step.sample_b:
                print(f"      a: {step.sample_a[:110]}")
                print(f"      b: {step.sample_b[:110]}")
            print()
        print("  VERDICT           H3 CONFIRMED")
    else:
        print("  none — VERDICT: H3 not confirmed on this corpus")

    results = {
        "traces": len(traces),
        "workflows_analysed": len(eligible),
        "h1": {
            "impure": pooled_impure,
            "stable": pooled_stable,
            "rate": rate,
            "ci95": [low, high],
            "predicted": 0.20,
        },
        "h2": {
            "tp": matrix.true_positive,
            "fp": matrix.false_positive,
            "tn": matrix.true_negative,
            "fn": matrix.false_negative,
            "precision": matrix.precision,
            "recall": matrix.recall,
        },
        "h3": {"wrongly_promoted": len(baseline_wrong)},
        "per_workflow": per_workflow,
    }
    out = ROOT / "docs" / "paper" / "RESULTS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print("=" * 72)
    print(f"written to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
