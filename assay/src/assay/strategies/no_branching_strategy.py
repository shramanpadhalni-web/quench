"""v1 default: reject any candidate whose traces diverge in control flow.

Necessary but **not sufficient** - pair with ``PurityStrategy``.
"""

from __future__ import annotations

from ..ports.verification_strategy import (
    VerificationResult,
    VerificationStrategy,
    Verdict,
)


class NoBranchingStrategy(VerificationStrategy):
    def verify(self, cast, traces) -> VerificationResult:
        raise NotImplementedError("Phase 2.")
