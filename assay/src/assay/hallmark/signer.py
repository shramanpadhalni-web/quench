"""Ed25519 signing and the provenance record.

The Hallmark is what makes an ``.ingot`` trustworthy when it travels: who
verified it, against how many traces, under which strategy, when.
"""

from __future__ import annotations


class Hallmark:
    def sign(self, cast):
        raise NotImplementedError("Phase 2.")
