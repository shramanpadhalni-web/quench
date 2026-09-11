"""Data-flow bindings — where a step's input comes from.

A sealed step records the *shape* of its input, which is enough to detect drift
and not enough to execute. Most real workflows chain: step 1 consumes what step
0 produced. Without knowing where a value comes from, Mill can only run
workflows whose steps are independent.

Bindings close that gap, and — this is the point — they are **inferred from the
traces**, not declared. If step 1's ``text`` is byte-identical to a value found
inside step 0's output, in the same place, in every trace, that is a data-flow
edge the agent was following all along.

## The path language

MCP wraps tool results in layers and then JSON-encodes the payload as a string,
so a real path has to be able to parse its way inward:

    ["items", 0, "Json", "content", 0, "text", "$json", "text"]
     dict key  idx  key     key     idx   key    parse    key

Segments are dict keys (str), list indices (int), or the literal ``"$json"``,
which parses the string at that point and continues into the result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator

#: Path segment meaning "parse the JSON string here and keep descending".
PARSE = "$json"

#: Values too small or too common to bind on. A binding to ``true`` or ``0``
#: would match everywhere and mean nothing.
MIN_BINDABLE_LEN = 8

#: Keys that carry agent commentary rather than data.
IGNORED_INPUT_KEYS = {"__tool_use_purpose"}


@dataclass(frozen=True)
class Binding:
    """One input field, resolved from an earlier step's output."""

    #: Field name in this step's input.
    field: str
    #: Index of the step that produced the value.
    from_step: int
    #: Path into that step's output.
    path: tuple[Any, ...]

    def to_dict(self) -> dict:
        return {"field": self.field, "from_step": self.from_step, "path": list(self.path)}

    @classmethod
    def from_dict(cls, data: dict) -> "Binding":
        return cls(
            field=data["field"],
            from_step=data["from_step"],
            path=tuple(data["path"]),
        )


def resolve(container: Any, path: tuple[Any, ...]) -> Any:
    """Follow a path into a structure, parsing JSON strings where told."""
    current = container
    for segment in path:
        if segment == PARSE:
            if not isinstance(current, str):
                raise KeyError(f"$json on non-string: {type(current).__name__}")
            current = json.loads(current)
        elif isinstance(segment, int):
            if not isinstance(current, (list, tuple)) or segment >= len(current):
                raise KeyError(f"index {segment} out of range")
            current = current[segment]
        else:
            if not isinstance(current, dict) or segment not in current:
                raise KeyError(f"key {segment!r} not found")
            current = current[segment]
    return current


def _walk(container: Any, prefix: tuple[Any, ...] = ()) -> Iterator[tuple[tuple, Any]]:
    """Yield (path, value) for every reachable leaf, descending into JSON strings."""
    if len(prefix) > 12:  # depth guard; real paths are ~8 segments
        return

    yield prefix, container

    if isinstance(container, dict):
        for key, value in container.items():
            yield from _walk(value, prefix + (key,))
    elif isinstance(container, (list, tuple)):
        for index, value in enumerate(container):
            yield from _walk(value, prefix + (index,))
    elif isinstance(container, str) and container.lstrip()[:1] in "{[":
        try:
            parsed = json.loads(container)
        except (json.JSONDecodeError, ValueError):
            return
        yield from _walk(parsed, prefix + (PARSE,))


def find_paths(container: Any, needle: Any) -> list[tuple[Any, ...]]:
    """Every path at which ``needle`` appears inside ``container``."""
    return [path for path, value in _walk(container) if value == needle]


def _bindable(value: Any) -> bool:
    """Only bind values distinctive enough for a match to be meaningful."""
    if isinstance(value, str):
        return len(value) >= MIN_BINDABLE_LEN
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return abs(value) >= 1000  # small integers collide constantly
    return False


def infer(traces: list) -> dict[int, tuple[Binding, ...]]:
    """Infer data-flow bindings that hold across **every** trace.

    A binding is kept only if the same field resolves from the same earlier step
    by the same path in all traces. One counterexample drops it — a data-flow
    edge that holds sometimes is not a data-flow edge.
    """
    if not traces:
        return {}

    # candidates[step][field] -> {(from_step, path): count}
    candidates: dict[int, dict[str, dict[tuple, int]]] = {}

    for trace in traces:
        calls = trace.calls
        outputs = [c.tool_response for c in calls]

        for index, call in enumerate(calls):
            for field, value in call.tool_input.items():
                if field in IGNORED_INPUT_KEYS or not _bindable(value):
                    continue
                for earlier in range(index):
                    for path in find_paths(outputs[earlier], value):
                        key = (earlier, path)
                        candidates.setdefault(index, {}).setdefault(field, {})
                        candidates[index][field][key] = (
                            candidates[index][field].get(key, 0) + 1
                        )

    total = len(traces)
    bindings: dict[int, tuple[Binding, ...]] = {}
    for step, fields in candidates.items():
        kept: list[Binding] = []
        for field, options in fields.items():
            # Must hold in every trace; shortest path wins a tie, since a
            # shallower path is the more direct data-flow edge.
            universal = [k for k, n in options.items() if n >= total]
            if not universal:
                continue
            from_step, path = min(universal, key=lambda k: (len(k[1]), k[0]))
            kept.append(Binding(field=field, from_step=from_step, path=path))
        if kept:
            bindings[step] = tuple(sorted(kept, key=lambda b: b.field))

    return bindings
