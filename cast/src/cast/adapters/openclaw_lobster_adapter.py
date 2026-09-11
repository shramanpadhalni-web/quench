"""TraceSource over OpenClaw / Lobster session logs. **Stub - post-v1.**

Exists to keep the portability claim honest and testable. The ``TraceSource``
port asks only for *tool name, input, output, grouped by session* - a shape
Kiro CLI, Claude Code and OpenClaw all emit through near-identical hook
contracts.

Implementing this is what separates "a Kiro Crew plugin" from "a determinism
compiler for agent runtimes". See README, Portability.
"""

from __future__ import annotations

from ..compiler.trace import Trace
from ..ports.trace_source import TraceSource


class OpenClawLobsterAdapter(TraceSource):
    def describe(self) -> str:
        return "openclaw-lobster:not-implemented"

    def fetch_traces(self, skill_id: str | None = None) -> list[Trace]:
        raise NotImplementedError("Post-v1. See README, Portability.")
