"""ToolInvoker that calls an MCP server over stdio.

The v1 invoker. Mill re-executes a sealed workflow by making the same MCP calls
the agent made — same server, same tool names, same arguments — with the model
removed from the decision about *which* call to make.

Note what this does and does not do. It re-runs the real tools against live
inputs, with real side effects. It is **not** a cache: a cache replays a stored
result; this performs the work.

The server is held open for the life of one execution. Piping every request at
once and closing stdin does not work — the server reaches EOF and shuts down
after answering `initialize`, before any `tools/call` is handled.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from ..ports.tool_invoker import ToolInvoker


class McpToolInvoker(ToolInvoker):
    """Speaks MCP over stdio to a locally-spawned server.

    One process per execution, not one per call: the handshake costs ~200ms and
    a sealed workflow makes several calls. A fresh process per execution also
    means no state can carry between runs — the property you want when the whole
    claim is reproducibility.
    """

    def __init__(
        self, command: list[str], server_name: str = "mcp", timeout: int = 60
    ) -> None:
        self.command = command
        self.server_name = server_name
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None
        self._next_id = 1

    def describe(self) -> str:
        return f"mcp-stdio:{self.server_name}"

    # ------------------------------------------------------------------ wire
    def _send(self, message: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()

    def _read_reply(self, expect_id: int) -> dict:
        assert self._proc and self._proc.stdout
        while True:
            line = self._proc.stdout.readline()
            if not line:
                stderr = ""
                if self._proc.stderr:
                    stderr = self._proc.stderr.read()[:300]
                raise RuntimeError(
                    f"{self.server_name} closed the stream"
                    + (f" (stderr: {stderr})" if stderr else "")
                )
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == expect_id:
                return message
            # Notifications and unrelated ids are skipped.

    def _ensure_started(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        self._proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._send(
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "quench-mill", "version": "0.1.0"},
                },
            }
        )
        self._read_reply(self._next_id)
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    # ------------------------------------------------------------------- api
    def invoke(self, tool_name: str, payload: dict) -> Any:
        # "@lease-tools/read_lease" -> "read_lease"
        tool = tool_name.split("/")[-1] if "/" in tool_name else tool_name

        self._ensure_started()
        request_id = self._next_id
        self._next_id += 1

        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": tool, "arguments": payload},
            }
        )
        message = self._read_reply(request_id)

        if "error" in message:
            raise RuntimeError(f"{tool}: {message['error']}")
        result = message.get("result", {})
        if result.get("isError"):
            raise RuntimeError(f"{tool}: {result}")
        return result

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
        self._proc = None

    def __enter__(self) -> "McpToolInvoker":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
