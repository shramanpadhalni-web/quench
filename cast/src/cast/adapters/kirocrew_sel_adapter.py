"""TraceSource over Crew's Signed Event Log. **Stub - not wired up in v1.**

Kept to demonstrate that ``TraceSource`` generalises, and as the place to
build from if the SEL ever records full tool arguments and results.

It does not today. Per ``sel.py``, a ``SecurityEvent`` carries
``operation``/``tool_kind``/``outcome`` plus a ``resources`` summary truncated
to ``_MAX_ARG_LEN = 500`` bytes after redaction, and no result payload at all.
That is sufficient for auditing and insufficient for compiling.

See ADR-0000 finding 3.
"""

from __future__ import annotations

from ..compiler.trace import Trace
from ..ports.trace_source import TraceSource


class KiroCrewSELAdapter(TraceSource):
    def describe(self) -> str:
        return "kirocrew-sel:not-implemented"

    def fetch_traces(self, skill_id: str | None = None) -> list[Trace]:
        raise NotImplementedError(
            "The SEL truncates tool arguments to 500 bytes and records no "
            "results, so a Cast cannot be compiled from it. Use "
            "HookTraceAdapter. See ADR-0000 finding 3."
        )
