"""Port: when a Shadow candidate may be promoted, and when it must be demoted.

Deliberately not a constant. A CI-migration workflow and a "rotate production
credentials" workflow should not share a risk tolerance, and a global threshold
would force them to.

Note the asymmetry, which is intentional: promotion requires sustained
evidence, demotion requires one event. A system that is slow to trust and quick
to doubt fails safe; the reverse fails silently.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PromotionPolicy(ABC):
    """Decides movement between Shadow and Sealed."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Recorded in the Hallmark provenance, so a consumer can see which
        risk tolerance an artifact was sealed under."""

    @abstractmethod
    def should_promote(self, match_history: list[bool]) -> bool:
        """Whether shadow evidence is sufficient to seal."""

    @abstractmethod
    def should_demote(self, drift_detected: bool, output_matched: bool) -> bool:
        """Whether to fall back to Shadow.

        Must be aggressive. Sealed Mode is never a one-way door, and the cost of
        an unnecessary demotion is a few model calls; the cost of a missed one
        is a wrong answer nobody notices.
        """


def _consecutive(match_history: list[bool]) -> int:
    count = 0
    for matched in reversed(match_history):
        if not matched:
            break
        count += 1
    return count


class DefaultPolicy(PromotionPolicy):
    """Ten consecutive shadow matches. Any drift demotes."""

    def __init__(self, threshold: int = 10) -> None:
        if threshold < 1:
            raise ValueError("threshold must be at least 1")
        self.threshold = threshold

    @property
    def name(self) -> str:
        return f"default(n={self.threshold})"

    def should_promote(self, match_history: list[bool]) -> bool:
        return _consecutive(match_history) >= self.threshold

    def should_demote(self, drift_detected: bool, output_matched: bool) -> bool:
        return drift_detected or not output_matched


class ConservativePolicy(PromotionPolicy):
    """For workflows where being wrong is expensive.

    Fifty consecutive matches, and a clean record: any prior mismatch anywhere
    in the history blocks promotion, not merely a recent one. Intended for
    anything touching credentials, money, or production state.
    """

    def __init__(self, threshold: int = 50) -> None:
        self.threshold = threshold

    @property
    def name(self) -> str:
        return f"conservative(n={self.threshold})"

    def should_promote(self, match_history: list[bool]) -> bool:
        if len(match_history) < self.threshold:
            return False
        # A single historical mismatch is disqualifying, not merely discounted.
        return all(match_history)

    def should_demote(self, drift_detected: bool, output_matched: bool) -> bool:
        return drift_detected or not output_matched


#: Resolvable by name from configuration, so a deployment can set a policy per
#: workflow without touching code.
POLICIES = {
    "default": DefaultPolicy,
    "conservative": ConservativePolicy,
}
