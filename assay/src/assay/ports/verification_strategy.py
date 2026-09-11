"""Port: how a candidate Cast is verified.

Strategy pattern - a credential-rotating skill and a CI-migration skill must
not share a threshold. Swappable per-skill, never a global constant.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class Verdict(Enum):
    VERIFIED = "verified"
    REJECTED = "rejected"
    INSUFFICIENT_HISTORY = "insufficient_history"


@dataclass(frozen=True)
class VerificationResult:
    verdict: Verdict
    reason: str
    failing_step: int | None = None

    def __bool__(self) -> bool:
        return self.verdict is Verdict.VERIFIED


class VerificationStrategy(ABC):
    @abstractmethod
    def verify(self, cast, traces) -> VerificationResult:
        """Decide whether a Cast may be sealed. Must be conservative: any
        doubt is a rejection, and a rejection only means "keep observing"."""
