"""The trace model - what a TraceSource yields.

Field names mirror the verified hook payload exactly, so an adapter is a
near rename-free mapping rather than a translation layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from .typed_ir import Operation

#: Keys under which Kiro batches several operations into one tool call.
BATCH_KEYS = ("operations", "items", "calls")
#: Injected by the agent; describes intent, not part of the operation itself.
PURPOSE_KEY = "__tool_use_purpose"


@dataclass(frozen=True)
class ToolCall:
    """One ``postToolUse`` event."""

    session_id: str
    cwd: str
    tool_name: str
    tool_input: dict[str, Any]
    tool_response: Any | None = None
    seq: int = 0

    @property
    def purpose(self) -> str | None:
        return self.tool_input.get(PURPOSE_KEY)

    def operations(self) -> Iterator[Operation]:
        """Split a batched tool call into its constituent operations."""
        payload = {k: v for k, v in self.tool_input.items() if k != PURPOSE_KEY}
        for key in BATCH_KEYS:
            batch = payload.get(key)
            if isinstance(batch, list) and batch:
                for item in batch:
                    yield Operation(
                        tool_name=self.tool_name,
                        payload=item if isinstance(item, dict) else {"value": item},
                        purpose=self.purpose,
                    )
                return
        yield Operation(
            tool_name=self.tool_name, payload=payload, purpose=self.purpose
        )


@dataclass(frozen=True)
class Trace:
    """One session's ordered tool calls."""

    session_id: str
    calls: tuple[ToolCall, ...]
    prompt: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def operations(self) -> list[Operation]:
        return [op for call in self.calls for op in call.operations()]

    def __len__(self) -> int:
        return len(self.calls)
