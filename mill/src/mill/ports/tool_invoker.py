"""Port: how Mill actually runs a step.

**This is the security boundary.** Mill never touches the filesystem, a shell or
a network itself — every step goes out through a ToolInvoker, because that is
where the host platform's governance check, OS sandbox and output redaction
live.

An implementation that executed steps directly would be faster and would void
the entire security argument: Mill is a shortcut around the model call, never
around the policy check.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ToolInvoker(ABC):
    """Executes one tool call and returns its result."""

    @abstractmethod
    def invoke(self, tool_name: str, payload: dict) -> Any:
        """Run ``tool_name`` with ``payload``.

        Must raise on failure rather than returning a sentinel: Mill halts the
        workflow on the first failed step, and a silent failure would let later
        steps run against a broken precondition.
        """

    @abstractmethod
    def describe(self) -> str:
        """Human-readable identification, recorded in execution metadata."""
