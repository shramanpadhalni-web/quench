"""The Shadow/Sealed lifecycle.

    Observing --verified candidate--> Shadow --N matches--> Sealed
        ^                               |                      |
        +------- output diverged -------+                      |
                                        ^                      |
                                        +----- drift detected -+

Two invariants that must survive every change to this file:

1. **Shadow Mode never has live side effects.** It compares only. Nothing is
   promoted on the strength of internal consistency -- only on a record of
   matching the agent's *real* behaviour.
2. **Sealed Mode is not a one-way door.** Every execution re-checks live inputs
   against the sealed signature. Sealing is a cache, not a promise.

Thresholds live in ``ports/promotion_policy.py``, not here. A credential
rotation and a CI migration should not share a risk tolerance, and hardcoding
one here would force them to.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum


class KernelState(Enum):
    OBSERVING = "observing"
    SHADOW = "shadow"
    SEALED = "sealed"
    REVOKED = "revoked"


class IllegalTransition(Exception):
    """A transition the lifecycle forbids.

    Notably: nothing reaches SEALED without passing through SHADOW. There is no
    skip-the-line path, including from the CLI -- a forced promotion still has
    to accumulate shadow evidence first.
    """


#: The only transitions the lifecycle permits.
LEGAL: dict[KernelState, frozenset[KernelState]] = {
    KernelState.OBSERVING: frozenset({KernelState.SHADOW, KernelState.REVOKED}),
    KernelState.SHADOW: frozenset(
        {KernelState.SEALED, KernelState.OBSERVING, KernelState.REVOKED}
    ),
    KernelState.SEALED: frozenset({KernelState.SHADOW, KernelState.REVOKED}),
    KernelState.REVOKED: frozenset(),  # terminal, deliberately
}


@dataclass
class SkillRecord:
    """Everything the Kernel knows about one workflow."""

    skill_id: str
    state: KernelState = KernelState.OBSERVING
    ingot_id: str | None = None
    #: Shadow comparison outcomes, oldest first. The promotion evidence.
    match_history: list[bool] = field(default_factory=list)
    drift_events: int = 0
    demotions: int = 0
    trace_count: int = 0
    note: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.created_at = self.created_at or now
        self.updated_at = self.updated_at or now

    # ------------------------------------------------------------ transitions
    def transition(self, to: KernelState, note: str = "") -> None:
        if to not in LEGAL[self.state]:
            allowed = sorted(s.value for s in LEGAL[self.state]) or ["none"]
            raise IllegalTransition(
                f"{self.skill_id}: {self.state.value} -> {to.value} is not "
                f"legal (allowed: {', '.join(allowed)})"
            )
        self.state = to
        self.note = note
        self.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    @property
    def consecutive_matches(self) -> int:
        """Matches since the last mismatch. Promotion counts this, not the total.

        A workflow that matched 40 times, diverged once, then matched twice has
        two consecutive matches -- not 42. The divergence is the signal, and
        counting cumulatively would let one good streak outvote a real failure.
        """
        count = 0
        for matched in reversed(self.match_history):
            if not matched:
                break
            count += 1
        return count

    # ----------------------------------------------------------- persistence
    def to_dict(self) -> dict:
        data = asdict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "SkillRecord":
        data = dict(data)
        data["state"] = KernelState(data.get("state", "observing"))
        return cls(**data)

    def describe(self) -> str:
        bits = [f"{self.skill_id[:16]}  {self.state.value}"]
        if self.state is KernelState.SHADOW:
            bits.append(
                f"{self.consecutive_matches} consecutive "
                f"({len(self.match_history)} compared)"
            )
        if self.ingot_id:
            bits.append(f"ingot {self.ingot_id[:12]}")
        if self.drift_events:
            bits.append(f"{self.drift_events} drift")
        if self.demotions:
            bits.append(f"{self.demotions} demotions")
        return "  ".join(bits)
