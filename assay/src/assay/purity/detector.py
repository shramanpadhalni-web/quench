"""Single-trace purity detector — the shippable heuristic.

The oracle (`oracle.py`) needs N traces to establish whether a step's output is
reproducible. Production cannot afford that: a running system must judge a step
from the output in front of it.

This detector does that with pattern matching. It is necessarily imperfect, and
measuring *how* imperfect — precision and recall against the oracle — is
hypothesis H2 of the preregistration.

**The patterns below are FROZEN.** `docs/paper/PREREGISTRATION.md` §3 fixes them
as detector v1 and forbids adding, removing or modifying any of them after that
document was pushed (commit 0f64bd0, 2026-09-11). Improvements belong to a
separately reported "detector v2", clearly marked post-hoc.

Editing this table invalidates the preregistration. Don't.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Detector v1. Frozen by preregistration §3. Do not edit.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("iso_timestamp", re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")),
    ("ls_mtime", re.compile(r"\b[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}\b")),
    (
        "uuid",
        re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
        ),
    ),
    ("pid", re.compile(r"\bpid[=:\s]\s*\d+", re.IGNORECASE)),
    ("long_hex", re.compile(r"\b(?:0x)?[0-9a-f]{12,}\b")),
    ("epoch_seconds", re.compile(r"\b1[6-9]\d{8}\b")),
    (
        "duration",
        re.compile(
            r"(?:took|elapsed|duration).{0,20}?\b\d+(?:\.\d+)?\s*(?:ms|s|sec|seconds)\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class DetectorVerdict:
    """What the detector saw in one step's output."""

    impure: bool
    classes: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.impure


def inspect(serialised_output: str) -> DetectorVerdict:
    """Judge a single serialised output for signs of non-reproducibility."""
    classes: list[str] = []
    evidence: list[str] = []

    for name, pattern in PATTERNS:
        match = pattern.search(serialised_output)
        if match:
            classes.append(name)
            evidence.append(match.group(0)[:60])

    return DetectorVerdict(
        impure=bool(classes), classes=tuple(classes), evidence=tuple(evidence)
    )


@dataclass(frozen=True)
class ConfusionMatrix:
    """Detector performance against the oracle. Hypothesis H2."""

    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0

    @property
    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else 0.0

    @property
    def total(self) -> int:
        return (
            self.true_positive
            + self.false_positive
            + self.true_negative
            + self.false_negative
        )

    def plus(self, oracle_impure: bool, detector_impure: bool) -> "ConfusionMatrix":
        return ConfusionMatrix(
            true_positive=self.true_positive + (oracle_impure and detector_impure),
            false_positive=self.false_positive
            + (not oracle_impure and detector_impure),
            true_negative=self.true_negative
            + (not oracle_impure and not detector_impure),
            false_negative=self.false_negative
            + (oracle_impure and not detector_impure),
        )
