# ADR-0000: Kiro Crew integration seams — what is actually available

- **Status:** Accepted
- **Date:** 2026-09-09
- **Supersedes:** assumptions in §1, §5, §7, §9, §12 and §16 of
  `QUENCH_ARCHITECTURE.md` v1.2

---

## Context

The v1.2 architecture brief specifies Quench as a Kiro Crew App that:

1. subscribes to a `skill_invoked` Gateway event,
2. registers a **pre-dispatch lifecycle hook** that intercepts a skill invocation
   *before the agent turn starts* and answers in its place (Sealed Mode),
3. compiles its typed IR from **Crew's Signed Event Log**, requiring "zero
   additional instrumentation", and
4. executes through a thin adapter over Crew's own OS sandbox primitives.

Every phase from 4 onward in §16 is gated on (2). Before writing code we verified
all four against Crew's published documentation and source. Three are false.

This ADR records what is actually available, so that later readers understand why
the implementation diverges from the brief — and so the divergence is a documented
engineering decision rather than undocumented drift.

---

## Findings

### 1. There is no `skill_invoked` event, and no `session_end` — **assumption false**

The events an App may subscribe to (gated by `permissions.events` in `app.json`):

```
chat_chunk, chat_done, chat_message, chat_error, tool_call, notification,
slots, slot_title, dashboard, log, refresh, approval, subagent_done,
task_update, task_complete, proactive_notification, app_reload, error
```

Neither event named in the brief exists. `chat_done` is the nearest analogue to
`session_end`; there is no skill-level event at all.

### 2. Apps cannot intervene in a turn — **assumption false, and architecturally decisive**

Crew's own architecture overview states this directly. On the app-facing hooks
(`backend.hooks` → `routes` / `on_startup` / `on_shutdown`, and
`setup.onEnable` / `onDisable`):

> "none of them lets an app take a position in a flow the core owns."

and, listed as the first of three acknowledged platform gaps:

> "Apps add but cannot intervene in core flows"

The capability Quench needs **does exist in the core**. `HookManager` runs
pre-dispatch and can return `HOOK_REPLY` — documented as "auto-reply without LLM
processing", which is functionally exactly Sealed Mode. But:

> Hooks are "built only from `config.json`'s `hooks` section" and it "exposes no
> registration path."

and the `auto_replies` config is a declarative list of pattern → static-text
rules (`AutoReplyHook`), not a callout to a process that computes an answer.

A second hook system exists at the Kiro CLI layer: versioned JSON files in
`~/.kiro/hooks/*.json`, with triggers `SessionStart`, `UserPromptSubmit`,
`PreToolUse`, `PostToolUse`, `Stop`, and others. These receive structured JSON on
stdin and **can block** — a `PreToolUse` hook exiting with code 2 halts the call
and returns stderr to the agent.

**But blocking is not answering.** Kiro documents `UserPromptSubmit` as able to
"block execution, inject additional context, or log prompts", and is silent on
supplying a response in place of the turn.

**Conclusion: we can observe, veto, and inject. We cannot say "skip the model,
here is the answer" through any documented seam.**

### 3. The SEL cannot serve as a trace source — **assumption false**

`~/.kiro/crew/security_events.jsonl`, append-only HMAC-SHA256 hash-chained JSONL.
Record schema (`SecurityEvent`):

```
event_id, timestamp, event_type, caller_identity, agent, source, operation,
tool_kind, outcome, resources, downstream_service, request_id, error,
prev_hash, entry_hash, metadata
```

Event types: `tool_invocation`, `tool_approval`, `tool_denial`, `mcp_call`,
`api_access`, plus `sel_rotation` boundary records.

**Tool arguments and results are not recorded.** The `resources` field holds an
"affected resources summary (truncated)", capped at `_MAX_ARG_LEN = 500` bytes
after redaction.

Two consequences:

- **Cast compilation cannot read the SEL.** There are no typed inputs or outputs
  in it from which to build a DAG. `kirocrew_sel_adapter.py` as specified in §8
  is not implementable.
- **`measure_savings.py` cannot read the SEL either.** There is no model-call or
  token event type. The §17 headline metric — the number the entire broadcast
  rests on — has no source in the log the brief points at. A separate source must
  be identified before anything seals.

### 4. Sandbox adapter — **assumption partially true**

`agent.sandbox: auto` engages Linux user namespaces or macOS `sandbox-exec`
Seatbelt. On macOS it is *mutually exclusive* with kiro-cli's own sandbox — nested
Seatbelt profiles fail with `EPERM` — so Crew delegates to kiro-cli instead. A
Mill adapter must handle that delegation rather than assume it owns the sandbox.

Critically:

> "The OS-level filesystem sandbox (Linux namespaces / macOS Seatbelt) is not
> available on Windows; every other feature works."

§7's guarantee is therefore unverifiable on Windows. See ADR-0005.

### 5. Manifest defects in §9 — **would fail App Store review**

The brief's `app.json` omits `permissions` entirely. `permissions.api` is the one
permission currently enforced — "via the app-token scope check — deny-by-default
on out-of-scope paths" — so as written, every Gateway API call would be denied.
Also missing: `author`, `license`, `minCrewVersion`, and `backend.type`.

Useful seams the brief does not mention and we should use: `backend.hooks`
(in-gateway Python), a manifest-level `crons` array, `dependencies.commands` (a
`which` check — where a Rust `mill` binary would have to declare itself), and
`setup.onInstall` for the UI build.

---

## Decision

### Trace capture moves from the SEL to a `PostToolUse` hook

A single hook file in `~/.kiro/hooks/` receives `tool_name`, `tool_input`,
`tool_response`, `cwd` and `session_id` per call — a complete, ordered execution
trace, which is strictly better data than the SEL ever offered.

This costs the brief's "zero additional instrumentation" claim. The replacement
claim is **"one hook, still no fork"**, which is honest and materially just as
strong.

The SEL adapter is retained as a stub, alongside the OpenClaw/Lobster adapter, to
demonstrate that the `TraceSource` port generalises.

### Sealed Mode splits by skill type

Since no documented seam permits replacing a turn:

| Skill type | Mechanism | Model calls |
|---|---|---|
| **Scheduled** | The app backend is a long-running process; it invokes Mill directly — no agent, no Gateway turn | **Zero** |
| **Interactive** | Mill exposed via MCP; N tool-call round trips collapse into one turn | **One instead of N** |

§14 selected `cloud-governance-check` as the Phase 4 proof precisely because "it
runs on a schedule in real life". That is fortunate: the one showcase domain
chosen for the first sealing proof is the one where zero-model-call execution is
achievable through documented seams today.

Two options were rejected:

- **Block-and-answer** — run Mill, then *block* the `UserPromptSubmit` prompt
  carrying the result. Abuses deny-semantics for the happy path, and a blocked
  prompt most likely surfaces to the user as an error rather than an answer.
- **PreToolUse pre-authorisation** — let the turn run and auto-approve steps
  matching the sealed Cast. The model still runs, so savings are zero. Fails the
  core claim.

### The interception gap becomes an upstream contribution

Crew's maintainers documented this gap themselves. A PR opening `HookManager` to
app registration is a stronger §16 Phase 9 deliverable than an `app-registry.json`
entry, and converts the project's principal limitation into its principal
contribution.

Phase 9 therefore becomes **two** PRs: the registry entry, and the extension
point.

---

## Consequences

**Positive**

- The `TraceSource` port now reads a hook contract that Kiro CLI, Claude Code and
  OpenClaw all expose in near-identical shape. §16 Phase 10 (portability) moves
  from "optional, post-v1" to nearly free — and it is what distinguishes a Crew
  plugin from a platform-independent idea.
- Compile-time governance rechecking (§7) is unaffected; `POLICY ∩ PROFILE` and
  the `PreToolUse` deny set remain readable and enforceable.

**Negative**

- "Zero tokens" becomes conditional and must be stated as such in every public
  claim. Overstating it would not survive a reviewer who reads Crew's docs.
- A model-call/token measurement source still has to be found before Phase 4. This
  is now an open task, not a solved one.

**Neutral**

- Development moves to Linux/WSL2 (ADR-0005).
- The `.ingot` format, Assay, Hallmark, Vault, Kernel, Saga, Pack and Exchange
  designs are all untouched by these findings. The divergence is confined to how
  traces arrive and how sealed execution is triggered.

---

## Verification status

Findings 1, 3, 4 and 5 come from Crew's published documentation and repository
source and are considered **confirmed**.

Finding 2's conclusion — that `UserPromptSubmit` cannot supply a replacement
response — rests partly on *absence* of documentation. It must be confirmed
empirically before Phase 4 by observing how a blocked `UserPromptSubmit` renders
to the user. This is cheap to test and is scheduled as the first task after
environment setup.

---

## Sources

- Crew Apps — https://kiro.dev/docs/crew/apps/
- Manifest reference — https://kiro.dev/docs/crew/apps/manifest/
- SDK / API reference — https://kiro.dev/docs/crew/apps/sdk/
- Publishing & guidelines — https://kiro.dev/docs/crew/apps/publishing/
- Security — https://kiro.dev/docs/crew/security/
- Installation — https://kiro.dev/docs/crew/installation/
- Hook triggers — https://kiro.dev/docs/hooks/types/
- KiroCrew architecture overview — `docs/architecture/overview.md`
- `src/kiro_crew/hooks.py`, `src/kiro_crew/sel.py`
- Kiro issue #7500 (CLI vs IDE hook payloads) —
  https://github.com/kirodotdev/Kiro/issues/7500

---

# Addendum — empirical verification, 2026-09-09

Everything below was observed on a live Crew 0.5.0 / kiro-cli 2.21.2 install, not
inferred from documentation.

## The hook mechanism — corrected

Findings 1–5 above described hooks by reading upstream docs. Two corrections:

**Hooks are not `.json` files in `~/.kiro/hooks/`.** That is Kiro's IDE surface.
Crew loads *executable scripts*. From `kiro_crew/agent.py`:

```
agent.kiro_hooks             in ~/.kiro/crew/config.json — explicit entries, merged additively
agent.kiro_hooks_autoimport  default TRUE — scans agent.kiro_hooks_dir
agent.kiro_hooks_dir         default ~/.kiro/hooks — executable scripts
```

Event resolution precedence: explicit `# event:` header → filename suffix
(`-post.sh` → `postToolUse`, `-pre.sh`, `-prompt.sh`) → default `preToolUse`.
An optional `# matcher:` header filters by tool.

**Hand-editing `~/.kiro/agents/kirocrew.json` does not work.** Crew regenerates
that file on every gateway start. An edit made at 14:13 was gone by 14:14:33.

**This resolves the install-story problem.** Quench never edits a file Crew owns.
It drops scripts into a directory Crew is designed to scan, and Crew merges them
additively on every start — surviving regeneration by design. Hook commands are
validated (absolute path, no shell metacharacters, must exist, inside `$HOME`,
not a sensitive path), with per-event and global caps; rejections are written to
the SEL as `kiro_hooks_rejected`, so failure is auditable rather than silent.

Source comment, independently confirming ADR-0005: *"EVERY Windows hook path is
rejected (autoimport silently loads nothing)."* On Windows, trace capture would
not merely run unsandboxed — it would never load.

## Payload shapes — CONFIRMED

| Event | Keys delivered on stdin |
|---|---|
| `userPromptSubmit` | `hook_event_name`, `cwd`, `session_id`, `prompt` |
| `preToolUse` | + `tool_name`, `tool_input` |
| `postToolUse` | + `tool_response` |

**ADR-0000's central bet holds.** `postToolUse` delivers full, untruncated
`tool_input` and `tool_response` grouped by `session_id` — everything the Cast
compiler needs, none of which the SEL contained.

Observed `postToolUse` payload (abridged):

```json
{
  "hook_event_name": "postToolUse",
  "cwd": "/home/<user>/.kiro/crew/workspace",
  "session_id": "f0051f6c-96b7-448c-ae69-b93ff8bc0b9b",
  "tool_name": "read",
  "tool_input": {
    "__tool_use_purpose": "Read quench-test.txt and list workspace directory",
    "operations": [
      {"mode": "Line", "path": ".../quench-test.txt"},
      {"mode": "Directory", "path": "...", "depth": 1, "exclude_patterns": []}
    ]
  },
  "tool_response": {"items": [{"Text": "line one: ..."}, {"Text": "User id: 1000\n-rw-r--r-- ..."}]}
}
```

### Consequences for the Cast IR

1. **`tool_input` is already structured.** No string parsing — it arrives as typed
   JSON. The IR builder maps a schema onto a schema, not onto free text.

2. **Kiro batches operations into one tool call.** The `read` above performs two
   distinct operations in a single call. **Cast DAG granularity must therefore be
   the *operation*, not the tool call** — otherwise two different workflows that
   happen to batch identically would compile to the same node.

3. **`__tool_use_purpose` is present on every call** — the agent's own stated
   intent. Unplanned, and valuable: it gives Cast steps human-readable labels for
   free, which is what makes §11's `quench inspect <ingot-id>` ("why did this run
   through Mill?") answerable in plain language rather than as raw JSON.

4. **`userPromptSubmit.prompt` carries the entire agent system prompt**, not just
   the user's text. Any skill-signature matching at that event must extract the
   user turn rather than hashing the whole payload.

5. **Agents execute in `~/.kiro/crew/workspace`**, not the Quench repo. Showcase
   demo drivers must account for this.

### Value non-determinism is now demonstrated, not hypothetical

The directory-listing response embeds mtimes:

```
-rw-r--r-- 1 1000 1000 99 Sep 09 14:15 .../quench-test.txt
```

A step can be perfectly non-branching and still return different bytes on every
run. `no_branching_strategy` catches control-flow divergence and would pass this
step happily.

**Assay therefore requires a purity check on step outputs in addition to the
branching check.** This was raised as a design suggestion before implementation
began; it is now an observed property of the very first trace captured. Treat it
as required for v1, not deferred.

## Still open

- Whether `userPromptSubmit` can supply a response replacing the turn, or only
  block. Unchanged from above — still the gating question for interactive Sealed
  Mode, still to be tested empirically.
- Whether the OS sandbox (`agent.sandbox: auto`, distinct from `jail: auto`, which
  the public edition lacks) genuinely engages. `config.json` confirms the two are
  separate settings, which is the encouraging answer; direct confirmation pending.
- `apps_allow_third_party` is `false` by default, with `apps_trusted` /
  `apps_trusted_local` alongside it. Quench ships as a third-party app, so
  enabling it is a required step in the install story.
