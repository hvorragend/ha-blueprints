"""
Paired live-versus-recovery scenario tests: the semantic contract.

CONTRACT (references/recovery-parity.md): recovery is a RECONCILIATION from the
currently observable state, not a historical replay. Given the same current inputs
and persisted helper state, the recovery must reach the same base-transition
decision, the same drive/no-drive decision and the same helper mutations the live
opening/closing path would reach at that moment. Deviations are intentional,
documented recovery semantics and are asserted here AS deviations.

Mechanically both paths consume the shared `base_gates` / `closing_position_hold`
projections, so equality is structural for the gates themselves. These tests guard
the COMPOSITION on top of the shared projections (flip context, night clause,
override_expired, drive holds): each scenario renders the real templates of both
paths end-to-end and compares the outcomes.
"""
import types

import pytest

from test_restart_recovery import (
    BP, NOW, NOW_TS, RECOVERY,
    _action_var, _branch, _branch_body, _branch_var,
    _render, _render_bool, _state_targets,
)


# ════════════════════════════════════════════════════════════════════════════
# Scenario harness
# ════════════════════════════════════════════════════════════════════════════

POSITIONS = dict(open_position=100, close_position=0, ventilate_position=50,
                 open_tilt_position=100, close_tilt_position=0,
                 ventilate_tilt_position=60, shading_tilt_position=40)

BASE_SCENARIO = dict(
    # environment (the real sensors; environment_allows_* is rendered, not stubbed)
    entities={"sensor.bri": "6780"},
    default_brightness_sensor="sensor.bri",
    default_sun_sensor=[],
    is_brightness_enabled=True,
    is_sun_elevation_enabled=False,
    use_and_operator=False,
    brightness_down=75,
    brightness_up=100,
    brightness_hysteresis=0,
    current_sun_elevation=10.0,
    sun_elevation_down_current=-1.4,
    sun_elevation_up_current=0.0,
    # schedule phases: evening, after time_down_early, before time_down_late
    is_time_control_disabled=False,
    is_time_field_enabled=True,
    is_calendar_enabled=False,
    calendar_open_start=None,
    is_up_enabled=True,
    is_down_enabled=True,
    is_opening_phase=False,
    is_daytime_phase=False,
    is_closing_phase=True,
    is_evening_phase=True,
    is_time_up_late=False,
    is_time_down_late=False,
    time_up_early_today="07:00:00",
    time_down_early_today="17:00:00",
    now_ts=NOW_TS,
    # helper state
    helper_state_base="opn",
    helper_state_manual=False,
    helper_state_is_shaded=False,
    helper_state_shade=False,
    override_expired=False,
    helper_ts_open=0,
    helper_ts_close=0,
    helper_ts_man=0,
    # override / prevent configuration
    override_flags={"opening": False, "closing": False},
    prevent_flags={"opening_multiple_times": False,
                   "closing_multiple_times": False,
                   "lowering_when_closing_if_shaded": False,
                   "higher_position_closing": False},
    # window / resident / force
    window="cls",                      # cls | tlt | opn (live contact state)
    lockout_tilted_when_closing=False,
    state_resident=False,
    resident_config=[],
    is_ventilation_enabled=True,
    is_opening_scheduled=True,
    shading_over_ventilation=False,
    live_force="non",
    is_paused=False,
    force_allows_open=True,
    force_allows_close=True,
    force_allows_shade=True,
    force_allows_ventilate=True,
    recovery_catch_up=True,
    stale_day=False,
    # cover
    current_position=100,
    position_tolerance=2,
    in_shading_position=False,
    effective_shading_position=20,
    effective_lockout_position=100,
    **POSITIONS,
)


def scenario(**over) -> dict:
    s = dict(BASE_SCENARIO)
    s.update(over)
    return s


def _flip_gate() -> dict:
    return next(step for step in _branch_body(RECOVERY)
                if "additional condition" in str(step.get("alias", "")))


def _flip_branch(direction: str) -> dict:
    return next(b for b in _flip_gate()["choose"] if direction in b["alias"])


def _environment(s: dict, which: str) -> bool:
    return _render_bool(_action_var(f"environment_allows_{which}"),
                        s["entities"], **s)


def _base_gates(s: dict) -> dict:
    """Render the real shared projections into plain booleans."""
    env = {"opening": _environment(s, "opening"), "closing": _environment(s, "closing")}
    override_blocks = {
        "opening": s["helper_state_manual"] and s["override_flags"]["opening"],
        "closing": s["helper_state_manual"] and s["override_flags"]["closing"],
    }
    gates = {}
    for direction in ("opening", "closing"):
        tpl = _action_var("base_gates")[direction]
        gates[direction] = {
            key: _render_bool(tpl[key], s["entities"], **s,
                              override_blocks=override_blocks,
                              environment_allows_opening=env["opening"],
                              environment_allows_closing=env["closing"])
            for key in ("override_ok", "once_ok", "schedule_ok")
        }
    return gates


def _closing_position_hold(s: dict) -> bool:
    comparisons = {
        "shading_above_close": s["effective_shading_position"] > s["close_position"],
        "current_below_close": s["current_position"] < s["close_position"],
    }
    return _render_bool(_action_var("closing_position_hold"), {}, **s,
                        position_comparisons=comparisons)


# --- the LIVE path -----------------------------------------------------------

def _live_enters(s: dict, branch_alias: str, gates: dict) -> bool:
    """AND the real entry conditions of the live branch (trigger identity assumed to
    match, the !input additional condition assumed true - see recovery-parity.md)."""
    branch = _branch(branch_alias)
    verdict = True
    for cond in branch["conditions"]:
        if not isinstance(cond, str) or "trigger" in cond:
            continue
        verdict = verdict and _render_bool(cond, s["entities"], **s, base_gates=gates)
    return verdict


def _live_closing_outcome(s: dict, gates: dict) -> dict:
    """The closing branch's decision: transition (bas write) and movement."""
    if not _live_enters(s, "Check for closing", gates):
        return {"transition": False, "moves": False, "target": None}
    lockout = s["window"] == "opn" or (
        s["lockout_tilted_when_closing"] and s["window"] == "tlt")
    if s["is_ventilation_enabled"] and lockout:
        return {"transition": True, "moves": False, "target": None}          # C-A
    if (s["is_ventilation_enabled"] and s["window"] == "tlt"
            and not s["lockout_tilted_when_closing"]):
        return {"transition": True, "moves": True,
                "target": s["ventilate_position"]}                            # C-B
    already_closed = abs(s["current_position"] - s["close_position"]) <= s["position_tolerance"]
    if already_closed:
        return {"transition": True, "moves": False, "target": None}          # C-C
    if _closing_position_hold(s):
        return {"transition": True, "moves": False, "target": None}          # C-D
    moves = not s["is_paused"] and s["force_allows_close"]
    return {"transition": True, "moves": moves, "target": s["close_position"]}  # C-E


# --- the RECOVERY path -------------------------------------------------------

def _recovered_base(s: dict) -> str:
    return _render(_branch_var(RECOVERY, "recovered_base"), s["entities"], **s).strip()


def _flip_taken(s: dict, direction: str, gates: dict) -> bool:
    branch = _flip_branch(direction)
    verdict = True
    for cond in branch["conditions"]:
        if not isinstance(cond, str):
            continue                                   # !input condition assumed true
        verdict = verdict and _render_bool(
            cond, s["entities"], **s, base_gates=gates,
            recovered_base=_recovered_base(s))
    return verdict


def _recovery_outcome(s: dict, gates: dict) -> dict:
    """The recovery's decision on the same inputs: new_base, movement, target."""
    closing_flip = _flip_taken(s, "closing", gates)
    opening_flip = (not closing_flip) and _flip_taken(s, "opening", gates)
    new_base = ("cls" if closing_flip else
                "opn" if opening_flip else s["helper_state_base"])
    recovered_shade = False if closing_flip else (
        s["helper_state_shade"] and not s["stale_day"])
    recovered_window = _render(
        _branch_var(RECOVERY, "recovered_window"),
        {**s["entities"],
         "binary_sensor.opened": "on" if s["window"] == "opn" else "off",
         "binary_sensor.tilted": "on" if s["window"] == "tlt" else "off"},
        **s,
        contact_window_opened="binary_sensor.opened",
        contact_window_tilted="binary_sensor.tilted",
        helper_state_window=s["window"]).strip()
    present = s["state_resident"]
    resident_flags = {
        "closing_trigger": "resident_closing_enabled" in s["resident_config"],
        "allow_open": ("resident_allow_opening" in s["resident_config"]) or not present,
        "allow_shade": ("resident_allow_shading" in s["resident_config"]) or not present,
        "allow_ventilate": ("resident_allow_ventilation" in s["resident_config"]) or not present,
    }
    recovered_state = _render(
        _branch_var(RECOVERY, "recovered_state"), s["entities"], **s,
        new_base=new_base, recovered_shade=recovered_shade,
        recovered_window=recovered_window, resident_flags=resident_flags).strip()
    targets = _state_targets(**{k: s[k] for k in POSITIONS},
                             effective_shading_position=s["effective_shading_position"],
                             effective_lockout_position=s["effective_lockout_position"])
    target = int(targets[recovered_state]["target"])
    caught_up_closing = new_base == "cls" and s["helper_state_base"] != "cls"
    hold = _render_bool(
        _branch_var(RECOVERY, "caught_up_closing_hold"), {}, **s,
        caught_up_closing=caught_up_closing, recovered_state=recovered_state,
        closing_position_hold=_closing_position_hold(s))
    allowed = _render_bool(
        _branch_var(RECOVERY, "recovery_allowed"), {}, **s,
        defer_to_shading=False, recovered_state=recovered_state)
    will_drive = (s["recovery_catch_up"] and not s["is_paused"]
                  and allowed and not hold)
    in_position = abs(target - s["current_position"]) <= s["position_tolerance"]
    return {"transition": new_base != s["helper_state_base"],
            "new_base": new_base,
            "state": recovered_state,
            "moves": will_drive and not in_position,
            "target": target if will_drive and not in_position else None}


def _paired_closing(s: dict) -> tuple[dict, dict]:
    gates = _base_gates(s)
    return _live_closing_outcome(s, gates), _recovery_outcome(s, gates)


# ════════════════════════════════════════════════════════════════════════════
# The exact #656 regression, and its neighbours
# ════════════════════════════════════════════════════════════════════════════
class TestIssue656Regression:
    """Outage recovery at ~18:15, brightness far above the closing threshold: the
    live 'Check for closing' would not run, so the catch-up must not close either -
    base stays open, nothing moves."""

    @pytest.mark.parametrize("brightness", ["6780", "7032"])
    def test_both_paths_reject_the_bright_evening_closing(self, brightness):
        s = scenario(entities={"sensor.bri": brightness})
        live, recovery = _paired_closing(s)
        assert live["transition"] is False
        assert recovery["transition"] is False
        assert recovery["new_base"] == "opn"
        assert live["moves"] is False
        assert recovery["moves"] is False

    def test_outage_mode_is_a_catch_up_for_a_mid_day_dropout(self):
        """recovery_catch_up itself: 'outage' mode with no restart in sight."""
        tpl = BP["variables"]["recovery_catch_up"]
        assert _render_bool(tpl, {}, recovery_mode="outage", is_restart_run=False,
                            instance_activated=False,
                            trigger=types.SimpleNamespace(id="t_recovery")) is True

    def test_both_paths_accept_once_it_is_dark(self):
        s = scenario(entities={"sensor.bri": "40"})
        live, recovery = _paired_closing(s)
        assert live["transition"] is True and recovery["transition"] is True
        assert live["moves"] is True and recovery["moves"] is True
        assert live["target"] == recovery["target"] == 0

    def test_both_paths_accept_at_the_ultimate_closing_time(self):
        s = scenario(is_time_down_late=True)     # still bright - no environment gate
        live, recovery = _paired_closing(s)
        assert live["transition"] is True and recovery["transition"] is True
        assert live["moves"] is True and recovery["moves"] is True


# ════════════════════════════════════════════════════════════════════════════
# Environment modes: hysteresis, AND/OR, sun elevation
# ════════════════════════════════════════════════════════════════════════════
class TestEnvironmentParity:
    @pytest.mark.parametrize("brightness,expected", [
        ("70", False),    # above threshold - hysteresis
        ("65", False),    # exactly at the boundary: < is strict
        ("60", True),     # below
    ])
    def test_hysteresis_boundary(self, brightness, expected):
        s = scenario(entities={"sensor.bri": brightness}, brightness_hysteresis=10)
        live, recovery = _paired_closing(s)
        assert live["transition"] is expected
        assert recovery["transition"] is expected

    @pytest.mark.parametrize("and_operator,expected", [
        (False, True),    # OR: the sun already below its threshold suffices
        (True, False),    # AND: brightness still too high blocks
    ])
    def test_and_or_operator(self, and_operator, expected):
        s = scenario(default_sun_sensor="sun.sun", is_sun_elevation_enabled=True,
                     current_sun_elevation=-3.0, use_and_operator=and_operator)
        live, recovery = _paired_closing(s)
        assert live["transition"] is expected
        assert recovery["transition"] is expected


# ════════════════════════════════════════════════════════════════════════════
# Override and once-a-day parity
# ════════════════════════════════════════════════════════════════════════════
class TestOverrideAndOnceParity:
    def test_an_active_closing_override_blocks_both(self):
        s = scenario(entities={"sensor.bri": "40"}, helper_state_manual=True,
                     override_flags={"opening": False, "closing": True})
        live, recovery = _paired_closing(s)
        assert live["transition"] is False
        assert recovery["transition"] is False
        assert recovery["moves"] is False

    def test_an_expired_override_is_an_intentional_recovery_semantic(self):
        """DOCUMENTED DEVIATION (recovery-parity.md): post-repair reconciliation.
        In the live timeline the reset would have fired at expiry and cleared man;
        whether the swallowed closing fell before or after that moment is unknowable,
        so the recovery repairs first (man -> 0) and reconciles against the repaired
        state: the flip and the drive proceed."""
        s = scenario(entities={"sensor.bri": "40"}, helper_state_manual=True,
                     override_flags={"opening": False, "closing": True},
                     override_expired=True)
        _, recovery = _paired_closing(s)
        assert recovery["transition"] is True
        assert recovery["moves"] is True

    def test_a_second_closing_of_the_day_blocks_both(self):
        closed_at = NOW.replace(hour=18, minute=0).timestamp()
        s = scenario(entities={"sensor.bri": "40"},
                     prevent_flags=dict(BASE_SCENARIO["prevent_flags"],
                                        closing_multiple_times=True),
                     helper_ts_close=closed_at, helper_ts_man=closed_at + 600)
        live, recovery = _paired_closing(s)
        assert live["transition"] is False
        assert recovery["transition"] is False


# ════════════════════════════════════════════════════════════════════════════
# Window states: lockout, tilted ventilation, tilted lockout option
# ════════════════════════════════════════════════════════════════════════════
class TestWindowParity:
    def test_tilted_window_goes_to_ventilation_in_both_paths(self):
        s = scenario(entities={"sensor.bri": "40"}, window="tlt")
        live, recovery = _paired_closing(s)
        assert live["transition"] is True and recovery["transition"] is True
        assert recovery["state"] == "vnt"
        assert live["moves"] is True and recovery["moves"] is True
        assert live["target"] == recovery["target"] == 50

    def test_tilted_lockout_option_holds_both_paths(self):
        """lockout_now.closing covers the tilted window when the option is set: the
        live branch records the closing without moving - so does the catch-up."""
        s = scenario(entities={"sensor.bri": "40"}, window="tlt",
                     lockout_tilted_when_closing=True)
        live, recovery = _paired_closing(s)
        assert live["transition"] is True and recovery["transition"] is True
        assert live["moves"] is False
        assert recovery["moves"] is False

    def test_open_window_lockout_is_an_intentional_recovery_semantic(self):
        """DOCUMENTED DEVIATION (recovery-parity.md): the live closing branch skips
        the movement under lockout, while the recovery reconciles to the lockout
        position - the target the (equally swallowed) contact-opened handler would
        have established. Both record the closing."""
        s = scenario(entities={"sensor.bri": "40"}, window="opn",
                     current_position=40)
        live, recovery = _paired_closing(s)
        assert live["transition"] is True and recovery["transition"] is True
        assert live["moves"] is False
        assert recovery["state"] == "lock"
        assert recovery["moves"] is True
        assert recovery["target"] == 100


# ════════════════════════════════════════════════════════════════════════════
# Shading interplay
# ════════════════════════════════════════════════════════════════════════════
class TestShadingParity:
    def test_a_caught_up_closing_ends_the_shading_in_both_paths(self):
        """Live closing clears shd and closes; the catch-up must not leave the
        cascade in SHADING and park the cover at the shading position overnight."""
        s = scenario(entities={"sensor.bri": "40"}, helper_state_shade=True,
                     helper_state_is_shaded=True, current_position=20,
                     in_shading_position=True)
        live, recovery = _paired_closing(s)
        assert live["transition"] is True and recovery["transition"] is True
        assert recovery["state"] == "cls"
        assert live["moves"] is True and recovery["moves"] is True
        assert live["target"] == recovery["target"] == 0

    def test_prevent_lowering_when_shaded_holds_both_paths(self):
        s = scenario(entities={"sensor.bri": "40"}, helper_state_shade=True,
                     helper_state_is_shaded=True, current_position=20,
                     in_shading_position=True, close_position=30,
                     effective_shading_position=20,
                     prevent_flags=dict(BASE_SCENARIO["prevent_flags"],
                                        lowering_when_closing_if_shaded=True))
        live, recovery = _paired_closing(s)
        assert live["transition"] is True and recovery["transition"] is True
        assert live["moves"] is False
        assert recovery["moves"] is False

    def test_prevent_higher_position_closing_holds_both_paths(self):
        s = scenario(entities={"sensor.bri": "40"}, current_position=10,
                     close_position=30,
                     prevent_flags=dict(BASE_SCENARIO["prevent_flags"],
                                        higher_position_closing=True))
        live, recovery = _paired_closing(s)
        assert live["transition"] is True and recovery["transition"] is True
        assert live["moves"] is False
        assert recovery["moves"] is False


# ════════════════════════════════════════════════════════════════════════════
# Opening parity
# ════════════════════════════════════════════════════════════════════════════
class TestOpeningParity:
    def _opening_scenario(self, **over):
        base = scenario(
            entities={"sensor.bri": "40"},        # still dark
            is_opening_phase=True, is_daytime_phase=True,
            is_closing_phase=False, is_evening_phase=False,
            helper_state_base="cls", current_position=0,
        )
        base.update(over)
        return base

    def _paired(self, s):
        gates = _base_gates(s)
        live = _live_enters(s, "Check for opening", gates)
        recovery = _recovery_outcome(s, gates)
        return live, recovery

    def test_a_dark_morning_blocks_both(self):
        live, recovery = self._paired(self._opening_scenario())
        assert live is False
        assert recovery["transition"] is False

    def test_a_bright_morning_opens_both(self):
        live, recovery = self._paired(
            self._opening_scenario(entities={"sensor.bri": "5000"}))
        assert live is True
        assert recovery["transition"] is True and recovery["new_base"] == "opn"
        assert recovery["moves"] is True and recovery["target"] == 100

    def test_the_ultimate_opening_time_opens_both(self):
        live, recovery = self._paired(self._opening_scenario(is_time_up_late=True))
        assert live is True
        assert recovery["transition"] is True

    def test_a_second_opening_of_the_day_blocks_both(self):
        live, recovery = self._paired(self._opening_scenario(
            entities={"sensor.bri": "5000"},
            prevent_flags=dict(BASE_SCENARIO["prevent_flags"],
                               opening_multiple_times=True),
            helper_ts_open=NOW_TS - 3600, helper_ts_man=NOW_TS - 600))
        assert live is False
        assert recovery["transition"] is False


# ════════════════════════════════════════════════════════════════════════════
# Structural: one source of truth, protected against drift
# ════════════════════════════════════════════════════════════════════════════
class TestSharedProjectionStructure:
    """Live and recovery must reference the SAME named projections. These tests make
    re-inlining a predicate on either side a test failure, not a silent fork."""

    PROJECTIONS = {"override_ok", "once_ok", "schedule_ok"}

    def _strings(self, conditions) -> list:
        return [c for c in conditions if isinstance(c, str)]

    def test_live_branches_consume_the_projections(self):
        for direction, alias in (("opening", "Check for opening"),
                                 ("closing", "Check for closing")):
            conds = " ".join(self._strings(_branch(alias)["conditions"]))
            for key in self.PROJECTIONS:
                assert f"base_gates.{direction}.{key}" in conds, (direction, key)
            for forbidden in ("override_blocks.", "prevent_flags.",
                              "environment_allows", "is_time_up_late",
                              "is_time_down_late"):
                assert forbidden not in conds, (direction, forbidden)

    def test_recovery_flips_consume_the_same_projections(self):
        for direction in ("opening", "closing"):
            conds = " ".join(self._strings(_flip_branch(direction)["conditions"]))
            for key in self.PROJECTIONS:
                assert f"base_gates.{direction}.{key}" in conds, (direction, key)
            for forbidden in ("override_blocks.", "prevent_flags.",
                              "environment_allows"):
                assert forbidden not in conds, (direction, forbidden)

    def test_the_projections_are_defined_exactly_once(self):
        gates = _action_var("base_gates")
        for direction in ("opening", "closing"):
            assert set(gates[direction]) == self.PROJECTIONS

    @pytest.mark.parametrize("direction,input_name", [
        ("opening", "auto_up_condition"), ("closing", "auto_down_condition")])
    def test_the_input_condition_is_the_same_yaml_node(self, direction, input_name):
        """The !input conditions cannot move into a Jinja projection, so they are
        anchored: the live branch aliases the recovery flip's node. PyYAML resolves
        an alias to the identical object - `is`, not just equality."""
        alias = "Check for opening" if direction == "opening" else "Check for closing"
        live_node = next(c for c in _branch(alias)["conditions"]
                         if isinstance(c, dict) and "condition" in c)
        recovery_node = next(c for c in _flip_branch(direction)["conditions"]
                             if isinstance(c, dict) and "condition" in c)
        assert live_node["condition"] == input_name
        assert live_node is recovery_node

    def test_the_closing_position_hold_is_shared(self):
        """Both the live status-only branch and the recovery hold reference the
        one closing_position_hold projection."""
        closing = _branch("Check for closing")
        nested = next(s["choose"] for s in closing["sequence"]
                      if isinstance(s, dict) and "choose" in s)
        live = next(b for b in nested if "Only status change" in str(b.get("alias", "")))
        assert live["conditions"] == ["{{ closing_position_hold }}"]
        assert "closing_position_hold" in _branch_var(RECOVERY, "caught_up_closing_hold")
