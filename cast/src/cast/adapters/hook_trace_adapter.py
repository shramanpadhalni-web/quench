"""TraceSource over Kiro's ``postToolUse`` hook output. **The v1 adapter.**

Reads the JSONL written by ``~/.kiro/hooks/quench-trace-post.sh``. Verified
against Kiro Crew 0.5.0 / kiro-cli 2.21.2 - see the empirical addendum in
``docs/adr/0000-crew-seam-verification.md``.

Why not the Signed Event Log? The SEL records ``tool_invocation`` events but
truncates arguments to 500 bytes and stores no results at all, so a Cast
cannot be compiled from it. The hook delivers full, untruncated ``tool_input``
and ``tool_response`` grouped by ``session_id``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..compiler.trace import Trace, ToolCall
from ..ports.trace_source import TraceSource

DEFAULT_TRACE_FILE = Path(
    os.environ.get(
        "QUENCH_TRACE_FILE", os.path.expanduser("~/.kiro/quench-traces/raw.jsonl")
    )
)


class HookTraceAdapter(TraceSource):
    """Groups captured hook events into per-session traces."""

    def __init__(self, trace_file: Path | None = None) -> None:
        self.trace_file = Path(trace_file) if trace_file else DEFAULT_TRACE_FILE

    def describe(self) -> str:
        return f"kiro-posttooluse-hook:{self.trace_file}"

    def _events(self):
        if not self.trace_file.exists():
            return
        with self.trace_file.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # A partially flushed line. Skip it rather than fail the
                    # whole compile - the observer must never be fragile.
                    continue
                if isinstance(event, dict) and event.get("hook_event_name"):
                    yield event

    def fetch_traces(self, skill_id: str | None = None) -> list[Trace]:
        sessions: dict[str, list[dict]] = {}
        prompts: dict[str, str] = {}

        for event in self._events():
            sid = event.get("session_id")
            if not sid:
                continue
            name = event["hook_event_name"]
            if name == "postToolUse":
                sessions.setdefault(sid, []).append(event)
            elif name == "userPromptSubmit" and sid not in prompts:
                prompts[sid] = event.get("prompt", "")

        traces: list[Trace] = []
        for sid, events in sessions.items():
            calls = tuple(
                ToolCall(
                    session_id=sid,
                    cwd=e.get("cwd", ""),
                    tool_name=e.get("tool_name", "unknown"),
                    tool_input=e.get("tool_input", {}) or {},
                    tool_response=e.get("tool_response"),
                    seq=i,
                )
                for i, e in enumerate(events)
            )
            trace = Trace(
                session_id=sid,
                calls=calls,
                prompt=prompts.get(sid),
                metadata={"source": self.describe()},
            )
            if skill_id is None or skill_id == sid:
                traces.append(trace)
        return traces
