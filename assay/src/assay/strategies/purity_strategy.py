"""Rejects Casts whose steps produce non-reproducible output.

**This is not a theoretical concern.** The very first trace captured from a
live Crew install contained a directory listing whose response embeds mtimes:

    -rw-r--r-- 1 1000 1000 99 Sep 09 14:15 .../quench-test.txt

That step is perfectly non-branching - ``no_branching_strategy`` would seal it
happily - and returns different bytes on every run. Sealing it would produce
an ingot that silently replays yesterday's timestamp.

Non-branching is a property of *control flow*. Determinism additionally
requires purity of *values*. Assay must check both.

See the empirical addendum in ADR-0000.
"""

from __future__ import annotations

import re

from ..ports.verification_strategy import (
    VerificationResult,
    VerificationStrategy,
    Verdict,
)

#: Patterns whose presence in a step's output means it cannot be reproduced.
VOLATILE_PATTERNS = (
    (re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"), "ISO timestamp"),
    (re.compile(r"\b[A-Z][a-z]{2} \d{2} \d{2}:\d{2}\b"), "ls-style mtime"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"), "UUID"),
    (re.compile(r"\bpid[= ]\d+", re.I), "process id"),
    (re.compile(r"\b(?:0x)?[0-9a-f]{12,}\b"), "address or long hex"),
)


class PurityStrategy(VerificationStrategy):
    """Flags steps whose outputs vary for reasons unrelated to their inputs."""

    def verify(self, cast, traces) -> VerificationResult:
        raise NotImplementedError(
            "Phase 2. Compare each step's output across traces; a step whose "
            "output differs while its input signature is identical is impure "
            "and blocks sealing."
        )
