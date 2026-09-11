# Quench

**A determinism compiler for agent runtimes.**

Quench watches an agent do the same thing over and over, proves the behavior is
actually deterministic, and compiles it into a signed artifact that runs without
a model. When the world stops matching what was sealed, it falls back to the
live agent automatically.

> Every comparable tool makes deterministic execution something you **author**.
> Quench makes it something you **earn** — verified against your agent's own
> recorded behavior, never designed in advance.

Status: **pre-v1, in active build.** See [`docs/adr/0000-crew-seam-verification.md`](docs/adr/0000-crew-seam-verification.md)
for what is proven and what is still assumed.

---

## What problem this solves

[Kiro Crew](https://github.com/kirodotdev/KiroCrew) watches you work and synthesizes
repeated workflows into Markdown **skills**. But a skill is a *prompt*, not a
*program* — the 200th run costs the same model call as the first, even when the
execution trace has been byte-identical for months.

Crew is a **learning** system. It has no **compiling** step. Quench is that step.

---

## What Quench is — and is not

Quench is **not** a multi-agent framework, and **not** a workflow orchestrator.
Getting this distinction right matters, because it determines where every future
piece of work belongs.

| | Does this | Example |
|---|---|---|
| Multi-agent orchestration | Coordinates several agents toward a goal | Kiro Crew, CrewAI, LangGraph |
| Deterministic orchestration | Executes a workflow a human specified up front | Lobster, duckflux, Temporal |
| **Quench** | **Decides whether a single behavior still needs a model at all** | — |

The right mental model is a **JIT compiler**, not an orchestrator. Crew is the
interpreter loop. Quench is the tier-2 JIT that promotes hot, verified traces out
of the interpreter and into compiled execution — while keeping every safety
guarantee the interpreter had.

Quench operates on **one skill at a time**, one layer *below* orchestration. It
never decides which agent runs, or in what order. It only asks: *has this
particular behavior earned the right to stop being interpreted?*

---

## The three layers — never confuse them

```
┌─────────────────────────────────────────────────────────┐
│  Layer 3 — PRODUCTS         claims-triage, lease-abstraction,
│  agents + skills + data     cloud-governance-check, and whatever
│  domain-specific            you build next
├─────────────────────────────────────────────────────────┤
│  Layer 2 — KIRO CREW        agent runtime, memory, orchestration,
│  the host platform          security chain, scheduling
│  upstream, unmodified
├─────────────────────────────────────────────────────────┤
│  Layer 1 — QUENCH           observe → compile → verify → sign
│  the determinism kernel     → shadow → seal
│  domain-agnostic, forever
└─────────────────────────────────────────────────────────┘
```

**The rule that keeps this architecture alive:**

> Quench must never contain domain logic.

The moment `cast/` imports something that knows what an insurance claim is, the
kernel stops being a general product and becomes one company's internal tool.
The showcase agents in `showcase/` are **fixtures, not features** — they exist to
prove the kernel works, and they sit entirely outside the kernel's dependency
graph.

### Adding a new agent or product

A new domain contributes:

- `agent.json` — the Crew agent config
- `skill.md` — the workflow, in Crew's own skill format
- `synthetic_data/` — generated data. Never real client data. Ever.
- `run_demo.sh` — drives enough repeated invocations to accumulate real history

A new domain contributes **zero lines** to `cast/`, `assay/`, `vault/`,
`kernel/`, `saga/`, or `mill/`.

If a new domain *forces* a kernel change, that is not a feature request from the
domain — it is a signal that the Cast IR is underspecified. Fix the IR, not the
special case. This is the single test that decides whether Quench is a product or
a pile of accumulated exceptions.

### What a shipped product eventually looks like

```
agents (live, for the parts that need judgment)
  + ingots (sealed, for the parts that don't)
  + a Saga (composition)
  = a .ingotpack you can hand to someone
```

"Install this pack and 80% of the workflow costs nothing" is the shipping story.

---

## The pipeline

```
observe   →   compile   →   verify   →   sign     →   shadow  →   seal
 traces        Cast         Assay       Hallmark      Kernel      Mill
```

1. **Observe** — a `PostToolUse` hook records every `tool_name` / `tool_input` /
   `tool_response`, grouped by session. One hook file. No fork.
2. **Cast** — after N runs with zero branching, compile that history into a typed
   DAG of steps.
3. **Assay** — verify the DAG against every historical trace, *and* re-run Crew's
   own `POLICY ∩ PROFILE` governance check on every step. A step Crew's security
   model would deny is rejected **at compile time**, not just at runtime.
4. **Hallmark** — Ed25519-sign it into a portable `.ingot`, with provenance:
   who verified it, against how many traces, when.
5. **Shadow** — Mill runs alongside the real agent, side effects discarded,
   outputs compared. Mandatory. There is no skip-the-line path, including from
   the CLI.
6. **Seal** — Mill answers. Every run still re-checks live inputs against the
   sealed signature. Any drift demotes instantly back to the live agent.

**Sealing is a cache, not a promise.** That sentence is the entire trust model.

---

## Honest performance claims

Kiro Crew currently gives apps no way to intervene in a turn — its own
architecture doc names this as a known gap ("Apps add but cannot intervene in
core flows"). So the savings are conditional, and we state them that way:

| Skill type | Path | Model calls |
|---|---|---|
| Scheduled | Backend invokes Mill directly — no agent, no turn | **Zero** |
| Interactive | Mill exposed as an MCP tool | **One turn instead of N** |

Closing that gap upstream — opening Crew's `HookManager` to app registration — is
part of this project's roadmap, not a workaround we hide.

---

## Portability

Trace capture reads a hook contract (`tool_name`, `tool_input`, `tool_response`
on stdin) that Kiro CLI, Claude Code, and OpenClaw all expose in near-identical
shape. The `TraceSource` port is therefore not aspirational:

**Quench is a determinism compiler for any agent runtime that emits tool hooks.
Kiro Crew is simply the first host.**

---

## Getting started

See **[docs/SETUP.md](docs/SETUP.md)**. One command should take you from a clean
machine to `kirocrew doctor` passing. If it takes a paragraph of prose instead,
that is a bug — please open an issue.

---

## Vocabulary

| Term | Meaning |
|---|---|
| **Cast** | Typed IR compiled from execution traces |
| **Assay** | Verifier at seal time; drift checker at runtime |
| **Hallmark** | Ed25519 signer; provenance record |
| **Ingot** | The sealed, signed, portable artifact (`.ingot`) |
| **Vault** | Artifact store |
| **Mill** | The executor — no model in the loop |
| **Kernel** | The Shadow/Sealed state machine |
| **Saga** | Composes multiple ingots into one workflow |
| **Pack** | Distributable bundle (`.ingotpack`) |
| **Exchange** | Registry for publishing and pulling Packs |

---

## License

Apache-2.0, matching Kiro Crew.
