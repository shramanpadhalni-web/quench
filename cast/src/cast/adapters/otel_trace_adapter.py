"""TraceSource over OpenTelemetry GenAI spans. **The portable adapter.**

This is what makes Quench framework-agnostic. The hook adapter observes one
runtime; this observes anything instrumented to the OTel GenAI semantic
conventions — LangChain and LangGraph (natively, via LangSmith), and any
framework emitting `gen_ai.*` spans.

## What we read

Per the GenAI conventions, each tool invocation is a span:

    span name                  "execute_tool {gen_ai.tool.name}"
    gen_ai.operation.name      "execute_tool"
    gen_ai.tool.name           the tool
    gen_ai.tool.call.id        this invocation
    gen_ai.tool.call.arguments the input      <- what we compile from
    gen_ai.tool.call.result    the output     <- what purity is judged on

Spans are grouped into traces by `traceId`, which is the agent run — the same
role `session_id` plays for the hook adapter.

## The operational requirement, stated plainly

**Content capture is disabled by default in every OTel GenAI instrumentation.**
Without `recordInputs` / `recordOutputs` (names vary by SDK), the arguments and
result attributes are simply absent, and Quench has nothing to compile. This is
not a limitation we can engineer around: a trace without inputs and outputs does
not describe a workflow.

`describe_readiness()` exists to say so clearly rather than silently returning
nothing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

from ..compiler.trace import Trace, ToolCall
from ..ports.trace_source import TraceSource

#: Attribute keys, per the OTel GenAI semantic conventions.
OPERATION = "gen_ai.operation.name"
TOOL_NAME = "gen_ai.tool.name"
CALL_ID = "gen_ai.tool.call.id"
ARGUMENTS = "gen_ai.tool.call.arguments"
RESULT = "gen_ai.tool.call.result"
AGENT_NAME = "gen_ai.agent.name"

TOOL_OPERATION = "execute_tool"

DEFAULT_SPAN_FILE = Path(
    os.path.expanduser(
        os.environ.get("QUENCH_OTEL_SPANS", "~/.kiro/quench-traces/otel-spans.jsonl")
    )
)


def _unwrap(value: dict) -> Any:
    """OTLP wraps every attribute value in a typed envelope. Unwrap it."""
    if not isinstance(value, dict):
        return value
    for key, cast in (
        ("stringValue", str),
        ("boolValue", bool),
        ("intValue", int),
        ("doubleValue", float),
    ):
        if key in value:
            try:
                return cast(value[key])
            except (TypeError, ValueError):
                return value[key]
    if "arrayValue" in value:
        return [_unwrap(v) for v in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return {
            kv.get("key"): _unwrap(kv.get("value", {}))
            for kv in value["kvlistValue"].get("values", [])
        }
    return None


def _attributes(span: dict) -> dict[str, Any]:
    return {
        attr.get("key"): _unwrap(attr.get("value", {}))
        for attr in span.get("attributes", [])
        if attr.get("key")
    }


def _maybe_json(value: Any) -> Any:
    """Arguments and results arrive as JSON strings. Parse when they are.

    A tool whose argument is genuinely the string "42" stays a string; only
    well-formed JSON objects and arrays are parsed, because a false parse would
    silently change the structural signature a Cast is built from.
    """
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in "{[":
            try:
                return json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                return value
    return value


class OtelTraceAdapter(TraceSource):
    """Reads OTLP spans and yields traces Quench can compile.

    Accepts either a JSONL file of OTLP export payloads (one JSON object per
    line, as written by `quench serve`'s OTLP receiver) or a list of payloads
    supplied directly.
    """

    def __init__(
        self,
        span_file: Path | None = None,
        payloads: list[dict] | None = None,
    ) -> None:
        self.span_file = Path(span_file) if span_file else DEFAULT_SPAN_FILE
        self._payloads = payloads

    def describe(self) -> str:
        if self._payloads is not None:
            return "otel:in-memory"
        return f"otel-genai:{self.span_file}"

    # ------------------------------------------------------------------ read
    def _payload_stream(self) -> Iterator[dict]:
        if self._payloads is not None:
            yield from self._payloads
            return
        if not self.span_file.exists():
            return
        with self.span_file.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue  # a partial flush must not fail the whole compile

    def _spans(self) -> Iterator[dict]:
        """Flatten OTLP's resourceSpans -> scopeSpans -> spans nesting."""
        for payload in self._payload_stream():
            for resource in payload.get("resourceSpans", []):
                for scope in resource.get("scopeSpans", []):
                    yield from scope.get("spans", [])

    # --------------------------------------------------------------- readiness
    def describe_readiness(self) -> dict:
        """Whether these spans can be compiled, and if not, why not.

        Exists because the common failure is silent: instrumentation is on,
        spans arrive, and content capture is off — so every tool span lacks the
        arguments and result that make it a workflow rather than a timing record.
        """
        total = tool_spans = with_args = with_result = 0
        for span in self._spans():
            total += 1
            attrs = _attributes(span)
            if attrs.get(OPERATION) != TOOL_OPERATION:
                continue
            tool_spans += 1
            if attrs.get(ARGUMENTS) is not None:
                with_args += 1
            if attrs.get(RESULT) is not None:
                with_result += 1

        if tool_spans == 0:
            advice = (
                "No execute_tool spans found. Quench compiles tool sequences; "
                "LLM-only spans carry nothing to compile."
            )
        elif with_args == 0 or with_result == 0:
            advice = (
                "Tool spans found, but arguments and/or results are missing. "
                "OTel GenAI instrumentations disable content capture by default "
                "— enable recordInputs and recordOutputs (names vary by SDK). "
                "Without them there is no input to match on and no output to "
                "check purity against."
            )
        else:
            advice = "ready"

        return {
            "spans": total,
            "tool_spans": tool_spans,
            "with_arguments": with_args,
            "with_result": with_result,
            "ready": advice == "ready",
            "advice": advice,
        }

    # ----------------------------------------------------------------- traces
    def fetch_traces(self, skill_id: str | None = None) -> list[Trace]:
        # traceId is the agent run: the same role session_id plays elsewhere.
        by_trace: dict[str, list[dict]] = {}
        for span in self._spans():
            attrs = _attributes(span)
            if attrs.get(OPERATION) != TOOL_OPERATION:
                continue
            trace_id = span.get("traceId")
            if not trace_id:
                continue
            by_trace.setdefault(trace_id, []).append(span)

        traces: list[Trace] = []
        for trace_id, spans in by_trace.items():
            if skill_id is not None and skill_id != trace_id:
                continue
            # Child spans arrive unordered; start time is the execution order.
            spans.sort(key=lambda s: int(s.get("startTimeUnixNano") or 0))

            calls = []
            for seq, span in enumerate(spans):
                attrs = _attributes(span)
                arguments = _maybe_json(attrs.get(ARGUMENTS))
                if not isinstance(arguments, dict):
                    # Normalise, so the Cast IR sees a payload shape either way.
                    arguments = {"value": arguments} if arguments is not None else {}
                calls.append(
                    ToolCall(
                        session_id=trace_id,
                        cwd="",  # OTel carries no working directory
                        tool_name=attrs.get(TOOL_NAME) or span.get("name", "unknown"),
                        tool_input=arguments,
                        tool_response=_maybe_json(attrs.get(RESULT)),
                        seq=seq,
                    )
                )

            if calls:
                traces.append(
                    Trace(
                        session_id=trace_id,
                        calls=tuple(calls),
                        metadata={"source": self.describe()},
                    )
                )
        return traces
