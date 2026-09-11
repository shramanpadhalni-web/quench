# Security

## The design rule

Mill execution passes through the **identical** PreToolUse gate, OS sandbox and
output redaction that a live agent turn would. Mill is a shortcut around the
*model call* — never around the policy check.

Concretely:

- Assay re-applies Crew's `POLICY ∩ PROFILE` governance check to every step at
  seal time. A Cast containing a step Crew's own governance would deny is
  **rejected at compile time**, not merely blocked at runtime.
- Mill calls the same OS sandbox primitives kiro-cli uses — a thin adapter, not
  a reimplementation, so the two cannot drift apart.
- Every Mill execution writes to the SEL with `executor: mill` plus the Hallmark
  signature used.
- Output redaction runs identically on Mill's output.

**The test:** if a reviewer cannot tell from the audit log alone that a step ran
through Mill rather than the LLM — except for one clearly labelled field — the
security model is implemented correctly.

## Platform requirement

Quench requires Linux or macOS. The OS sandbox does not exist on Windows, and
Crew rejects every Windows hook path outright. See
`docs/adr/0005-linux-required-for-sandbox-parity.md`.

## Sealing is a cache, not a promise

Sealed Mode is never a one-way door. Every execution re-checks live inputs
against the sealed signature; drift demotes to Shadow Mode immediately.

## Reporting a vulnerability

Please open a private security advisory rather than a public issue.
