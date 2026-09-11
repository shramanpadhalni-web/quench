"""The Kernel — owns each workflow's lifecycle and the evidence behind it.

This is what turns Quench from a set of commands you run into a layer that
works. Without it, every promotion is a human decision; with it, a workflow
earns its own way to Sealed and loses it on its own too.

State is a single JSON file next to the Vault, so one backup captures traces,
artifacts and lifecycle together.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .ports.promotion_policy import DefaultPolicy, PromotionPolicy
from .state_machine import IllegalTransition, KernelState, SkillRecord

DEFAULT_STATE_FILE = Path(
    os.path.expanduser(
        os.environ.get("QUENCH_KERNEL_STATE", "~/.kiro/crew/quench-kernel.json")
    )
)


class Kernel:
    """Tracks every observed workflow and decides what may execute how."""

    def __init__(
        self,
        state_file: Path | None = None,
        policy: PromotionPolicy | None = None,
        policies: dict[str, PromotionPolicy] | None = None,
    ) -> None:
        self.state_file = Path(state_file) if state_file else DEFAULT_STATE_FILE
        self.default_policy = policy or DefaultPolicy()
        #: Per-skill overrides, wired at the composition root.
        self.policies = policies or {}
        self._records: dict[str, SkillRecord] = {}
        self._load()

    # ----------------------------------------------------------- persistence
    def _load(self) -> None:
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text())
        except (json.JSONDecodeError, OSError):
            # A corrupt state file must not take the agent down with it. We
            # start empty; workflows re-observe and re-earn their state.
            return
        for skill_id, record in data.get("skills", {}).items():
            try:
                self._records[skill_id] = SkillRecord.from_dict(record)
            except (TypeError, ValueError):
                continue

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "skills": {k: v.to_dict() for k, v in self._records.items()},
        }
        tmp = self.state_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
        tmp.replace(self.state_file)

    def policy_for(self, skill_id: str) -> PromotionPolicy:
        return self.policies.get(skill_id, self.default_policy)

    # ------------------------------------------------------------- accessors
    def record(self, skill_id: str) -> SkillRecord:
        if skill_id not in self._records:
            self._records[skill_id] = SkillRecord(skill_id=skill_id)
            self._save()
        return self._records[skill_id]

    def state_of(self, skill_id: str) -> KernelState:
        return self.record(skill_id).state

    def all(self) -> list[SkillRecord]:
        return sorted(self._records.values(), key=lambda r: r.skill_id)

    def by_state(self, state: KernelState) -> list[SkillRecord]:
        return [r for r in self.all() if r.state is state]

    # ----------------------------------------------------------- transitions
    def observe(self, skill_id: str, trace_count: int) -> SkillRecord:
        """Record that more evidence has accumulated for a workflow."""
        record = self.record(skill_id)
        record.trace_count = trace_count
        self._save()
        return record

    def enter_shadow(self, skill_id: str, ingot_id: str) -> SkillRecord:
        """Register a verified, signed candidate for shadow comparison.

        The caller must have run verification and signing already. The Kernel
        does not verify; conflating the two would let a state machine promote
        something unverified.
        """
        record = self.record(skill_id)
        if record.state is KernelState.SEALED:
            return record  # already past this
        record.ingot_id = ingot_id
        record.match_history = []
        record.transition(KernelState.SHADOW, "candidate verified and signed")
        self._save()
        return record

    def record_shadow_run(self, skill_id: str, matched: bool) -> SkillRecord:
        """Record one shadow comparison, and promote if the policy is satisfied.

        ``matched`` means Mill's output agreed with what the live agent actually
        produced -- not that Mill agreed with itself.
        """
        record = self.record(skill_id)
        if record.state is not KernelState.SHADOW:
            raise IllegalTransition(
                f"{skill_id}: shadow runs are only meaningful in SHADOW, "
                f"currently {record.state.value}"
            )

        record.match_history.append(bool(matched))
        policy = self.policy_for(skill_id)

        if not matched:
            # Confidence resets to Observing. Re-entering Shadow requires a
            # fresh verified candidate, not merely a few more good runs.
            record.transition(
                KernelState.OBSERVING, "shadow output diverged from the agent"
            )
        elif policy.should_promote(record.match_history):
            record.transition(
                KernelState.SEALED,
                f"{record.consecutive_matches} consecutive matches "
                f"under {policy.name}",
            )
        self._save()
        return record

    def record_drift(self, skill_id: str, reason: str = "") -> SkillRecord:
        """Demote on runtime drift. The fallback path already ran the agent."""
        record = self.record(skill_id)
        record.drift_events += 1
        if record.state is KernelState.SEALED:
            record.demotions += 1
            record.match_history = []
            record.transition(KernelState.SHADOW, reason or "drift detected")
        self._save()
        return record

    def revoke(self, skill_id: str, reason: str = "manual revoke") -> SkillRecord:
        """Immediate and terminal. Mill refuses anything revoked."""
        record = self.record(skill_id)
        if record.state is not KernelState.REVOKED:
            record.transition(KernelState.REVOKED, reason)
            self._save()
        return record

    # ------------------------------------------------------------- execution
    def may_execute(self, skill_id: str) -> tuple[bool, str]:
        """Whether Mill may answer for this workflow, and why not if not.

        Only SEALED authorises live execution. SHADOW runs happen through a
        separate path that discards side effects -- routing them here would be
        the single worst bug available in this system.
        """
        record = self.record(skill_id)
        if record.state is KernelState.SEALED:
            return True, "sealed"
        return False, f"state is {record.state.value}, not sealed"

    def summary(self) -> dict[str, int]:
        counts = {s.value: 0 for s in KernelState}
        for record in self.all():
            counts[record.state.value] += 1
        return counts
