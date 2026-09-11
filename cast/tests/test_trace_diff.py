"""Trace diffing is the gate that decides what may ever be sealed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cast.compiler.trace import Trace, ToolCall
from cast.compiler.trace_diff import diff_traces


def _call(tool, payload, sid="s"):
    return ToolCall(session_id=sid, cwd="/w", tool_name=tool, tool_input=payload)


def _trace(sid, calls):
    return Trace(session_id=sid, calls=tuple(calls))


def test_rejects_insufficient_history():
    traces = [_trace(f"s{i}", [_call("read", {"path": "/a"})]) for i in range(3)]
    result = diff_traces(traces, minimum=5)
    assert not result
    assert "2 more required" in result.reason


def test_accepts_identical_shapes_with_differing_values():
    # Same shape, different leaf values - this is the whole point.
    traces = [
        _trace(f"s{i}", [_call("read", {"path": f"/file{i}.txt", "depth": 1})])
        for i in range(5)
    ]
    result = diff_traces(traces, minimum=5)
    assert result, result.reason


def test_rejects_divergent_step_count():
    traces = [_trace(f"s{i}", [_call("read", {"path": "/a"})]) for i in range(4)]
    traces.append(_trace("s4", [_call("read", {"path": "/a"}), _call("write", {"path": "/b"})]))
    result = diff_traces(traces, minimum=5)
    assert not result
    assert "branches" in result.reason


def test_batched_operations_split_into_separate_steps():
    """ADR-0000 finding 2: step granularity is the operation, not the call."""
    batched = _call("read", {"operations": [{"path": "/a"}, {"path": "/b"}]})
    trace = _trace("s", [batched])
    assert len(trace.operations()) == 2


def test_purpose_is_extracted_not_treated_as_input():
    call = _call("read", {"__tool_use_purpose": "why", "path": "/a"})
    (op,) = list(call.operations())
    assert op.purpose == "why"
    assert "__tool_use_purpose" not in op.payload
