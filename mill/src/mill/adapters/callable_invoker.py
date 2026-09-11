"""ToolInvoker over in-process callables. **The adapter for embedded use.**

For any Python agent framework — LangChain, LlamaIndex, AgentSquad, a custom
loop — where the tools are functions the host already holds. The host hands
Quench its own tool registry, and Mill calls exactly what the agent called.

## On the security boundary

The `ToolInvoker` port is where governance, sandboxing and output redaction
live. **This adapter adds none of those, and that is deliberate.** It calls the
host's own tool objects through the host's own path, so whatever the host
enforces around a tool call still applies — and nothing Quench does can weaken
it, because Quench never touches the tool directly.

The corollary matters and should be said plainly: if a host has no sandbox,
Mill executing through this adapter has no sandbox either. Quench does not add
safety a runtime lacks; it preserves the safety a runtime has.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from ..ports.tool_invoker import ToolInvoker


class CallableInvoker(ToolInvoker):
    """Executes sealed steps against a registry of host-supplied callables.

        invoker = CallableInvoker({
            "fetch_claim": fetch_claim,
            "lookup_policy": lookup_policy,
        })
        Mill(invoker=invoker).execute(ingot, live_inputs)
    """

    def __init__(
        self,
        tools: dict[str, Callable[..., Any]],
        name: str = "callables",
        strict: bool = True,
    ) -> None:
        self.tools = dict(tools)
        self.name = name
        #: When strict, an unknown tool raises rather than being skipped. A
        #: silently skipped step would let a workflow "succeed" having done
        #: less than it was sealed to do.
        self.strict = strict

    def describe(self) -> str:
        return f"callable:{self.name}({len(self.tools)} tools)"

    def _resolve(self, tool_name: str) -> Callable[..., Any]:
        # Sealed names may carry a server prefix ("@lease-tools/read_lease")
        # depending on which TraceSource observed them. Try both.
        for candidate in (tool_name, tool_name.split("/")[-1].lstrip("@")):
            if candidate in self.tools:
                return self.tools[candidate]
        raise KeyError(
            f"no tool named {tool_name!r} in this registry "
            f"(have: {', '.join(sorted(self.tools)) or 'none'})"
        )

    def invoke(self, tool_name: str, payload: dict) -> Any:
        func = self._resolve(tool_name)

        # Call by keyword where the signature allows it, since that is how the
        # arguments were recorded. Fall back to a single positional payload for
        # tools that take one argument object (LangChain's convention).
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            return func(payload)

        accepts_kwargs = any(
            p.kind is inspect.Parameter.VAR_KEYWORD
            for p in signature.parameters.values()
        )
        named = {
            p.name for p in signature.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                          inspect.Parameter.KEYWORD_ONLY)
        }

        if accepts_kwargs or (payload and set(payload) <= named):
            return func(**payload)
        if len(signature.parameters) == 1:
            return func(payload)
        raise TypeError(
            f"{tool_name}: cannot map sealed arguments {sorted(payload)} onto "
            f"signature {signature}"
        )


def from_langchain_tools(tools, name: str = "langchain") -> CallableInvoker:
    """Build an invoker from LangChain tool objects.

    LangChain tools expose ``.name`` and ``.invoke(input)``. Nothing here
    imports LangChain — duck typing keeps it an optional dependency, which
    matters because Quench should not pull a framework into a host that does
    not already have it.
    """
    registry: dict[str, Callable[..., Any]] = {}
    for tool in tools:
        tool_name = getattr(tool, "name", None)
        if not tool_name:
            continue
        invoke = getattr(tool, "invoke", None) or getattr(tool, "run", None)
        if invoke is None:
            continue
        # LangChain tools take one input object, not keywords.
        registry[tool_name] = (lambda fn: lambda payload: fn(payload))(invoke)
    return CallableInvoker(registry, name=name)
