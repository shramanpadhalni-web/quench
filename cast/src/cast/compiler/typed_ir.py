"""The Cast data model.

Shaped by real ``postToolUse`` payloads captured from Kiro Crew 0.5.0. See
``docs/adr/0000-crew-seam-verification.md`` for the verification record.

The critical structural decision is ADR-0000 finding 2: **a Cast step is one
operation, not one tool call.** Kiro batches several operations into a single
tool call (one ``read`` may open a file *and* list a directory). Modelling a
step as a tool call would let two genuinely different workflows compile to the
same node whenever they happened to batch alike.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def stable_hash(payload: Any) -> str:
    """Hash a JSON-ish structure deterministically (sorted keys, no whitespace)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def structural_signature(value: Any) -> Any:
    """Reduce a value to its *shape*, discarding leaf values.

    ``{"path": "/a/b.txt", "depth": 1}`` becomes ``{"path": "str", "depth": "int"}``.

    This is what lets one Cast serve runs whose inputs differ in content but
    not in form, and it is exactly what Assay compares a live input against
    before letting Mill run.
    """
    if isinstance(value, dict):
        return {k: structural_signature(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        inner = structural_signature(value[0]) if value else "empty"
        return ["list", inner]
    return type(value).__name__


@dataclass(frozen=True)
class Operation:
    """One unit of work inside a tool call - the atom of a Cast."""

    tool_name: str
    payload: dict[str, Any]
    purpose: str | None = None

    @property
    def signature(self) -> str:
        return stable_hash([self.tool_name, structural_signature(self.payload)])


@dataclass(frozen=True)
class CastStep:
    """A single ordered step in a compiled workflow."""

    index: int
    operation: Operation
    output_signature: str | None = None
    #: Input fields resolved from earlier steps' outputs. Inferred from traces,
    #: never declared. See `bindings.py`.
    bindings: tuple = ()

    @property
    def signature(self) -> str:
        return self.operation.signature


@dataclass(frozen=True)
class Cast:
    """A compiled, *not yet verified* candidate workflow.

    A Cast becomes an ``.ingot`` only once Assay verifies it and Hallmark
    signs it. Compiling one is cheap and implies no trust whatsoever.
    """

    cast_id: str
    skill_signature: str
    steps: tuple[CastStep, ...]
    trace_count: int
    source: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def signature(self) -> str:
        """Identity of the workflow shape. Stable across runs, not across edits."""
        return stable_hash([s.signature for s in self.steps])

    def __len__(self) -> int:
        return len(self.steps)
