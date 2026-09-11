"""Reports real model-call counts before and after sealing.

**This produces the number the entire project rests on** (§17). It must be a
measurement, never an estimate written into a dashboard component.

OPEN PROBLEM - unresolved, blocks Phase 4:

ADR-0000 finding 3 established that Crew's SEL cannot be this source. Its
event types are ``tool_invocation``, ``tool_approval``, ``tool_denial``,
``mcp_call`` and ``api_access``. **There is no model-call or token event.**

The brief assumed otherwise. A substitute source - session transcripts, or
``chat_done`` event accounting - must be identified and the baseline captured
BEFORE anything is sealed. A "before" number cannot be reconstructed after the
fact.
"""

raise NotImplementedError(
    "Blocked: no model-call source identified yet. See ADR-0000 finding 3."
)
