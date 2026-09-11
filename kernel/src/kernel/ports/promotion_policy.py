"""Port: when a Shadow candidate may be promoted to Sealed.

Deliberately not a constant. A CI-migration skill and a "rotate prod
credentials" skill must not share a threshold.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PromotionPolicy(ABC):
    @abstractmethod
    def should_promote(self, match_history: list[bool]) -> bool: ...

    @abstractmethod
    def should_demote(self, drift_detected: bool) -> bool:
        """Demotion must be aggressive. Sealed Mode is never a one-way door."""
