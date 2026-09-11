# Contributing to Quench

## The one rule that matters

> **Quench must never contain domain logic.**

The moment `cast/` imports something that knows what an insurance claim is, we
no longer have a kernel — we have one company's internal tool with a compiler
bolted on.

### Adding a new agent or product

A new domain contributes exactly four things, under `showcase/<name>/`:

- `agent.json` — the Crew agent config
- `skill.md` — the workflow in Crew's own skill format
- `synthetic_data/` — generated. **Never real client data. Ever.**
- `run_demo.sh` — drives enough repeated invocations to accumulate history

A new domain contributes **zero lines** to `cast/`, `assay/`, `vault/`,
`kernel/`, `saga/`, `mill/`, `pack/` or `exchange/`.

### The falsification test

If a new domain *forces* a kernel change, that is not a feature request from
the domain — it is proof the Cast IR is underspecified. **Fix the IR, not the
special case.** This single rule decides whether Quench stays a product or
becomes a pile of accumulated exceptions.

## Architecture rules

1. **Ports & adapters per component.** Anything crossing a component boundary
   gets an abstract `ports/*.py` interface first. Concretes live in
   `adapters/`. Nothing outside a component imports from another's `adapters/`.
2. **One composition root.** `app/backend/main.py` is the *only* file allowed
   to import a concrete adapter and wire it to a port. A new contributor should
   be able to read that one file and see the entire object graph.
3. **Strategy pattern for policy.** Assay's verification strategy and Kernel's
   promotion policy are swappable per-skill, never global constants.
4. **No component trusts another's internals** — only its port contract.

## Before you open a PR

```bash
./scripts/build_all.sh    # lint, typecheck, test
```

New behaviour needs a test. Decisions that constrain the future need an ADR in
`docs/adr/` — immutable once merged; supersede rather than edit.
