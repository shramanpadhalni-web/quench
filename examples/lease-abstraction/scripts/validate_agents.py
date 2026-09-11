#!/usr/bin/env python3
"""Validate agent configs before they are registered.

Catches the failure that cost us a run on 2026-09-11: an agent declared
``tools: ["@kirocrew-core"]`` while its ``mcpServers`` contained only
``lease-tools``. The tool did not exist, so the model — instructed to call it —
**narrated the call as plain text and invented the results.** No error was
raised, the turn succeeded, and the transcript looked entirely plausible.

That failure mode is silent by construction, so it has to be caught statically.

Usage:
    python3 scripts/validate_agents.py agents/*.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def validate(path: Path) -> list[str]:
    """Return a list of problems; empty means the config is sound."""
    problems: list[str] = []
    try:
        cfg = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return [f"invalid JSON: {exc}"]

    for field in ("name", "description", "prompt", "tools"):
        if not cfg.get(field):
            problems.append(f"missing or empty required field: {field}")

    servers = set(cfg.get("mcpServers", {}))
    declared = cfg.get("tools", []) or []
    allowed = cfg.get("allowedTools", []) or []

    # Every @server referenced in tools must be present in mcpServers.
    for entry in declared:
        if not entry.startswith("@"):
            continue
        server = entry[1:].split("/")[0]
        if server not in servers:
            problems.append(
                f"tools declares '{entry}' but mcpServers has no '{server}' "
                f"(present: {sorted(servers) or 'none'}). The tool will not "
                f"exist at runtime and the model may narrate the call instead "
                f"of making it."
            )

    # Every allowedTools entry must be covered by a declared tool.
    for entry in allowed:
        if not entry.startswith("@"):
            continue
        server = entry[1:].split("/")[0]
        if server not in servers:
            problems.append(
                f"allowedTools references '{entry}' but mcpServers has no "
                f"'{server}'"
            )
        if not any(d == f"@{server}" or d == entry for d in declared):
            problems.append(
                f"allowedTools references '{entry}' but tools does not declare "
                f"'@{server}'"
            )

    # An MCP server nobody uses is usually a copy-paste leftover.
    for server in servers:
        if not any(d.startswith(f"@{server}") for d in declared):
            problems.append(f"mcpServers defines '{server}' but no tool uses it")

    # A local server needs a cwd, or relative paths inside it break.
    for server, spec in (cfg.get("mcpServers") or {}).items():
        if not spec.get("command"):
            problems.append(f"mcpServers['{server}'] has no command")
        elif not Path(spec["command"]).exists():
            problems.append(
                f"mcpServers['{server}'] command not found: {spec['command']}"
            )

    return problems


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv[1:]]
    if not paths:
        print(__doc__)
        return 2

    failed = 0
    for path in sorted(paths):
        problems = validate(path)
        if problems:
            failed += 1
            print(f"\n✗ {path.name}")
            for problem in problems:
                print(f"    {problem}")
        else:
            print(f"✓ {path.name}")

    if failed:
        print(f"\n{failed} of {len(paths)} configs have problems.")
        return 1
    print(f"\nAll {len(paths)} configs valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
