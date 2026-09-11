# Preregistration — Output Purity in Observed-Promotion Systems

**Status: FROZEN on commit. This document must not be edited after it is pushed.**
Any change of plan goes in `DEVIATIONS.md` alongside it, with a date and a
reason. The value of this document is entirely destroyed by silent revision.

- **Registered:** 2026-09-11
- **Registered by:** Shraman Padhalni
- **Repository:** this repo, Apache-2.0, synthetic data committed
- **Target venue:** arXiv `cs.SE` (primary), `cs.AI` / `cs.MA` cross-listed

---

## 1. Background

Several recent systems promote observed agent behaviour to deterministic
execution on the basis of accumulated evidence:

- **Progressive Crystallization** — Malik, Microsoft Azure Networking,
  [arXiv 2607.07052](https://arxiv.org/abs/2607.07052). Promotion criterion
  includes *"≥10 successful runs"* and *"≥90% of runs produce the same action
  sequence."*
- **LOOP Skill Engine** — Wang et al.,
  [arXiv 2605.14237](https://arxiv.org/abs/2605.14237). One-shot recording of a
  tool trajectory, extraction of a parameterised **branch-free** template,
  deterministic replay.

Both criteria are properties of **control flow**: the sequence and shape of
operations. Neither, as published, specifies a check on whether a step's
**output** is reproducible.

We observed a counterexample in the first execution trace we captured from a
live agent installation (Kiro Crew 0.5.0, 2026-09-09). A directory-listing step
returned:

```
-rw-r--r-- 1 1000 1000 99 Sep 09 14:15 .../quench-test.txt
```

The step is non-branching and its input signature is stable. Its output contains
a modification timestamp and therefore differs on every execution. A
control-flow-only criterion would promote it, producing an artifact that replays
a frozen timestamp indefinitely and silently.

This preregistration commits, in advance of data collection, to measuring how
often that gap occurs.

---

## 2. Definitions, fixed in advance

**Step.** One operation, not one tool call. Where a runtime batches several
operations into a single call, each is a distinct step. (Rationale recorded in
`docs/adr/0000-crew-seam-verification.md`.)

**Input structural signature.** The recursive shape of a step's input with all
leaf values replaced by their type name; dict keys sorted; lists reduced to
`["list", <shape of first element>]`. Implemented as
`cast.compiler.typed_ir.structural_signature`.

**Control-flow-stable step.** A step at position *i* whose input structural
signature is identical across **all** traces in a convergent trace set, where a
convergent set is ≥10 traces of the same workflow with identical step count and
identical per-position signatures. This operationalises the published criteria at
their strictest reading.

**Output purity (the oracle).** A control-flow-stable step is **impure** if its
serialised output is not byte-identical across all traces in the set. Determined
empirically from observed traces — **not** by pattern matching.

**Purity detector (the shipped artifact).** A single-trace heuristic that flags
suspected impurity from output content alone, without requiring N traces.
Detector v1 is frozen in §3.

The distinction between oracle and detector is deliberate and central: the
oracle requires a corpus and establishes ground truth; the detector is what a
production system can afford to run. We measure both.

---

## 3. Purity detector v1 — frozen

Flagged as impure if the serialised output matches any of:

| # | Class | Pattern (Python `re`) |
|---|---|---|
| 1 | ISO 8601 timestamp | `\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}` |
| 2 | `ls`-style mtime | `\b[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}\b` |
| 3 | UUID | `\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b` |
| 4 | Process id | `\bpid[=:\s]\s*\d+` (case-insensitive) |
| 5 | Long hex / address | `\b(?:0x)?[0-9a-f]{12,}\b` |
| 6 | Epoch seconds | `\b1[6-9]\d{8}\b` |
| 7 | Monotonic duration | `\b\d+(\.\d+)?\s*(ms|s|sec|seconds)\b` preceded by `took|elapsed|duration` within 20 chars |

**No pattern may be added, removed or modified after this document is pushed.**
Improvements belong to a "detector v2" reported separately and clearly marked as
post-hoc.

---

## 4. Hypotheses

### H1 — primary, directional

> Among control-flow-stable steps in real agent execution traces, a
> **non-negligible fraction produce non-reproducible output** and would therefore
> be wrongly promoted by a control-flow-only criterion.

**Point prediction: 20% of control-flow-stable steps are impure by the oracle.**

**Prediction interval: 8% – 40%.**

*Prediction set by the author on 2026-09-11, before any corpus data was
collected or inspected. The only evidence available at the time of prediction
was a single observed instance (the directory-listing mtime described in §1).*

### H2 — detector quality

> Purity detector v1 identifies oracle-impure steps with **precision ≥ 0.80** and
> **recall ≥ 0.70**.

### H3 — consequence

> Applying the published control-flow-only criterion to our corpus promotes at
> least one step that the oracle classifies as impure.

H3 is deliberately weak — a single instance proves the gap is real. H1 measures
whether it is *common enough to matter*.

---

## 5. Falsification — stated in advance

The paper's central claim **fails** if any of the following holds:

- **H1 falsified:** oracle-impure steps are **< 5%** of control-flow-stable
  steps. The gap would then be a curiosity, not a finding, and we will report it
  as such rather than reframing.
- **H2 falsified:** detector precision < 0.5 or recall < 0.4. A detector that
  poor is not shippable and must be reported as a negative result.
- **H3 falsified:** the baseline criterion promotes zero impure steps across the
  whole corpus. The premise would not reproduce.

**If H1 is falsified we will publish that result.** A measured negative finding
about a widely-adopted promotion criterion is a genuine contribution and will be
written up as one.

---

## 6. Corpus

| Parameter | Committed value |
|---|---|
| Minimum sessions | **100** |
| Minimum distinct workflows | **3** (`lease-abstraction`, `claims-triage`, `cloud-governance-check`) |
| Minimum traces per workflow | **10** (the published criterion's threshold) |
| Data | Synthetic only. No client data, ever. Corpus committed to the repository. |
| Capture | `postToolUse` hook; full `tool_name` / `tool_input` / `tool_response`, grouped by `session_id` |
| Runtime | Kiro Crew 0.5.0 / kiro-cli 2.21.2 on Ubuntu 24.04 |

**Inclusion.** Any session that completed without a runtime error and produced
≥1 tool call.

**Exclusion, decided now:**

1. Sessions with a tool error (`is_error`), which conflate failure with drift.
2. Sessions from a workflow with fewer than 10 total traces, which cannot form a
   convergent set.
3. Sessions captured before the hook configuration is frozen (see `DEVIATIONS.md`
   if the hook changes mid-collection).

**No session may be excluded for producing an inconvenient result.** Exclusions
are applied by the analysis script from the rules above, not by hand.

---

## 7. The baseline reimplementation

A faithful implementation of the published control-flow-only criterion, written
**before** the corpus is complete, in `assay/src/assay/strategies/baseline_controlflow_strategy.py`:

> Promote when: ≥10 successful traces, identical step count, and ≥90% of traces
> produce the same per-position input structural signature.

It must be implementable and runnable independently of our purity check. Where
the published description is ambiguous, the ambiguity and our reading are
recorded in a code comment and in the paper.

**Primary outcome table** — the paper's central result:

| | Baseline promotes | Baseline rejects |
|---|---|---|
| **Oracle: pure** | true promote | conservative reject |
| **Oracle: impure** | **wrongly promoted** ← the finding | correct reject |

---

## 8. Analysis plan — fixed in advance

1. Group captured events by `session_id` into traces.
2. Group traces by workflow; discard workflows with <10 traces (§6).
3. For each workflow, compute the convergent set and identify control-flow-stable
   steps.
4. For each such step, apply the **oracle**: are outputs byte-identical across
   the set?
5. For each such step, apply **detector v1** to a single trace's output.
6. Report: oracle impurity rate (H1), detector precision/recall against the
   oracle (H2), and the §7 outcome table (H3).
7. Report per-workflow figures as well as pooled, so a single dominant workflow
   cannot drive the headline number.

**Statistics.** Wilson score interval at 95% for all proportions. No hypothesis
test is planned; this is a descriptive measurement study and will be described as
one.

**One analysis script, `scripts/reproduce_paper.sh`, produces every number the
paper prints.** No figure is computed by hand.

---

## 9. Deviations

Any departure from this document — a changed pattern, a changed threshold, a new
exclusion rule, a corpus smaller than 100 sessions — is recorded in
`docs/paper/DEVIATIONS.md` with the date, the change, and the reason, **before**
the affected analysis is run.

The paper will state whether any deviation occurred. A preregistration with
undisclosed deviations is worse than no preregistration at all.

---

## 10. Commitments

- Every number in the paper is measured. Nothing is projected or estimated.
- The corpus, the code and the analysis script are public under Apache-2.0.
- Results are reproduced independently on at least two machines that are not the
  author's before submission.
- Prior work is cited generously and precisely. Malik's framing is credited
  plainly; this work extends a published criterion rather than competing with it.
- The limitation that **Quench proves repeatability, not correctness** is stated
  in the abstract, not buried.
