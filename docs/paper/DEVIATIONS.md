# Deviations from the Preregistration

Every departure from `PREREGISTRATION.md` is recorded here **before** the
affected analysis is run: the date, the change, and the reason.

The paper will state whether any deviation occurred. A preregistration with
undisclosed deviations is worse than no preregistration at all.

---

## D1 — 2026-09-11 — Oracle definition was wrong as registered

**Status:** correction, applied before any result was reported or published.

### What was registered

`PREREGISTRATION.md` §2:

> **Output purity (the oracle).** A control-flow-stable step is **impure** if its
> serialised output is not byte-identical across all traces in the set.

### Why it is wrong

"Control-flow-stable" is defined in the same section as *identical input
**structural signature*** — identical input **shape**, with leaf values replaced
by type names.

Two traces can therefore be control-flow-stable while carrying entirely
different input *values*. `read_lease(document_id="lease-001")` and
`read_lease(document_id="lease-002")` share the signature
`{"document_id": "str"}` and legitimately return different documents.

Under the registered definition, that step is classified impure. It is not. It
is a pure function of its input, exercised on different inputs.

The first run of the analysis made this unmistakable:

```
[0] IMPURE  read_lease       outputs=20   detector=-
[5] IMPURE  write_record     outputs=20   detector=-
```

Twenty distinct outputs across 52 traces of 20 distinct lease documents — one
per document. Correct behaviour scored as a defect.

Pooled, the flawed definition yielded an impurity rate of **81.8%**, far outside
the registered 8–40% interval. That number is an artefact of the definition, not
a finding.

### The correction

Impurity is judged **within groups of traces sharing identical input values** at
that step position, not merely identical input shape:

> A control-flow-stable step is **impure** if, among traces whose serialised
> input at that position is byte-identical, the serialised output is not
> byte-identical.
>
> Step positions for which no input value recurs across traces are **excluded
> from the denominator**, since purity is not observable for them.

This is the question the registered definition was intended to ask, and the one
the motivating example — a directory listing whose mtime changes between runs on
*identical* inputs — actually poses.

### What is unchanged

- Detector v1's seven patterns (§3) — **untouched**.
- The H1 point prediction of 20% and its 8–40% interval — **untouched**. The
  prediction stands as registered and is reported against the corrected measure.
- The falsification thresholds (§5) — **untouched**.
- The baseline criterion (§7) and the analysis plan (§8) — **untouched**.

### Honest consequence

The corrected denominator is much smaller, counting only step positions where an
input value recurs. On the current corpus this materially reduces statistical
power. That limitation will be stated in the paper rather than managed around.

### Recorded by

Committed before the corrected analysis was run. The flawed 81.8% figure is
preserved here deliberately, so the correction is auditable rather than
invisible.
