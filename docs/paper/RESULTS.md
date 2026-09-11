# Results

**Measured 2026-09-11** against a preregistration frozen the same day, before any
data was collected. Every number here is produced by `./scripts/reproduce.sh`
from traces committed to this repository. Nothing is estimated.

- Preregistration: [`PREREGISTRATION.md`](PREREGISTRATION.md) — commit `0f64bd0`
- Deviations: [`DEVIATIONS.md`](DEVIATIONS.md) — one, D1, recorded before the
  corrected analysis ran
- Machine-readable: [`RESULTS.json`](RESULTS.json)

---

## 1. The headline

> **A published promotion criterion based on control-flow stability promotes a
> step whose output is not reproducible.** We demonstrate a counterexample from
> real agent traces, and a checker that rejects it.

The criterion under test is from Malik, *Progressive Crystallization*
([arXiv 2607.07052](https://arxiv.org/abs/2607.07052)), Table II: promote after
≥10 successful runs where ≥90% produce the same action sequence.

Applied to a cloud governance workflow captured from a live agent, it promotes
all five steps. Step 4 returns **31 distinct outputs across 31 traces for
byte-identical input** — it appends to an audit log, and audit entries carry
timestamps. Sealing it produces an artifact that replays a frozen timestamp
indefinitely, silently.

---

## 2. Corpus

| | |
|---|---|
| Sessions | **142** (112 lease, 30 governance) |
| Trace events | **1,058** |
| Distinct workflows | **4** (≥10 traces each) |
| Verification | every session checked against source documents before inclusion |
| Runtime | Kiro Crew 0.5.0 / kiro-cli 2.21.2, Ubuntu 24.04 |
| Data | synthetic, deterministic seeds, committed to this repository |

Two workflow families, chosen to differ in one property:

| Corpus | Tools | Steps analysed |
|---|---|---|
| `lease-abstraction` | purpose-built MCP server | 11 |
| `cloud-governance-check` | platform built-ins (`fs_read`, `execute_bash`) | 5 |

---

## 3. Hypotheses, as registered

### H1 — impurity rate · **measured below the registered interval**

> Among control-flow-stable steps, a non-negligible fraction produce
> non-reproducible output.

| | |
|---|---|
| **Registered prediction** | 20%, interval 8–40%, falsified below 5% |
| **Measured** | **6.2%** (1 of 16 observable steps) |
| 95% CI (Wilson) | [1.1%, 28.3%] |
| Verdict | Above the falsification floor; **below the predicted interval** |

The prediction was too high. Reported as registered.

**Per corpus:**

| Corpus | Observable steps | Impure | Rate |
|---|---|---|---|
| `lease-abstraction` | 11 | 0 | 0% |
| `cloud-governance-check` | 5 | 1 | 20% |

### H2 — detector quality · **below target, not falsified**

> Purity detector v1 identifies oracle-impure steps with precision ≥0.80 and
> recall ≥0.70.

| | TP | FP | TN | FN | Precision | Recall |
|---|---|---|---|---|---|---|
| Measured | 1 | 1 | 14 | 0 | **0.50** | **1.00** |

Recall is perfect: the detector caught the impure step. Precision is halved by a
single false positive, discussed in §5 — where we argue the detector may be
right and the oracle short-sighted.

### H3 — wrongly promoted steps · **CONFIRMED**

> The control-flow-only criterion promotes at least one step the oracle
> classifies as impure.

**Confirmed. One step.**

```
workflow: read -> read -> read -> shell -> shell   (31 traces, 5 steps)
baseline: PROMOTE — all positions ≥90% agreement

  [0] pure    read    repeats=1   outputs=1   detector=ls_mtime
  [1] pure    read    repeats=10  outputs=10  detector=-
  [2] pure    read    repeats=1   outputs=1   detector=-
  [3] pure    shell   repeats=10  outputs=10  detector=-
  [4] IMPURE  shell   repeats=10  outputs=31  detector=iso_timestamp
```

---

## 4. The corpus contrast

The most useful finding was not planned. Our first corpus measured **0%
impurity** — because its tools were written deterministic by construction: no
clock, no randomness, no network, `sort_keys` on write, with a self-test
asserting byte-stability.

A corpus built from tools that cannot be impure cannot measure impurity. That
mistake is recorded in commit `cab7c25` rather than quietly corrected.

The second corpus used the platform's **built-in** tools, and impurity appeared.

> **Purpose-built tools are pure because someone chose to make them so.
> General-purpose platform tools are not — and observation-first promotion
> systems compile the second kind.**

This matters directly for the systems under discussion. Malik's crystallises
workflows built from Azure's operational tooling; LOOP records trajectories over
whatever tools the agent has. Neither operates on hand-written pure functions.

---

## 5. The false positive is instructive

Step 0 of the governance workflow — a directory listing. The detector flagged
`ls_mtime`; the oracle scored it pure.

**Both are defensible.** The mtime pattern is genuinely present, and a directory
listing *will* eventually return different bytes. But the directory did not
change during a 15-minute corpus, so outputs were byte-identical and the oracle
saw purity.

> **The oracle is ground truth only within the observation window.** A step whose
> output changes daily looks perfectly pure in a corpus collected over fifteen
> minutes.

This is a limitation of every observation-first system, including the ones we
compare against, and it is an argument *for* a cheap pattern detector rather than
against one: the detector encodes knowledge the observation window cannot supply.
H2's apparent precision failure may be the oracle's short-sightedness rather than
the detector's error.

---

## 6. End-to-end demonstration

The checker is not a paper artifact. It runs:

```
CANDIDATE [0]  read_lease -> extract x4 -> write_record    SEALED
CANDIDATE [1]  read_lease                                  SEALED
CANDIDATE [2]  lookup -> check -> lookup -> check          SEALED
CANDIDATE [3]  read -> read -> read -> shell -> shell      REFUSED
     purity: step 4 produced 31 distinct outputs for identical input
     (passed: no_branching)
```

Sealed workflows are Ed25519-signed, stored as portable `.ingot` files, and
executed by a model-free runtime:

```
Mill executed 6 steps in 475ms, 0 model calls
  [1] extract_clause  {'clause_type':'term','value':24}
  [2] extract_clause  {'clause_type':'annual_rent','value':521000}
  [3] extract_clause  {'clause_type':'escalation','value':2.5}
  [4] extract_clause  {'clause_type':'renewal','value':'NO'}
```

Values match the source document exactly. The agent path for the same work takes
**~27 seconds and 6 model turns**.

Data-flow bindings — which input comes from which earlier output — are **inferred
from traces, not declared**:

```
step 1-4 .text        <- step 0  ["items",0,"Json","content",0,"text","$json","text"]
step 5   .document_id <- step 0  [...,"$json","document_id"]
```

Refusals verified: tampered provenance, drifted input shape, and revoked
artifacts all decline and hand work back to the agent.

---

## 7. Limitations

**Small sample.** One impure step, 16 observable steps. The CI is wide
[1.1%, 28.3%]. H3 is an existence claim and needs only one instance; H1 is a rate
and this sample cannot pin it down.

**Two workflow families.** Both synthetic, both authored by us. We do not claim
the rate generalises.

**Observation window.** Fifteen minutes. Slow-changing impurity is invisible
(§5).

**Repeatability, not correctness.** Everything here concerns whether a step
reproduces. Nothing establishes that it is *right*. A consistently wrong workflow
seals cleanly.

**Charitable baseline.** We could not reproduce the "zero safety violations"
condition outside its original environment and treated all traces as
violation-free, making the baseline more permissive than published.

---

## 8. Reproducing this

```bash
git clone <repo> && cd quench
./scripts/setup.sh
./scripts/reproduce.sh
```

No agent runs, no API keys, no credits. The corpus is committed. Every number in
this document, plus the seal/refuse demonstration and a Mill execution, comes out
of that one command.
