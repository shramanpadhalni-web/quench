"""``quench`` — one command for the whole lifecycle.

    quench status              what has been observed, and its state
    quench candidates          workflows discovered from traces
    quench seal <index>        verify, sign, store, enter Shadow
    quench inspect <ingot>     what a sealed artifact will do, and why
    quench run <ingot> ...     execute without a model
    quench revoke <ingot>      immediate and terminal
    quench serve               HTTP API + dashboard
    quench serve --mcp         expose Quench as MCP tools

The CLI exists before the UI on purpose: every capability must be scriptable
before it is clickable, or the UI becomes the only way to do things and the
system stops being automatable.
"""

from __future__ import annotations

import argparse
import json
import sys

from .wiring import build


def cmd_status(args) -> int:
    app = build()
    summary = app.kernel.summary()
    print("  ".join(f"{k}={v}" for k, v in summary.items()))
    print()
    for record in app.kernel.all():
        print(f"  {record.describe()}")
    if not app.kernel.all():
        print("  nothing observed yet")
    return 0


def cmd_candidates(args) -> int:
    app = build()
    rows = app.candidates()
    if not rows:
        print("No workflows observed yet.", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"{len(rows)} candidate workflow(s)\n")
    for row in rows:
        ready = "ready" if row["eligible"] else f"needs {row['needs']} more"
        print(f"  [{row['index']}] {row['traces']:>3} traces  "
              f"{row['steps']} steps  {row['state']:<10} ({ready})")
        print(f"      {' -> '.join(row['tools'])}")
        print(f"      {row['label'][:70]}")
        print()
    return 0


def cmd_seal(args) -> int:
    result = build().seal(args.index)
    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return 2
    if not result.get("sealed"):
        print("REFUSED — not sealed")
        for refusal in result.get("refusals", []):
            print(f"  {refusal}")
        if result.get("passed"):
            print(f"  (passed: {', '.join(result['passed'])})")
        return 2
    print(f"SEALED  {result['ingot_id']}  {result['steps']} steps")
    print(f"  verified by  {', '.join(result['verified_by'])}")
    print(f"  state        {result['state']}")
    print(f"  {result['note']}")
    return 0


def cmd_inspect(args) -> int:
    app = build()
    ingot = app.vault.get(args.ingot_id)
    if ingot is None:
        print(f"No ingot {args.ingot_id}", file=sys.stderr)
        return 1
    provenance = ingot.hallmark.get("provenance", {})
    print(f"ingot      {ingot.ingot_id}")
    print(f"steps      {len(ingot)}")
    print(f"sealed at  {provenance.get('sealed_at')}")
    print(f"verified   {', '.join(provenance.get('verified_by', []))}")
    print(f"traces     {provenance.get('trace_count')}")
    print(f"revoked    {ingot.revoked}")
    print("\nwhat it will do:")
    for step in ingot.steps:
        edges = ", ".join(f"{b.field}<-step{b.from_step}" for b in step.bindings)
        print(f"  [{step.index}] {step.tool_name.split('/')[-1]:<18} "
              f"{(step.purpose or '-')[:44]}")
        if edges:
            print(f"       inputs from earlier steps: {edges}")
    return 0


def cmd_revoke(args) -> int:
    app = build()
    ok = app.vault.revoke(args.ingot_id)
    print(f"{'revoked' if ok else 'no such ingot'}: {args.ingot_id}")
    return 0 if ok else 1


def cmd_serve(args) -> int:
    if args.mcp:
        from .mcp_server import serve_mcp
        return serve_mcp()
    from .http_server import serve_http
    return serve_http(port=args.port)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quench", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="lifecycle state of every observed workflow")

    p = sub.add_parser("candidates", help="workflows discovered from traces")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("seal", help="verify, sign, store, enter Shadow")
    p.add_argument("index", type=int)

    p = sub.add_parser("inspect", help="what a sealed artifact will do")
    p.add_argument("ingot_id")

    p = sub.add_parser("revoke", help="revoke an artifact, immediately")
    p.add_argument("ingot_id")

    p = sub.add_parser("serve", help="HTTP API and dashboard")
    p.add_argument("--port", type=int, default=8471)
    p.add_argument("--mcp", action="store_true",
                   help="expose Quench as MCP tools instead of HTTP")

    args = parser.parse_args(argv)
    return {
        "status": cmd_status,
        "candidates": cmd_candidates,
        "seal": cmd_seal,
        "inspect": cmd_inspect,
        "revoke": cmd_revoke,
        "serve": cmd_serve,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
