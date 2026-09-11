"""The `.ingot` file format.

An ingot is the whole point of the project: compiled agent behaviour as a
**file**. Once behaviour is a file it can be reviewed before it runs, signed,
versioned, revoked, moved between machines, and published to a registry.

Format: JSON, sorted keys. Human-readable on purpose — a consumer must be able
to read exactly what will execute before deciding to run it. A binary format
would be smaller and would forfeit the property that matters most.

    {
      "format": "quench/ingot",
      "version": 1,
      "cast":     { cast_id, skill_signature, steps[] },
      "hallmark": { provenance, signature, public_key, algorithm },
      "metadata": { ... }
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FORMAT = "quench/ingot"
VERSION = 1


@dataclass(frozen=True)
class SealedStep:
    """One step, as sealed. Values are gone; only the shape survives."""

    index: int
    tool_name: str
    #: Structural signature of the input — what drift is measured against.
    input_shape: Any
    #: sha256 over tool_name + input_shape.
    signature: str
    purpose: str | None = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "tool_name": self.tool_name,
            "input_shape": self.input_shape,
            "signature": self.signature,
            "purpose": self.purpose,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SealedStep":
        return cls(
            index=data["index"],
            tool_name=data["tool_name"],
            input_shape=data["input_shape"],
            signature=data["signature"],
            purpose=data.get("purpose"),
        )


@dataclass(frozen=True)
class Ingot:
    """A sealed, signed, portable workflow artifact."""

    cast_id: str
    skill_signature: str
    steps: tuple[SealedStep, ...]
    hallmark: dict
    metadata: dict = field(default_factory=dict)
    revoked: bool = False

    @property
    def ingot_id(self) -> str:
        return self.cast_id

    def to_dict(self) -> dict:
        return {
            "format": FORMAT,
            "version": VERSION,
            "cast": {
                "cast_id": self.cast_id,
                "skill_signature": self.skill_signature,
                "steps": [s.to_dict() for s in self.steps],
            },
            "hallmark": self.hallmark,
            "metadata": self.metadata,
            "revoked": self.revoked,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict) -> "Ingot":
        if data.get("format") != FORMAT:
            raise ValueError(f"not a Quench ingot: format={data.get('format')!r}")
        if data.get("version") != VERSION:
            raise ValueError(f"unsupported ingot version: {data.get('version')!r}")
        cast = data["cast"]
        return cls(
            cast_id=cast["cast_id"],
            skill_signature=cast["skill_signature"],
            steps=tuple(SealedStep.from_dict(s) for s in cast["steps"]),
            hallmark=data["hallmark"],
            metadata=data.get("metadata", {}),
            revoked=data.get("revoked", False),
        )

    @classmethod
    def load(cls, path: Path) -> "Ingot":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def __len__(self) -> int:
        return len(self.steps)


def from_cast(cast, hallmark, metadata: dict | None = None) -> Ingot:
    """Build an ingot from a verified Cast and its Hallmark."""
    from cast.compiler.typed_ir import structural_signature

    steps = tuple(
        SealedStep(
            index=step.index,
            tool_name=step.operation.tool_name,
            input_shape=structural_signature(step.operation.payload),
            signature=step.signature,
            purpose=step.operation.purpose,
        )
        for step in cast.steps
    )
    return Ingot(
        cast_id=cast.cast_id,
        skill_signature=cast.skill_signature,
        steps=steps,
        hallmark=hallmark.to_dict(),
        metadata={**(metadata or {}), "source": cast.source},
    )
