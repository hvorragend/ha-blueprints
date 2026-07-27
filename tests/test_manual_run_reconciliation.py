"""
Tests for the manual-run reconciliation (#639).

A run started by hand (`automation.trigger` / the UI "Run" action) carries no trigger id,
and every dispatch branch is keyed on one - so such a run used to fall through the whole
dispatch and end in the silent "No operational branch matched" stop, even when the cascade
plainly demanded a movement (shading warranted, cover stuck open). Since the user's intent
behind a manual trigger is "evaluate now and apply the correct state", the run is treated
as an explicit reconciliation request: the recovery gate claims it, re-derives the cascade
from live state and drives to the state it demands.

Two hazards make the claim more than a one-line change, and both are pinned here:

  * skip_condition: true (the UI "Run" action always uses it) bypasses the global
    conditions, so the claim must re-check the availability gates itself
    (`manual_run_ready`) - and the pre-dispatch init/migration writes must not clobber a
    helper that is merely `unavailable` (its stored value is intact, just not loaded).
  * The claimed run consumes shading_start_warranted and the parsed calendar boundaries,
    so both load gates must match a manual run (Bug Pattern T - a trigger-id allow-list
    upstream of a value-based consumer breaks silently when the set of reaching runs
    grows).

All templates are extracted verbatim from the blueprint.
"""
import types

import pytest

from test_restart_recovery import (
    BP,
    RECOVERY,
    _branch_gate,
    _render_bool,
    _top_level_branches,
    _top_var,
)

COVER = "cover.test"
HELPER = "input_text.cca_status"
OPENED = "binary_sensor.window_opened"
TILTED = "binary_sensor.window_tilted"
INVALID = ["", "unavailable", "unknown", "none", "None", "null", "query failed", []]

HELPER_JSON = (
    '{"bas":"opn","shd":0,"pnd":"non","win":"cls","frc":"non","res":0,"man":0,'
    '"ts":{"opn":0,"cls":0,"shd":0,"due":0,"arm":0,"man":0},"v":6,"t":1,"d":0}'
)

MANUAL = types.SimpleNamespace(platform=None)  # what automation.trigger provides: no id


def _ready(entity_states=None, **over):
    args = dict(
        critical_entities=[COVER],
        invalid_states=INVALID,
        cover_status_helper=HELPER,
        instance_active=[],
        is_ventilation_enabled=True,
        contact_window_opened=[],
        contact_window_tilted=[],
    )
    args.update(over)
    return _render_bool(_top_var("manual_run_ready"), entity_states or {}, **args)


class TestIsManualRun:
    def TPL(self) -> str:
        return _top_var("is_manual_run")

    def test_a_run_without_a_trigger_id_is_manual(self):
        """automation.trigger passes trigger = {'platform': None} - no id."""
        assert _render_bool(self.TPL(), {}, trigger=MANUAL) is True

    def test_a_run_without_a_trigger_at_all_is_manual(self):
        assert _render_bool(self.TPL(), {}) is True

    def test_every_configured_trigger_carries_an_id_so_no_real_run_reads_as_manual(self):
        """The detection is 'no trigger id' - it is only sound while EVERY trigger in the
        blueprint carries an id."""
        assert all("id" in t for t in BP["triggers"])
        assert _render_bool(self.TPL(), {}, trigger=types.SimpleNamespace(id="t_open_1")) is False


class TestRecoveryGateClaimsIt:
    def GATE(self) -> str:
        return next(c for c in _branch_gate(RECOVERY) if "automation_resumed" in str(c))

    def _run(self, **over):
        args = dict(trigger=MANUAL, automation_resumed=False,
                    is_manual_run=True, manual_run_ready=True)
        args.update(over)
        return _render_bool(self.GATE(), {}, **args)

    def test_a_manual_run_is_claimed(self):
        assert self._run() is True

    def test_but_only_while_the_sources_are_ready(self):
        """skip_condition: true bypasses the global availability gates, so the claim
        re-checks them itself. An unready manual run falls through to the dispatch,
        matches nothing and stops without a helper write - safe, and repeatable."""
        assert self._run(manual_run_ready=False) is False

    def test_the_manual_triggers_stay_exempt(self):
        """t_manual_position / t_manual_tilt carry ids - they are NOT manual runs, and
        their claim exemption (the handler records man: 1 instead of driving) stands."""
        assert self._run(trigger=types.SimpleNamespace(id="t_manual_position"),
                         is_manual_run=False, automation_resumed=True) is False

    def test_no_dispatch_branch_can_consume_a_manual_run(self):
        """The other half of the design: every dispatch branch is keyed on a trigger id,
        so the pre-dispatch claim is the ONLY handler a manual run can reach. A future
        branch without a trigger-id condition would silently swallow manual runs."""
        for branch in _top_level_branches():
            assert any("trigger.id" in str(c) for c in branch["conditions"]), \
                branch.get("alias", "<unnamed>")


class TestManualRunCatchesUp:
    """A manual trigger is an explicit request, like the activation flank - the recovery
    opt-in only guards against restarts moving the cover unasked, so it does not apply."""

    def _run(self, *, mode, restart=False):
        return _render_bool(_top_var("recovery_catch_up"), {}, recovery_mode=mode,
                            trigger=MANUAL, is_manual_run=True, is_restart_run=restart)

    @pytest.mark.parametrize("mode", ["never", "outage", "always"])
    def test_in_every_mode(self, mode):
        assert self._run(mode=mode) is True

    @pytest.mark.parametrize("mode", ["never", "outage"])
    def test_even_right_after_a_save(self, mode):
        """is_restart_run stays true for 300 s after a re-attach, and saving the automation
        is a re-attach - 'save, then hit Run to test' is the first thing anyone does."""
        assert self._run(mode=mode, restart=True) is True


class TestManualRunReady:
    """The availability mirror. Same tiers as the global conditions: critical entities,
    the Tier-1b helper rule (block only 'unavailable' - 'unknown' must pass so the init
    step can repair it), the multi-instance gate, and the per-contact Tier-2 rule."""

    GOOD = {COVER: "open", HELPER: HELPER_JSON}

    def test_ready_when_everything_is_usable(self):
        assert _ready(self.GOOD) is True

    def test_an_unavailable_cover_blocks(self):
        assert _ready({COVER: "unavailable", HELPER: HELPER_JSON}) is False

    def test_a_gone_cover_passes_to_the_mandatory_validation(self):
        """Half 0: a disabled/deleted entity never comes back, so blocking would make the
        automation silently dead. The mandatory entity validation (which runs BEFORE the
        recovery gate) names it and stops the run."""
        assert _ready({HELPER: HELPER_JSON}) is True

    def test_an_unavailable_helper_blocks(self):
        assert _ready({COVER: "open", HELPER: "unavailable"}) is False

    def test_an_unknown_helper_passes_so_the_init_step_can_repair_it(self):
        assert _ready({COVER: "open", HELPER: "unknown"}) is True

    def test_an_inactive_instance_never_reconciles(self):
        switch = "input_boolean.cca_summer"
        assert _ready({**self.GOOD, switch: "off"}, instance_active=switch,
                      instance_active_on_states=["on", "true"]) is False
        assert _ready({**self.GOOD, switch: "on"}, instance_active=switch,
                      instance_active_on_states=["on", "true"]) is True

    def test_a_stateless_opened_contact_blocks_only_while_the_window_was_open(self):
        helper_open = HELPER_JSON.replace('"win":"cls"', '"win":"opn"')
        assert _ready({COVER: "open", HELPER: helper_open, OPENED: "unavailable"},
                      contact_window_opened=OPENED) is False
        assert _ready({COVER: "open", HELPER: HELPER_JSON, OPENED: "unavailable"},
                      contact_window_opened=OPENED) is True

    def test_a_stateless_tilted_contact_blocks_while_the_window_was_not_closed(self):
        helper_tilted = HELPER_JSON.replace('"win":"cls"', '"win":"tlt"')
        assert _ready({COVER: "open", HELPER: helper_tilted, TILTED: "unavailable"},
                      contact_window_tilted=TILTED) is False
        assert _ready({COVER: "open", HELPER: HELPER_JSON, TILTED: "unavailable"},
                      contact_window_tilted=TILTED) is True

    def test_ventilation_disabled_means_the_contacts_do_not_exist(self):
        helper_open = HELPER_JSON.replace('"win":"cls"', '"win":"opn"')
        assert _ready({COVER: "open", HELPER: helper_open, OPENED: "unavailable"},
                      contact_window_opened=OPENED, is_ventilation_enabled=False) is True


class TestLoadGatesMatchManualRuns:
    """Bug Pattern T, sixth recurrence prevented: the claimed manual run evaluates
    shading_start_warranted (recovered_pending) and the parsed calendar boundaries
    (recovered_base), so both load gates must let it through."""

    def _gate(self, service: str) -> list:
        for step in BP["actions"]:
            if isinstance(step, dict) and "if" in step and service in str(step.get("then", "")):
                return step["if"]
        raise AssertionError(f"no load gate for {service}")

    @pytest.mark.parametrize("service", ["weather.get_forecasts", "calendar.get_events"])
    def test_the_trigger_id_guard_lets_a_manual_run_through(self, service):
        guard = next(c for c in self._gate(service)
                     if isinstance(c, str) and "trigger.id is defined" in c)
        assert _render_bool(guard, {}, trigger=MANUAL, is_manual_run=True) is True
        assert _render_bool(guard, {}, trigger=MANUAL, is_manual_run=False) is False

    def test_the_forecast_is_loaded_on_a_manual_run(self):
        gate = next(c for c in self._gate("weather.get_forecasts")
                    if isinstance(c, str) and "regex_match" in c)
        assert _render_bool(gate, {}, trigger=MANUAL, automation_resumed=False,
                            is_manual_run=True) is True

    def test_the_calendar_is_loaded_on_a_manual_run(self):
        or_cond = next(c for c in self._gate("calendar.get_events")
                       if isinstance(c, dict) and "or" in c)
        assert any(_render_bool(c, {}, trigger=MANUAL, automation_resumed=False,
                                is_manual_run=True)
                   for c in or_cond["or"])


class TestUnavailableHelperIsNeverClobbered:
    """Tier-1b says an 'unavailable' helper still holds its stored value - only the global
    conditions used to guarantee that nothing writes it, and a manual run with
    skip_condition: true bypasses them. The two pre-dispatch writes (init/repair and the
    v5->v6 migration persist) must therefore carry the guard themselves."""

    def _init_step(self) -> dict:
        for step in BP["actions"]:
            if (isinstance(step, dict) and "if" in step
                    and any(isinstance(a, dict) and a.get("action") == "input_text.set_value"
                            for a in step.get("then", []))
                    and "invalid_states" in str(step["if"])):
                return step
        raise AssertionError("init step not found")

    def _migration_step(self) -> dict:
        for step in BP["actions"]:
            if isinstance(step, dict) and "has_unknown_ts" in str(step.get("if", "")):
                return step
        raise AssertionError("migration step not found")

    @pytest.mark.parametrize("step_getter", ["_init_step", "_migration_step"])
    def test_both_write_steps_carry_the_guard(self, step_getter):
        step = getattr(self, step_getter)()
        guard = next((c for c in step["if"]
                      if isinstance(c, str) and "!= 'unavailable'" in c), None)
        assert guard is not None, "missing the unavailable-helper guard"
        assert _render_bool(guard, {HELPER: "unavailable"}, cover_status_helper=HELPER) is False
        assert _render_bool(guard, {HELPER: "unknown"}, cover_status_helper=HELPER) is True
