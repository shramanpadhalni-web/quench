# ADR-0005: Linux (or WSL2) is required — sandbox parity is not optional

- **Status:** Accepted
- **Date:** 2026-09-09
- **Related:** ADR-0000 finding 4; §7 and §15 of `QUENCH_ARCHITECTURE.md`

---

## Context

§7 of the architecture brief states the project's most important design rule:

> Mill execution must pass through the identical PreToolUse Gate, OS Sandbox, and
> Output Redaction stages that a live agent turn would. Mill is not a shortcut
> around Crew's security — it's a shortcut around the *model call*, not around the
> policy check.

Kiro Crew supports Windows natively, and primary development for this project
began on Windows 11. However:

> "The OS-level filesystem sandbox (Linux namespaces / macOS Seatbelt) is not
> available on Windows; every other feature works."
> — Kiro Crew installation documentation

Kiro Crew's own app manifest schema reflects the same reality: `platform.os`
defaults to `["macos", "linux"]`.

## Decision

**Quench is developed, tested, and deployed on Linux or macOS. On Windows,
development happens inside WSL2 (Ubuntu 24.04), not on the Windows host.**

The repository is cloned to the Linux filesystem (`~/quench`), never to
`/mnt/c/...`.

## Rationale

1. **The security claim is the product.** Quench's entire pitch is that sealed
   execution is *as safe as* an agent turn, not merely faster. On Windows there is
   no OS sandbox for Mill to pass through, so the claim cannot be tested — only
   asserted. A claim we cannot test is one a reviewer will correctly refuse to
   believe.

2. **Dev/prod parity.** §15's deployment target is a single Linux host running
   Docker Compose. Developing on Linux means the sandbox adapter, the filesystem
   layout under `~/.kiro/crew/`, and process behaviour are identical in
   development and production from day one, rather than diverging until Phase 7.

3. **Cross-filesystem I/O distorts measurement.** Working through `/mnt/c` adds
   substantial and variable latency, and file-watching behaves inconsistently
   across the WSL filesystem boundary. Quench exists to produce trustworthy
   before/after execution numbers; running on a filesystem that adds noise to
   those numbers is self-defeating.

4. **The macOS delegation case still needs handling.** On macOS, Crew's sandbox
   and kiro-cli's own sandbox are mutually exclusive (nested Seatbelt profiles
   fail with `EPERM`), so Crew delegates. The Mill sandbox adapter must handle
   delegation rather than assume ownership — a case that only exists on a platform
   where the sandbox exists at all.

## Consequences

**Positive**

- §7's guarantee becomes testable, and can be asserted in public claims.
- Phase 7 deployment becomes a packaging exercise rather than a porting exercise.
- The `mill/sandbox_adapter` boundary is exercised against a real sandbox from the
  first Shadow Mode run.

**Negative**

- Windows contributors need a one-time WSL2 setup step. This is documented as a
  single command in `docs/SETUP.md` and is a prerequisite, not a workaround.
- Windows-native Crew users are not a supported Quench target for v1. This should
  be stated plainly in the README rather than discovered by a user whose sandbox
  silently does nothing.

**Neutral**

- No component design changes. This is an environment decision, not an
  architectural one.

## Alternatives considered

**Develop on Windows, defer sandbox verification to Phase 7.** Rejected. It
defers the single most load-bearing verification in the project to the phase
furthest from where it would be cheap to fix, and would let five phases of work
accumulate on an untested assumption.

**Support Windows with a documented sandbox gap.** Rejected for v1. Shipping a
determinism kernel whose security guarantee is silently absent on one platform is
worse than not supporting that platform. Revisit if Crew gains Windows sandboxing.
