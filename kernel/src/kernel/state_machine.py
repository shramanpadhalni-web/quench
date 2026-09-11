"""The Shadow/Sealed lifecycle.

    Observing -> ShadowMode -> SealedMode
                    ^              |
                    +---- drift ---+

Two invariants that must survive implementation:

1. **Shadow Mode never has live side effects.** It only compares. Nothing is
   promoted without a record of matching the agent's *real* behaviour.
2. **Sealed Mode is not a one-way door.** Every execution re-checks live
   inputs against the sealed signature. Sealing is a cache, not a promise.
"""

from __future__ import annotations

from enum import Enum


class KernelState(Enum):
    OBSERVING = "observing"
    SHADOW = "shadow"
    SEALED = "sealed"
    REVOKED = "revoked"
