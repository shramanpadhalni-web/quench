"""OTel GenAI adapter — the portability claim, tested.

Payloads here are shaped as a real OTLP/JSON export: typed attribute envelopes,
resourceSpans → scopeSpans → spans nesting, and unordered child spans.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cast.adapters.otel_trace_adapter import OtelTraceAdapter


def span(trace_id, tool, args, result, start, *, content=True):
    attrs = [
        {"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}},
        {"key": "gen_ai.tool.name", "value": {"stringValue": tool}},
        {"key": "gen_ai.tool.call.id", "value": {"stringValue": f"call-{start}"}},
    ]
    if content:
        attrs += [
            {"key": "gen_ai.tool.call.arguments",
             "value": {"stringValue": json.dumps(args)}},
            {"key": "gen_ai.tool.call.result",
             "value": {"stringValue": json.dumps(result)}},
        ]
    return {
        "traceId": trace_id,
        "spanId": f"s{start}",
        "name": f"execute_tool {tool}",
        "startTimeUnixNano": str(start),
        "attributes": attrs,
    }


def payload(spans):
    return {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}


def llm_span(trace_id, start):
    """A chat span, which carries nothing Quench can compile."""
    return {
        "traceId": trace_id, "spanId": f"l{start}", "name": "chat gpt-4",
        "startTimeUnixNano": str(start),
        "attributes": [
            {"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}}
        ],
    }


def test_groups_spans_into_traces_by_trace_id():
    src = OtelTraceAdapter(payloads=[payload([
        span("t1", "read_claim", {"id": "c-1"}, {"amount": 500}, 100),
        span("t1", "check_policy", {"policy": "p-9"}, {"valid": True}, 200),
        span("t2", "read_claim", {"id": "c-2"}, {"amount": 900}, 300),
    ])])
    traces = src.fetch_traces()
    assert len(traces) == 2
    assert {len(t.calls) for t in traces} == {1, 2}


def test_orders_by_start_time_not_arrival():
    """Child spans arrive unordered; execution order is what a Cast encodes."""
    src = OtelTraceAdapter(payloads=[payload([
        span("t1", "third", {}, {}, 300),
        span("t1", "first", {}, {}, 100),
        span("t1", "second", {}, {}, 200),
    ])])
    (trace,) = src.fetch_traces()
    assert [c.tool_name for c in trace.calls] == ["first", "second", "third"]


def test_ignores_non_tool_spans():
    src = OtelTraceAdapter(payloads=[payload([
        llm_span("t1", 50),
        span("t1", "read_claim", {"id": "c-1"}, {"ok": True}, 100),
    ])])
    (trace,) = src.fetch_traces()
    assert [c.tool_name for c in trace.calls] == ["read_claim"]


def test_parses_json_arguments_and_results():
    src = OtelTraceAdapter(payloads=[payload([
        span("t1", "read_claim", {"id": "c-1", "depth": 2}, {"amount": 500}, 100),
    ])])
    (trace,) = src.fetch_traces()
    call = trace.calls[0]
    assert call.tool_input == {"id": "c-1", "depth": 2}
    assert call.tool_response == {"amount": 500}


def test_compiles_through_the_normal_pipeline():
    """The point of the adapter: OTel spans reach the compiler unchanged."""
    from cast.compiler.grouping import group_traces

    payloads = [payload([
        span(f"t{i}", "read_claim", {"id": f"c-{i}"}, {"amount": 100 + i}, 100),
        span(f"t{i}", "check_policy", {"policy": "p-1"}, {"valid": True}, 200),
    ]) for i in range(12)]

    groups = group_traces(OtelTraceAdapter(payloads=payloads).fetch_traces())
    assert len(groups) == 1
    assert len(groups[0]) == 12
    assert groups[0].tool_sequence == ("read_claim", "check_policy")


def test_readiness_reports_missing_content_capture():
    """The common silent failure: instrumentation on, content capture off."""
    src = OtelTraceAdapter(payloads=[payload([
        span("t1", "read_claim", {"id": "c-1"}, {"ok": True}, 100, content=False),
    ])])
    readiness = src.describe_readiness()
    assert readiness["tool_spans"] == 1
    assert readiness["with_arguments"] == 0
    assert not readiness["ready"]
    assert "recordInputs" in readiness["advice"]


def test_readiness_reports_no_tool_spans():
    src = OtelTraceAdapter(payloads=[payload([llm_span("t1", 50)])])
    readiness = src.describe_readiness()
    assert readiness["tool_spans"] == 0
    assert not readiness["ready"]


def test_readiness_ready_when_content_present():
    src = OtelTraceAdapter(payloads=[payload([
        span("t1", "read_claim", {"id": "c-1"}, {"ok": True}, 100),
    ])])
    assert src.describe_readiness()["ready"]


def test_missing_span_file_is_not_an_error(tmp_path):
    src = OtelTraceAdapter(span_file=tmp_path / "absent.jsonl")
    assert src.fetch_traces() == []


def test_partial_line_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "spans.jsonl"
    path.write_text(
        json.dumps(payload([span("t1", "a", {}, {}, 100)])) + "\n{partial"
    )
    assert len(OtelTraceAdapter(span_file=path).fetch_traces()) == 1
