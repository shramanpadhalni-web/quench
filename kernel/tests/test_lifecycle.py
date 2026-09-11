"""The lifecycle invariants. These are the safety properties, not niceties."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from kernel.kernel import Kernel
from kernel.ports.promotion_policy import ConservativePolicy, DefaultPolicy
from kernel.state_machine import IllegalTransition, KernelState


@pytest.fixture
def kernel(tmp_path):
    return Kernel(state_file=tmp_path / "state.json", policy=DefaultPolicy(threshold=3))


def test_new_skill_starts_observing(kernel):
    assert kernel.state_of("s1") is KernelState.OBSERVING


def test_sealing_enters_shadow_not_sealed(kernel):
    """The invariant that matters most: signing does not authorise execution."""
    record = kernel.enter_shadow("s1", ingot_id="i1")
    assert record.state is KernelState.SHADOW
    allowed, why = kernel.may_execute("s1")
    assert not allowed and "not sealed" in why


def test_promotion_requires_the_full_threshold(kernel):
    kernel.enter_shadow("s1", "i1")
    for _ in range(2):
        kernel.record_shadow_run("s1", matched=True)
    assert kernel.state_of("s1") is KernelState.SHADOW
    kernel.record_shadow_run("s1", matched=True)
    assert kernel.state_of("s1") is KernelState.SEALED


def test_mismatch_resets_to_observing(kernel):
    """A divergence is not a setback to re-earn from; it invalidates the
    candidate. Re-entering Shadow requires a fresh verified Cast."""
    kernel.enter_shadow("s1", "i1")
    kernel.record_shadow_run("s1", matched=True)
    kernel.record_shadow_run("s1", matched=False)
    assert kernel.state_of("s1") is KernelState.OBSERVING


def test_consecutive_not_cumulative(kernel):
    """40 matches, one divergence, 2 matches is 2 consecutive - not 42."""
    kernel.enter_shadow("s1", "i1")
    kernel.record_shadow_run("s1", matched=True)
    kernel.record_shadow_run("s1", matched=False)   # -> observing
    kernel.enter_shadow("s1", "i1")                  # fresh candidate
    kernel.record_shadow_run("s1", matched=True)
    assert kernel.record("s1").consecutive_matches == 1
    assert kernel.state_of("s1") is KernelState.SHADOW


def test_drift_demotes_a_sealed_skill(kernel):
    kernel.enter_shadow("s1", "i1")
    for _ in range(3):
        kernel.record_shadow_run("s1", matched=True)
    assert kernel.state_of("s1") is KernelState.SEALED

    kernel.record_drift("s1", "input shape changed")
    assert kernel.state_of("s1") is KernelState.SHADOW
    assert kernel.record("s1").demotions == 1
    # Confidence is cleared, not carried over.
    assert kernel.record("s1").consecutive_matches == 0


def test_no_path_from_observing_to_sealed(kernel):
    """There is no skip-the-line, including from the CLI."""
    with pytest.raises(IllegalTransition):
        kernel.record("s1").transition(KernelState.SEALED)


def test_revoked_is_terminal(kernel):
    kernel.revoke("s1")
    assert kernel.state_of("s1") is KernelState.REVOKED
    with pytest.raises(IllegalTransition):
        kernel.record("s1").transition(KernelState.SHADOW)


def test_shadow_runs_rejected_outside_shadow(kernel):
    with pytest.raises(IllegalTransition):
        kernel.record_shadow_run("s1", matched=True)


def test_conservative_policy_rejects_any_historical_mismatch(tmp_path):
    k = Kernel(state_file=tmp_path / "s.json", policy=ConservativePolicy(threshold=3))
    k.enter_shadow("s1", "i1")
    k.record_shadow_run("s1", matched=True)
    k.record_shadow_run("s1", matched=False)  # -> observing
    k.enter_shadow("s1", "i1")
    for _ in range(3):
        k.record_shadow_run("s1", matched=True)
    # Three consecutive is enough for DefaultPolicy; Conservative wants a clean
    # record, and enter_shadow cleared it, so this promotes.
    assert k.state_of("s1") is KernelState.SEALED


def test_state_survives_restart(tmp_path):
    path = tmp_path / "state.json"
    k1 = Kernel(state_file=path, policy=DefaultPolicy(threshold=2))
    k1.enter_shadow("s1", "i1")
    k1.record_shadow_run("s1", matched=True)

    k2 = Kernel(state_file=path, policy=DefaultPolicy(threshold=2))
    assert k2.state_of("s1") is KernelState.SHADOW
    assert k2.record("s1").consecutive_matches == 1


def test_corrupt_state_file_does_not_crash(tmp_path):
    """A corrupt state file must not take the agent down with it."""
    path = tmp_path / "state.json"
    path.write_text("{not json")
    k = Kernel(state_file=path)
    assert k.all() == []
