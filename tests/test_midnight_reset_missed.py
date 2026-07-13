"""
Tests for the missed-midnight-reset claim (`midnight_reset_missed`).

The 23:55 reset clears shd/pnd every night - so a shd/pnd that SURVIVED a day boundary
proves that every run since then was dropped (a long-blocking global condition, an inactive
instance whose take-over edge fell into a blackout, ...). Acting on that helper drives into
a days-old shading position; the claim turns the next trigger into a recovery instead.

The dangerous alternative design - claiming on plain helper AGE - is pinned here as a
negative: a clean helper may be legitimately old (a schedule whose opening/closing comes
from calendar time-control events has weekend-sized gaps, and the 23:55 reset only fires
with shading enabled - there is no daily-write guarantee), and claiming those runs would
swallow a real opening or closing with the catch-up off. The claim must require the
surviving shading state, not just the age.
"""
import types

import pytest

from test_restart_recovery import (
    BP,
    RECOVERY,
    _branch_gate,
    _render_bool,
    _top_var,
)


def _flag(*, stale_day, shd=False, pnd_start=False, pnd_end=False):
    return _render_bool(
        _top_var("midnight_reset_missed"), {},
        stale_day=stale_day,
        helper_state_shade=shd,
        helper_state_pending_start=pnd_start,
        helper_state_pending_end=pnd_end,
    )


class TestTheClaimCondition:
    def test_a_shading_that_survived_midnight_is_the_proof(self):
        assert _flag(stale_day=True, shd=True) is True

    @pytest.mark.parametrize("kw", ["pnd_start", "pnd_end"])
    def test_a_pending_that_survived_midnight_counts_too(self, kw):
        assert _flag(stale_day=True, **{kw: True}) is True

    def test_a_clean_old_helper_is_not_claimed(self):
        """The load-bearing negative. stale_day alone is NOT a blockade - a calendar
        time-control schedule skips whole weekends legitimately. Claiming such a run would
        turn Monday's opening into a hygiene run with the catch-up off: cover stays shut
        all morning."""
        assert _flag(stale_day=True) is False

    def test_a_same_day_shading_is_normal_operation(self):
        assert _flag(stale_day=False, shd=True) is False


class TestRecoveryGateClaimsIt:
    def GATE(self) -> str:
        return next(c for c in _branch_gate(RECOVERY) if "midnight_reset_missed" in str(c))

    def _run(self, tid, **over):
        args = dict(automation_resumed=False, instance_activated=False,
                    midnight_reset_missed=False)
        args.update(over)
        return _render_bool(self.GATE(), {}, trigger=types.SimpleNamespace(id=tid), **args)

    def test_any_trigger_is_claimed_while_the_proof_stands(self):
        for tid in ["t_open_1", "t_close_5", "t_shading_start_pending_1", "t_reset_timeout"]:
            assert self._run(tid, midnight_reset_missed=True) is True, tid

    @pytest.mark.parametrize("tid", ["t_manual_position", "t_manual_tilt"])
    def test_the_manual_triggers_are_exempt(self, tid):
        """Same exemption as for automation_resumed (#603): the manual handler only records,
        and the recovery must respect the man: 1 it writes."""
        assert self._run(tid, midnight_reset_missed=True) is False

    def test_normal_runs_are_not_claimed(self):
        assert self._run("t_open_1") is False


class TestLoadGatesReachTheClaimedRun:
    """Bug Pattern T, fifth recurrence prevented: the claimed run evaluates
    shading_start_warranted (recovered_pending) and the calendar boundaries (recovered_base)
    under ANY trigger id, so both load gates must match the claim, not just trigger ids."""

    def _gate(self, service: str):
        for step in BP["actions"]:
            if isinstance(step, dict) and "if" in step and service in str(step.get("then", "")):
                return step["if"]
        raise AssertionError(f"no load gate for {service}")

    @pytest.mark.parametrize("service", ["weather.get_forecasts", "calendar.get_events"])
    def test_a_claimed_run_loads_them(self, service):
        args = dict(automation_resumed=False, instance_activated=False,
                    midnight_reset_missed=True)
        conds = self._gate(service)
        target = next(c for c in conds if "midnight_reset_missed" in str(c))
        if isinstance(target, dict):
            assert any(_render_bool(c, {}, trigger=types.SimpleNamespace(id="t_close_1"), **args)
                       for c in target["or"])
        else:
            assert _render_bool(target, {}, trigger=types.SimpleNamespace(id="t_close_1"), **args)
