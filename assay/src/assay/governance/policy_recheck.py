"""Re-applies Crew's ``POLICY ∩ PROFILE`` check to every step at seal time.

A Cast containing a step Crew's own governance would deny must be **rejected
at compile time**, not merely blocked at runtime. Mill is a shortcut around
the model call - never around the policy check.

Sources (read-only):
  ``~/.kiro/crew/security_policy.json``   the enterprise ceiling
  ``~/.kiro/crew/profiles/``               per-surface narrowing

A running app may narrow the allowed scope but can never loosen the ceiling.
"""

from __future__ import annotations


class PolicyRecheck:
    def check(self, cast) -> None:
        raise NotImplementedError("Phase 2. See SECURITY.md.")
