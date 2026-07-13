"""
Tests for the hand-over switch (`instance_active`) - several CCA automations, one cover.

Each instance has its own status helper and its own settings; an automation outside CCA
decides which one is in charge. The mechanism is two pieces, and neither works alone:

  1. The GATE (global condition) - while the switch is off this instance does NOTHING.
     Not even record a cover movement as a manual override: the other instance made it,
     and a stored `man: 1` would come back to block this one's own take-over.
  2. The TAKE-OVER - switching on re-derives everything (schedule, window, presence, force,
     shading) and positions the cover the way THIS instance's settings want it.

Piece 2 is what makes piece 1 legal at all. A gate that stops runs orphans every latching
trigger of the off period (a due shading execution, an override reset) - the CLAUDE.md rule
is that such a gate needs an exemption, a repair path, or a re-evaluation in the recovery.
This one takes the third option, which is why most of these tests are about the recovery.

Mirrors the resume mechanism (Half 1b) deliberately: `t_instance_activated` is only the
prompt, `instance_activated` is the claim - so a swallowed trigger edge cannot lose the
take-over. The templates are extracted verbatim from the blueprint.
"""
import datetime
import types

import pytest

from test_restart_recovery import (
    BP,
    NOW,
    NOW_TS,
    RECOVERY,
    _branch,
    _branch_gate,
    _condition,
    _render,
    _render_bool,
    _top_var,
)

SWITCH = "input_boolean.cca_summer"


def _trigger(trigger_id: str) -> list[dict]:
    return [t for t in BP["triggers"] if t.get("id") == trigger_id]


def _trigger_on(entity: str, trigger_id: str) -> list[dict]:
    return [t for t in BP["triggers"]
            if t.get("id") == trigger_id and t.get("entity_id") == entity]


# ════════════════════════════════════════════════════════════════════════════
# The gate - while the switch is off, this instance does not exist
# ════════════════════════════════════════════════════════════════════════════
class TestGate:
    def GATE(self) -> str:
        return _condition("instance_active")

    def _run(self, state, *, configured=True):
        return _render_bool(
            self.GATE(),
            {SWITCH: state} if state is not None else {},
            instance_active=SWITCH if configured else [],
        )

    def test_unconfigured_runs_exactly_as_before(self):
        """The default. Nobody who runs a single CCA automation may notice this feature."""
        assert self._run(None, configured=False) is True

    @pytest.mark.parametrize("state", ["on", "true"])
    def test_the_active_instance_runs(self, state):
        assert self._run(state) is True

    @pytest.mark.parametrize("state", ["off", "false"])
    def test_the_inactive_instance_is_blocked(self, state):
        assert self._run(state) is False

    def test_an_unavailable_switch_blocks(self):
        """CCA cannot tell whether it owns the cover, and a second instance may. Parking is
        the safe read in both directions: if the OTHER instance is the active one, nothing is
        lost at all. Self-heals via the switch's own t_recovery trigger."""
        assert self._run("unavailable") is False

    def test_a_gone_switch_is_let_through_to_the_diagnostics(self):
        """Bug Pattern AF: a disabled/deleted entity never comes back, so a gate that merely
        blocks kills every run for good and nothing ever says why. It passes the gate and is
        stopped - loudly - by the mandatory entity validation."""
        assert self._run(None, configured=True) is True   # not in the state machine at all

    def test_the_gate_has_no_trigger_exemptions(self):
        """The contact and manual triggers are exempt from the contact gate. They must NOT be
        exempt here: an inactive instance that recorded the other instance's drive as a manual
        override would come back with man == 1 and refuse to position the cover."""
        assert "trigger" not in self.GATE()


class TestGoneSwitchStopsTheRun:
    def _validation(self) -> dict:
        return _branch("Configured entity is disabled or deleted")

    def test_it_stops_the_run(self):
        stop = next(s for s in self._validation()["then"] if "if" in s)
        assert "instance_active in missing_entities" in str(stop["if"])
        assert any("stop" in s for s in stop["then"])

    def test_it_is_logged_as_an_error_not_a_warning(self):
        log = next(s for s in self._validation()["then"]
                   if s.get("action") == "system_log.write")
        assert _render(log["data"]["level"], {}, missing_critical=[],
                       missing_entities=[SWITCH], instance_active=SWITCH) == "error"

    def test_the_message_says_a_second_instance_may_own_the_cover(self):
        log = next(s for s in self._validation()["then"]
                   if s.get("action") == "system_log.write")
        msg = _render(log["data"]["message"], {}, friendly_name="Bedroom",
                      missing_entities=[SWITCH], missing_critical=[], missing_contacts=[],
                      helper_state_window="cls", instance_active=SWITCH)
        assert "two automations driving the same cover" in msg


# ════════════════════════════════════════════════════════════════════════════
# The triggers
# ════════════════════════════════════════════════════════════════════════════
class TestTriggers:
    def test_the_activation_trigger_fires_on_the_on_flank(self):
        """Two shapes share the id: the plain off -> on flank (no value configured), and the
        value variant that fires on any valid -> valid change (arrivals at a foreign value are
        dropped by the gate). Both are restart-proof by construction - a restart returns the
        entity from unavailable, which neither from: [off, false] nor not_from matches - and
        the catch-up exemption in recovery_catch_up relies on exactly that."""
        t = _trigger("t_instance_activated")
        assert len(t) == 2
        classic = next(x for x in t if "from" in x)
        value = next(x for x in t if "not_from" in x)
        assert classic["from"] == ["off", "false"] and classic["to"] == ["on", "true"]
        assert value["not_from"] == ["unavailable", "unknown"]
        assert value["not_to"] == ["unavailable", "unknown"]

    def test_exactly_one_variant_is_armed(self):
        """The enabled gates are complementary in instance_active_value - never both, never
        neither (while the entity is configured)."""
        classic = next(x for x in _trigger("t_instance_activated") if "from" in x)
        value = next(x for x in _trigger("t_instance_activated") if "not_from" in x)
        for val, want_classic in [("", True), ("  ", True), ("Sommer", False)]:
            assert _render_bool(classic["enabled"], {}, instance_active=SWITCH,
                                instance_active_value=val) is want_classic, val
            assert _render_bool(value["enabled"], {}, instance_active=SWITCH,
                                instance_active_value=val) is (not want_classic), val

    def test_the_activation_trigger_is_not_gated_on_the_recovery_opt_in(self):
        """The opt-in guards against the cover moving after a RESTART. An activation is not a
        restart - it is an explicit "you are in charge now", and an instance that takes over
        without positioning the cover has done nothing at all."""
        for t in _trigger("t_instance_activated"):
            assert "is_recovery_enabled" not in str(t["enabled"])

    def test_the_switch_is_also_a_recovery_source(self):
        """While it has no usable state the gate blocks every run, exactly like the cover or a
        contact - so its outage eats the latching triggers the same way. Ungated like the five
        gate sources - but unlike them its return run is NOT hygiene-only, it takes over
        (TestSwitchDropoutTakesOver)."""
        t = _trigger_on("instance_active", "t_recovery")
        assert len(t) == 1
        assert "is_recovery_enabled" not in str(t[0]["enabled"])
        assert t[0]["from"] == ["unavailable", "unknown"]


# ════════════════════════════════════════════════════════════════════════════
# The claim - a swallowed activation edge must not lose the take-over
# ════════════════════════════════════════════════════════════════════════════
class TestInstanceActivatedClaim:
    def TPL(self) -> str:
        return _top_var("instance_activated")

    def _run(self, *, helper_written, switched_on, state="on", configured=True):
        return _render_bool(
            self.TPL(),
            {SWITCH: state},
            {SWITCH: switched_on},
            instance_active=SWITCH if configured else [],
            helper_ts_write=helper_written,
        )

    def test_switched_on_and_not_reconciled_yet_is_a_take_over(self):
        assert self._run(helper_written=NOW_TS - 3600, switched_on=NOW) is True

    def test_a_fresh_instance_that_never_ran_is_a_take_over(self):
        """Unlike automation_resumed, an unwritten helper (t == 0) counts here: a brand-new
        instance being switched on for the first time is exactly the event this exists for."""
        assert self._run(helper_written=0, switched_on=NOW) is True

    def test_the_helper_write_clears_it(self):
        """Self-clearing, like automation_resumed - otherwise every run after the take-over
        would be claimed by the recovery and the dispatch would never see a trigger again."""
        assert self._run(helper_written=NOW_TS,
                         switched_on=NOW - datetime.timedelta(hours=1)) is False

    def test_an_inactive_switch_is_not_a_take_over(self):
        assert self._run(helper_written=0, switched_on=NOW, state="off") is False

    def test_unconfigured_is_never_a_take_over(self):
        assert self._run(helper_written=0, switched_on=NOW, configured=False) is False

    def test_a_gone_switch_is_not_a_take_over(self):
        """states[x] is none - it cannot be read at all, so it cannot claim anything. The run
        is stopped by the entity validation instead."""
        assert _render_bool(self.TPL(), {}, instance_active=SWITCH, helper_ts_write=0) is False

    def test_a_dropdown_option_claims_like_a_switch(self):
        assert _render_bool(self.TPL(), {SWITCH: "Sommer"}, {SWITCH: NOW},
                            instance_active=SWITCH, helper_ts_write=0,
                            instance_active_on_states=["Sommer"]) is True

    def test_a_foreign_option_does_not_claim(self):
        assert _render_bool(self.TPL(), {SWITCH: "Winter"}, {SWITCH: NOW},
                            instance_active=SWITCH, helper_ts_write=0,
                            instance_active_on_states=["Sommer"]) is False


# ════════════════════════════════════════════════════════════════════════════
# The value variant - one dropdown for N instances, or an inverted boolean
# ════════════════════════════════════════════════════════════════════════════
class TestActiveValue:
    """instance_active_value makes the entity count as on while it shows exactly this value.
    A dropdown (input_select) can only ever show one option, so mutual exclusion between the
    instances is guaranteed by construction - no switching automation needed. 'off' on a
    shared boolean gives two complementary instances the same way."""

    def GATE(self) -> str:
        return _condition("instance_active")

    def _gate(self, state, value):
        return _render_bool(self.GATE(), {SWITCH: state},
                            instance_active=SWITCH, instance_active_value=value)

    def test_the_matching_option_runs(self):
        assert self._gate("Sommer", "Sommer") is True

    def test_a_foreign_option_is_blocked(self):
        assert self._gate("Winter", "Sommer") is False

    def test_the_inverted_boolean(self):
        assert self._gate("off", "off") is True
        assert self._gate("on", "off") is False

    def test_an_unavailable_entity_still_blocks(self):
        """The value never matches an invalid state, so the availability semantics of the
        plain switch (block, self-heal via t_recovery) carry over unchanged."""
        assert self._gate("unavailable", "Sommer") is False

    def test_the_value_is_trimmed(self):
        assert self._gate("Sommer", " Sommer ") is True

    def test_an_empty_value_keeps_the_plain_switch_semantics(self):
        assert self._gate("on", "") is True
        assert self._gate("off", "") is False

    def test_the_on_states_derivation(self):
        tpl = _top_var("instance_active_on_states")
        assert _render(tpl, {}, instance_active_value="") == "['on', 'true']"
        assert _render(tpl, {}, instance_active_value=" Sommer ") == "['Sommer']"


# ════════════════════════════════════════════════════════════════════════════
# The take-over drives, whatever the recovery opt-in says
# ════════════════════════════════════════════════════════════════════════════
class TestCatchUpOnActivation:
    """The two activation signals are NOT equally strong, and the gate must not treat them as
    one. The TRIGGER is unambiguous (only a real off -> on flank fires it). The CLAIM is a
    timestamp proxy that reads true on any restart, because the gating entity is recreated with
    everything else. So the trigger is exempt from is_restart_run and the claim is not."""

    def TPL(self) -> str:
        return _top_var("recovery_catch_up")

    def _run(self, *, mode, activated=False, restart=False, tid="t_open_1"):
        return _render_bool(self.TPL(), {}, recovery_mode=mode,
                            trigger=types.SimpleNamespace(id=tid),
                            instance_activated=activated, is_restart_run=restart)

    @pytest.mark.parametrize("mode", ["never", "outage", "always"])
    def test_an_activation_catches_up_in_every_mode(self, mode):
        """Including 'never' - the default, and the mode most users are in. An instance that
        took charge and left the cover where the previous one parked it did nothing."""
        assert self._run(mode=mode, activated=True) is True
        assert self._run(mode=mode, tid="t_instance_activated") is True

    @pytest.mark.parametrize("mode", ["never", "outage"])
    def test_the_switch_still_drives_right_after_a_save(self, mode):
        """The regression this class exists for. is_restart_run stays true for 300 s after a
        re-attach, and saving the automation IS a re-attach - so gating the trigger on it means:
        save the automation, flip the switch to try the hand-over, cover stays put. Which is the
        first thing anyone does with this feature. The explicit off -> on flank cannot be a
        restart (a restart returns the entity as unavailable -> on, which the trigger's
        from: [off, false] does not match), so it does not need the guard at all."""
        assert self._run(mode=mode, tid="t_instance_activated", restart=True) is True

    @pytest.mark.parametrize("mode", ["never", "outage"])
    def test_but_the_timestamp_claim_still_defers_to_a_restart(self, mode):
        """The other half: the claim reads true on every restart (the gating entity is recreated
        too, so its last_changed points at the boot). Exempting it from the opt-in as well would
        smuggle every restart past it - exactly what the opt-in promises not to do."""
        assert self._run(mode=mode, activated=True, restart=True) is False

    def test_without_an_activation_nothing_changed(self):
        assert self._run(mode="never") is False
        assert self._run(mode="outage") is True
        assert self._run(mode="always") is True
        assert self._run(mode="always", restart=True) is True


# ════════════════════════════════════════════════════════════════════════════
# A dropout of the switch itself - the sixth gate source is not like the five
# ════════════════════════════════════════════════════════════════════════════
class TestSwitchDropoutTakesOver:
    """A mid-runtime dropout of the gating entity (on -> unavailable -> on, no restart) leaves
    the return run with instance_activated true: the helper froze while the gate blocked every
    run, and the switch's last_changed moved to the return. That is indistinguishable, by
    design, from a hand-over whose off -> on flank fell into the outage - HA only keeps the
    final 'on'. The safe read is to take over: losing a real hand-over strands the cover, while
    the false positive drives to the position the cascade wants anyway. So unlike the five
    other gate sources, whose return run is hygiene-only with the catch-up off, this one
    DRIVES in every recovery mode. Only affects physically-backed gating entities (switch,
    binary_sensor); an input_boolean drops out around a restart only, where the proxy is held
    back (test_but_the_timestamp_claim_still_defers_to_a_restart)."""

    def test_the_return_run_claims_the_take_over(self):
        returned = NOW - datetime.timedelta(seconds=125)   # recovery settle already served
        assert _render_bool(
            _top_var("instance_activated"),
            {SWITCH: "on"}, {SWITCH: returned},
            instance_active=SWITCH,
            helper_ts_write=NOW_TS - 7200,                 # last write before the dropout
        ) is True

    @pytest.mark.parametrize("mode", ["never", "outage", "always"])
    def test_and_the_claimed_run_drives_in_every_mode(self, mode):
        assert _render_bool(
            _top_var("recovery_catch_up"), {},
            recovery_mode=mode,
            trigger=types.SimpleNamespace(id="t_recovery"),
            instance_activated=True, is_restart_run=False,
        ) is True


# ════════════════════════════════════════════════════════════════════════════
# The take-over must not come back blocked by its own old override
# ════════════════════════════════════════════════════════════════════════════
class TestOverrideIsVoidedOnTakeOver:
    def TPL(self) -> str:
        return _top_var("override_expired")

    def _run(self, *, activated, manual=True, reset_disabled=True):
        return _render_bool(
            self.TPL(), {},
            helper_state_manual=manual,
            instance_activated=activated,
            is_reset_disabled=reset_disabled,
            is_reset_timeout=False, is_reset_fixed_time=False, is_reset_position=False,
            in_reset_override_position=False,
            helper_ts_man=NOW_TS - 86400, reset_override_timeout=30,
            reset_override_time="12:00:00",
        )

    def test_an_override_from_the_previous_shift_is_discarded(self):
        """THE bug this feature would otherwise ship with. The instance went inactive with
        man == 1; while it was off it could not even see the cover being moved. Without this,
        recovery_allowed is false on the take-over, the cover is never positioned - and with a
        reset rule that cannot fire by itself (none configured, or reset-in-position while the
        cover is elsewhere) it stays blocked for good."""
        assert self._run(activated=True) is True

    def test_without_a_take_over_the_reset_rules_still_decide(self):
        assert self._run(activated=False) is False

    def test_nothing_to_void_when_there_is_no_override(self):
        assert self._run(activated=True, manual=False) is False


# ════════════════════════════════════════════════════════════════════════════
# The recovery gate is what performs the take-over
# ════════════════════════════════════════════════════════════════════════════
class TestRecoveryGateClaimsTheTakeOver:
    def GATE(self) -> str:
        return next(c for c in _branch_gate(RECOVERY) if "instance_activated" in str(c))

    def _run(self, tid, **over):
        args = dict(automation_resumed=False, instance_activated=False)
        args.update(over)
        return _render_bool(self.GATE(), {}, trigger=types.SimpleNamespace(id=tid), **args)

    def test_the_activation_trigger_enters_the_gate(self):
        assert self._run("t_instance_activated") is True

    def test_any_trigger_is_claimed_until_the_take_over_has_run(self):
        """The claim, not the prompt. If the availability gates swallowed the activation edge
        (the cover was still coming back, say), a state trigger has no second edge - so the
        next trigger of any kind has to become the take-over."""
        for tid in ["t_open_1", "t_close_5", "t_contact_opened_changed", "t_reset_timeout"]:
            assert self._run(tid, instance_activated=True) is True, tid

    @pytest.mark.parametrize("tid", ["t_manual_position", "t_manual_tilt"])
    def test_the_manual_triggers_are_exempt_from_the_claim(self, tid):
        """Same exemption, same reason as on a resumed run (#603): the manual handler never
        drives, it only records. Claiming it would drop the man: 1 the take-over must respect."""
        assert self._run(tid, instance_activated=True) is False

    def test_normal_runs_are_not_claimed(self):
        assert self._run("t_open_1") is False


# ════════════════════════════════════════════════════════════════════════════
# Bug Pattern T - the take-over is a new consumer of forecast and calendar data
# ════════════════════════════════════════════════════════════════════════════
class TestLoadGatesReachTheTakeOver:
    """The recurring shape: a trigger-id allow-list upstream of a value-based consumer breaks
    silently every time the set of triggers that can reach the consumer grows. The take-over
    run evaluates shading_start_warranted (recovered_pending) and the calendar boundaries
    (recovered_base) - and it can arrive under ANY trigger id via the claim."""

    def _gate(self, service: str):
        for step in BP["actions"]:
            if not isinstance(step, dict) or "if" not in step:
                continue
            body = str(step.get("then", ""))
            if service in body:
                return step["if"]
        raise AssertionError(f"no load gate for {service}")

    def _passes(self, service, tid, **over):
        args = dict(automation_resumed=False, instance_activated=False)
        args.update(over)
        conds = self._gate(service)
        target = next(c for c in conds if "instance_activated" in str(c))
        if isinstance(target, dict):        # the calendar gate is an `or:` block
            return any(_render_bool(c, {}, trigger=types.SimpleNamespace(id=tid), **args)
                       for c in target["or"])
        return _render_bool(target, {}, trigger=types.SimpleNamespace(id=tid), **args)

    @pytest.mark.parametrize("service", ["weather.get_forecasts", "calendar.get_events"])
    def test_the_activation_trigger_loads_them(self, service):
        assert self._passes(service, "t_instance_activated") is True

    @pytest.mark.parametrize("service", ["weather.get_forecasts", "calendar.get_events"])
    @pytest.mark.parametrize("tid", ["t_close_1", "t_resident_update", "t_contact_tilted_changed"])
    def test_a_claimed_run_loads_them_under_any_trigger_id(self, service, tid):
        assert self._passes(service, tid, instance_activated=True) is True

    @pytest.mark.parametrize("service", ["weather.get_forecasts", "calendar.get_events"])
    def test_an_unrelated_normal_run_still_does_not_load_them(self, service):
        assert self._passes(service, "t_resident_update") is False
