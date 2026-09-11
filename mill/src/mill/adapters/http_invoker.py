"""ToolInvoker over HTTP. **The adapter for out-of-process and non-Python hosts.**

When the mesh is not Python, or Quench runs beside it rather than inside it,
the host exposes a tool endpoint and Mill posts to it:

    POST {base_url}/{tool_name}      {"arguments": {...}}
    -> 200 {"result": ...}  or the raw result body

The same boundary note as `callable_invoker` applies, and more sharply: the
host's endpoint is where authorisation and sandboxing live. Mill sends a tool
name and arguments; whether that call is permitted is the host's decision, made
the same way it is for the agent. Quench adds no privilege and removes none.

Standard library only — a dependency here would be a dependency in every host
that embeds Quench.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..ports.tool_invoker import ToolInvoker


class HttpToolInvoker(ToolInvoker):
    """Posts sealed steps to a host-provided tool endpoint."""

    def __init__(
        self,
        base_url: str,
        timeout: int = 60,
        headers: dict[str, str] | None = None,
        name: str = "http",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.name = name

    def describe(self) -> str:
        return f"http:{self.base_url}"

    def invoke(self, tool_name: str, payload: dict) -> Any:
        tool = tool_name.split("/")[-1].lstrip("@")
        url = f"{self.base_url}/{tool}"
        body = json.dumps({"arguments": payload}).encode()

        request = urllib.request.Request(url, data=body, headers=self.headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            # A refusal by the host is a step failure, not a Quench failure.
            # Mill halts the workflow and the caller falls back to the agent.
            raise RuntimeError(f"{tool}: HTTP {exc.code} {detail}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{tool}: {exc.reason}") from None

        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        # Accept either {"result": ...} or a bare result body.
        if isinstance(parsed, dict) and "result" in parsed:
            return parsed["result"]
        if isinstance(parsed, dict) and parsed.get("error"):
            raise RuntimeError(f"{tool}: {parsed['error']}")
        return parsed
