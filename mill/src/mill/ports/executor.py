"""Port: executing a sealed Cast.

Python for v1 (ADR-0002 revisited): Mill walks a handful of shell and file
operations, so there is no performance pressure yet, and a Rust binary is a
per-platform distribution problem before the idea has proven anything. This
port is what makes the later swap cheap.

**The security rule is absolute.** Mill executes through the identical
PreToolUse gate, OS sandbox and output redaction a live agent turn would.
A shortcut around the model call, never around the policy check.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Executor(ABC):
    @abstractmethod
    def execute(self, ingot, live_inputs: dict):
        """Run a sealed artifact. MUST call ``drift_check`` first."""

    @abstractmethod
    def drift_check(self, ingot, live_inputs: dict) -> bool:
        """Compare live inputs against the sealed signature. On mismatch,
        refuse and let the caller fall through to the live agent."""
