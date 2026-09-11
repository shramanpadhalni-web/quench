"""Port: where execution traces come from.

Deliberately narrow. Any agent runtime that can report *what tool ran, with
what input, producing what output, grouped by session* can implement this -
Kiro Crew, Kiro CLI, Claude Code and OpenClaw all expose that shape.

This port is the reason Quench is a determinism compiler rather than a Kiro
Crew plugin.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..compiler.trace import Trace


class TraceSource(ABC):
    """Yields completed execution traces."""

    @abstractmethod
    def fetch_traces(self, skill_id: str | None = None) -> list[Trace]:
        """Return traces, optionally filtered to one skill.

        Implementations MUST be read-only. Nothing here may perturb the agent
        being observed - that is the whole premise of observation-earned
        determinism.
        """

    @abstractmethod
    def describe(self) -> str:
        """Human-readable identification, recorded in provenance."""
