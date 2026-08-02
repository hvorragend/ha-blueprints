"""
Paired live-versus-recovery tests: the semantic contract, executed from the YAML.

CONTRACT (references/recovery-parity.md): recovery is a RECONCILIATION from the
currently observable state. Given the same current inputs and persisted helper
state, it must reach the same base-transition decision, the same drive/no-drive
decision and the same helper mutations the live opening/closing path reaches at
that moment. Recovery-only hygiene (win/res/frc re-read, stale-state cleanup) is
declared explicitly in the comparison; everything else must match.

These are NOT hand-written oracles: a small evaluator walks the REAL parsed YAML
of both paths - it evaluates the actual branch conditions in order, injects a
verdict for every `!input` condition it meets (an un-stubbed one raises), renders
the real `variables:` chains (will_drive, drive_plan, update_values) and stops at
the shared apply-transition anchor. The Python below only assembles context and
normalizes outcomes; the decisions come from the blueprint.
"""
import ast
import types

import pytest

from test_restart_recovery import (
    BP, NOW, NOW_TS, RECOVERY,
    _action_var, _branch, _branch_body, _render, _top_var,
)


# ════════════════════════════════════════════════════════════════════════════
# The YAML evaluator
# ════════════════════════════════════════════════════════════════════════════

def _apply_transition_node():
    """The shared apply-transition anchor, identified by object identity: the step
    right after the variables block in the closing branch's default leaf."""
    closing = _branch("Check for closing")
    dispatch = next(s for s in closing["sequence"] if isinstance(s, dict) and "choose" in s)
    default_leaf = dispatch["default"]
    return next(s for s in default_leaf
                if isinstance(s, dict) and "variables" not in s and "stop" not in s)


APPLY_TRANSITION = _apply_transition_node()


def _cast(rendered: str):
    text = rendered.strip()
    if text == "True":
        return True
    if text == "False":
        return False
    if text == "None":
        return None
    if text.startswith(("{", "[")):
        try:
            return ast.literal_eval(text)
        except (SyntaxError, ValueError):
            pass
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


class Runner:
    """Interprets the subset of HA script YAML the open/close/recovery paths use:
    `variables:`, `choose:`, `if:`/`then:`/`else:`, `stop:`. `!input` conditions
    resolve through the injected verdicts."""

    def __init__(self, ctx: dict, entities: dict, verdicts: dict):
        self.ctx = dict(ctx)
        self.entities = entities
        self.verdicts = verdicts

    def render(self, template):
        if isinstance(template, str) and ("{{" in template or "{%" in template):
            return _cast(_render(template, self.entities, **self.ctx))
        if isinstance(template, dict):
            return {k: self.render(v) for k, v in template.items()}
        return template

    def condition(self, cond) -> bool:
        if isinstance(cond, str):
            return self.render(cond) is True
        if "or" in cond:
            return any(self.condition(c) for c in cond["or"])
        if "and" in cond:
            return all(self.condition(c) for c in cond["and"])
        if "not" in cond:
            return not any(self.condition(c) for c in cond["not"])
        if "condition" in cond and isinstance(cond["condition"], str):
            return self.verdicts[cond["condition"]]     # un-stubbed !input -> KeyError
        raise AssertionError(f"unsupported condition shape: {cond!r}")

    def conditions(self, conds) -> bool:
        if conds is None:
            return True
        if not isinstance(conds, list):
            conds = [conds]
        return all(self.condition(c) for c in conds)

    def run(self, steps) -> str | None:
        if not isinstance(steps, list):
            return None
        for step in steps:
            if not isinstance(step, dict):
                continue
            if step is APPLY_TRANSITION:
                continue                                 # outcome is already in ctx
            if "variables" in step:
                for name, tpl in step["variables"].items():
                    self.ctx[name] = self.render(tpl)
            elif "choose" in step:
                for branch in step["choose"] or []:
                    if self.conditions(branch.get("conditions")):
                        if self.run(branch.get("sequence")) == "stop":
                            return "stop"
                        break
                else:
                    if self.run(step.get("default")) == "stop":
                        return "stop"
            elif "if" in step:
                which = "then" if self.conditions(step["if"]) else "else"
                if self.run(step.get(which)) == "stop":
                    return "stop"
            elif "stop" in step:
                return "stop"
        return None


# ════════════════════════════════════════════════════════════════════════════
# Scenario context: primitives in, real projections rendered from the blueprint
# ════════════════════════════════════════════════════════════════════════════

POSITIONS = dict(open_position=100, close_position=0, ventilate_position=50,
                 open_tilt_position=100, close_tilt_position=0,
                 ventilate_tilt_position=60, shading_tilt_position=40,
                 shading_position=20)

SCENARIO_DEFAULTS = dict(
    # environment sensors
    brightness="6780",
    default_sun_sensor=[],
    is_brightness_enabled=True,
    is_sun_elevation_enabled=False,
    use_and_operator=False,
    brightness_down=75, brightness_up=100, brightness_hysteresis=0,
    current_sun_elevation=10.0,
    sun_elevation_down_current=-1.4, sun_elevation_up_current=0.0,
    # schedule phases (default: evening, between early and ultimate-late closing)
    is_time_control_disabled=False, is_time_field_enabled=True,
    is_calendar_enabled=False, calendar_open_start=None,
    is_up_enabled=True, is_down_enabled=True,
    is_opening_phase=False, is_daytime_phase=False,
    is_closing_phase=True, is_evening_phase=True,
    is_time_up_late=False, is_time_down_late=False,
    time_up_early_today="07:00:00", time_down_early_today="17:00:00",
    is_shading_allowed_window=True,
    # window / options
    window="cls",                       # cls | tlt | opn
    is_ventilation_enabled=True,
    lockout_tilted_when_closing=False,
    lockout_tilted_when_shading_starts=False,
    lockout_tilted_when_shading_ends=False,
    # helper state
    helper=dict(bas="opn", shd=0, pnd="non", win="cls", frc="non", res=0, man=0),
    helper_ts_open=0, helper_ts_close=0, helper_ts_man=0,
    helper_ts_pending_due=0, helper_ts_pending_arm=0,
    stale_day=False, override_expired=False,
    # configuration
    override_flags={"opening": False, "closing": False,
                    "ventilation": False, "shading": False},
    prevent_flags={"opening_multiple_times": False, "closing_multiple_times": False,
                   "lowering_when_closing_if_shaded": False,
                   "higher_position_closing": False,
                   "shading_multiple_times": False},
    resident_config=[],
    state_resident=False,
    is_opening_scheduled=True,
    shading_over_ventilation=False,
    is_shading_enabled=True,
    ventilation_flags={"start_no_delay": False, "delay_enabled": False,
                       "if_lower_enabled": False, "after_shading_end": False,
                       "keep_open_on_full_to_tilt": False},
    shading_start_warranted=False, shading_end_conditions_met=False,
    shading_waitingtime_start=300, shading_waitingtime_end=600,
    shading_start_max_duration=3600,
    # force / pause / recovery flags
    live_force="non", is_paused=False,
    force_allows_open=True, force_allows_close=True,
    force_allows_shade=True, force_allows_ventilate=True,
    recovery_catch_up=True,
    instance_activated=False, automation_resumed=False,
    is_restart_run=False, midnight_reset_missed=False,
    # cover
    current_position=100, current_tilt_position=100,
    position_tolerance=2, tilt_position_tolerance=5,
    is_awning=False, is_cover_tilt_enabled_and_possible=False,
    is_cover_tilt_reposition_enabled=False,
    effective_shading_position=20, effective_lockout_position=100,
    drive_delay_fix=0, drive_delay_random=0,
    drive_time=90,
    **POSITIONS,
)


def _context(s: dict, trigger_id: str) -> tuple[dict, dict]:
    """Primitives plus every real projection both paths consume, rendered from the
    blueprint with the scenario's entity states."""
    entities = {
        "sensor.bri": s["brightness"],
        "sun.sun": "above_horizon",
        "binary_sensor.opened": "on" if s["window"] == "opn" else "off",
        "binary_sensor.tilted": "on" if s["window"] == "tlt" else "off",
    }
    helper = dict(s["helper"])
    helper["ts"] = {"opn": s["helper_ts_open"], "cls": s["helper_ts_close"],
                    "shd": 0, "due": s["helper_ts_pending_due"],
                    "arm": s["helper_ts_pending_arm"], "man": s["helper_ts_man"]}
    ctx = {k: v for k, v in s.items()
           if k not in ("brightness", "window", "helper")}
    ctx.update(
        trigger=types.SimpleNamespace(id=trigger_id),
        default_brightness_sensor="sensor.bri",
        contact_window_opened="binary_sensor.opened",
        contact_window_tilted="binary_sensor.tilted",
        helper_json=helper,
        helper_state_base=helper["bas"],
        helper_state_window=helper["win"],
        helper_state_force=helper["frc"],
        helper_state_manual=helper["man"] == 1,
        helper_state_shade=helper["shd"] == 1,
        helper_state_is_shaded=helper["shd"] == 1 and helper["pnd"] != "beg",
        helper_state_pending=helper["pnd"],
        helper_state_pending_start=helper["pnd"] == "beg",
        helper_state_pending_end=helper["pnd"] == "end",
        now_ts=NOW_TS,
        override_blocks={k: helper["man"] == 1 and v
                         for k, v in s["override_flags"].items()},
        shading_once_guard_ok=True,
        drive_delay_standard=0,
        state_labels=_action_var("state_labels"),
    )
    ctx["manual_allows_event"] = Runner(ctx, entities, {}).render(
        _top_var("manual_allows_event")
    )
    for name in ("window_opened_now", "window_tilted_now", "window_any_now",
                 "window_opened_clear"):
        ctx[name] = Runner(ctx, entities, {}).render(_action_var(name))
    for name in ("in_open_position", "in_close_position", "in_shading_position",
                 "in_ventilate_position", "in_lockout_position",
                 "position_comparisons", "resident_flags", "effective_state"):
        ctx[name] = Runner(ctx, entities, {}).render(_top_var(name))
    for name in ("lockout_now", "environment_allows_opening",
                 "environment_allows_closing", "base_gates",
                 "closing_position_hold", "state_targets", "state_gates"):
        ctx[name] = Runner(ctx, entities, {}).render(_action_var(name))
    return ctx, entities


DEFAULT_VERDICTS = {"auto_up_condition": True, "auto_down_condition": True,
                    "auto_ventilate_condition": True}


def scenario(**over) -> dict:
    s = dict(SCENARIO_DEFAULTS)
    helper = dict(SCENARIO_DEFAULTS["helper"])
    helper.update(over.pop("helper", {}))
    s.update(over)
    s["helper"] = helper
    return s


# ════════════════════════════════════════════════════════════════════════════
# Outcome extraction and comparison
# ════════════════════════════════════════════════════════════════════════════

def _resolved(ctx: dict, helper: dict, drove: bool = False) -> dict:
    """The persisted decision fields after the run: update_values merged over the
    helper, timestamps normalized ('now' stays 'now')."""
    uv = ctx.get("update_values") or {}
    ts = uv.get("ts") or {}
    helper_ts = helper["ts"]
    return {
        "bas": uv.get("bas", helper["bas"]),
        "shd": int(uv.get("shd", helper["shd"])),
        "pnd": uv.get("pnd", helper["pnd"]),
        "man": int(uv.get("man", 0 if drove else helper["man"])),
        "win": uv.get("win", helper["win"]),
        "ts_opn": ts.get("opn", helper_ts["opn"]),
        "ts_cls": ts.get("cls", helper_ts["cls"]),
        "ts_due": ts.get("due", helper_ts["due"]),
        "ts_arm": ts.get("arm", helper_ts["arm"]),
    }


def _movement(ctx: dict, s: dict) -> dict:
    plan = ctx.get("drive_plan") or {}
    run = bool(plan.get("run"))
    move = plan.get("move", "full")
    target = plan.get("target")
    target_tilt = plan.get("target_tilt")
    position_relevant = move != "tilt" and target is not None
    tilt_relevant = (
        s["is_cover_tilt_enabled_and_possible"] and target_tilt is not None
    )
    position_moves = (
        position_relevant
        and abs(int(target) - s["current_position"]) > s["position_tolerance"]
    )
    tilt_moves = (
        tilt_relevant
        and abs(int(target_tilt) - s["current_tilt_position"])
        > s["tilt_position_tolerance"]
    )
    # Mirrors apply_transition: a full plan moves when either its position or
    # relevant tilt differs; a tilt-only plan deliberately ignores position.
    moves = run and (tilt_moves if move == "tilt" else position_moves or tilt_moves)
    return {"moves": moves,
            "target": int(target) if moves and position_relevant else None,
            "tilt": int(target_tilt) if moves and tilt_relevant else None,
            "action_set": (plan.get("action_set") or "") if moves else ""}


def run_live(s: dict, direction: str, verdicts: dict | None = None) -> dict:
    trigger_id = "t_close_1" if direction == "closing" else "t_open_1"
    alias = "Check for closing" if direction == "closing" else "Check for opening"
    ctx, entities = _context(s, trigger_id)
    runner = Runner(ctx, entities, verdicts or DEFAULT_VERDICTS)
    branch = _branch(alias)
    if not runner.conditions(branch["conditions"]):
        return {"entered": False,
                "final": _resolved({}, ctx["helper_json"]),
                **_movement({}, s)}
    runner.run(branch["sequence"])
    movement = _movement(runner.ctx, s)
    return {"entered": True,
            "final": _resolved(runner.ctx, ctx["helper_json"], movement["moves"]),
            **movement}


def run_recovery(s: dict, verdicts: dict | None = None) -> dict:
    ctx, entities = _context(s, "t_recovery")
    runner = Runner(ctx, entities, verdicts or DEFAULT_VERDICTS)
    runner.run(_branch_body(RECOVERY))
    movement = _movement(runner.ctx, s)
    return {"entered": True,
            "new_base": runner.ctx["new_base"],
            "state": runner.ctx["recovered_state"],
            "final": _resolved(runner.ctx, ctx["helper_json"], movement["moves"]),
            **movement}


HYGIENE_FIELDS = ("win",)   # re-read from the live sensors on every recovery run


def assert_paired(s: dict, direction: str = "closing",
                  verdicts: dict | None = None, hygiene: tuple = HYGIENE_FIELDS):
    """Full-outcome comparison. `hygiene` names the declared recovery-only fields;
    everything else must match the live outcome (or, when live does not run,
    remain unchanged)."""
    live = run_live(s, direction, verdicts)
    recovery = run_recovery(s, verdicts)
    assert recovery["moves"] == live["moves"], (live, recovery)
    if live["moves"]:
        assert recovery["target"] == live["target"]
        assert recovery["tilt"] == live["tilt"]
        assert recovery["action_set"] == live["action_set"]
    for field, value in live["final"].items():
        if field in hygiene:
            continue
        assert recovery["final"][field] == value, (
            f"field {field!r}: live={value!r} recovery={recovery['final'][field]!r}")
    # the hygiene win field must match the live contact-handler outcome: the sensors
    expected_win = s["window"] if s["is_ventilation_enabled"] else s["helper"]["win"]
    assert recovery["final"]["win"] == expected_win
    return live, recovery


# ════════════════════════════════════════════════════════════════════════════
# The exact #656 regression, and its neighbours
# ════════════════════════════════════════════════════════════════════════════
class TestIssue656Regression:
    @pytest.mark.parametrize("brightness", ["6780", "7032"])
    def test_both_paths_reject_the_bright_evening_closing(self, brightness):
        s = scenario(brightness=brightness)
        live, recovery = assert_paired(s)
        assert live["entered"] is False
        assert recovery["new_base"] == "opn"
        assert recovery["moves"] is False

    def test_outage_mode_is_a_catch_up_for_a_mid_day_dropout(self):
        tpl = BP["variables"]["recovery_catch_up"]
        assert _render(tpl, {}, recovery_mode="outage", is_restart_run=False,
                       instance_activated=False,
                       trigger=types.SimpleNamespace(id="t_recovery")).strip() == "True"

    def test_both_paths_accept_once_it_is_dark(self):
        live, recovery = assert_paired(scenario(brightness="40"))
        assert live["entered"] and live["moves"] and live["target"] == 0
        assert recovery["final"]["bas"] == "cls" and recovery["final"]["ts_cls"] == "now"

    def test_both_paths_accept_at_the_ultimate_closing_time(self):
        live, recovery = assert_paired(scenario(is_time_down_late=True))
        assert live["moves"] and recovery["target"] == 0


# ════════════════════════════════════════════════════════════════════════════
# Environment modes
# ════════════════════════════════════════════════════════════════════════════
class TestEnvironmentParity:
    @pytest.mark.parametrize("brightness,closes", [
        ("70", False), ("65", False), ("60", True),
    ])
    def test_hysteresis_boundary(self, brightness, closes):
        live, _ = assert_paired(scenario(brightness=brightness, brightness_hysteresis=10))
        assert live["entered"] is closes

    @pytest.mark.parametrize("and_operator,closes", [(False, True), (True, False)])
    def test_and_or_operator(self, and_operator, closes):
        s = scenario(default_sun_sensor="sun.sun", is_sun_elevation_enabled=True,
                     current_sun_elevation=-3.0, use_and_operator=and_operator)
        live, _ = assert_paired(s)
        assert live["entered"] is closes


# ════════════════════════════════════════════════════════════════════════════
# Manual override: direction-specific parity for caught-up transitions
# ════════════════════════════════════════════════════════════════════════════
class TestManualOverrideParity:
    def test_override_with_the_closing_ignore_option_advances_state_but_blocks_drive(self):
        s = scenario(brightness="40", helper={"man": 1},
                     override_flags={"opening": False, "closing": True,
                                     "ventilation": False, "shading": False})
        live, recovery = assert_paired(s)
        assert live["entered"] is True
        assert live["final"]["bas"] == recovery["final"]["bas"] == "cls"
        assert live["final"]["man"] == recovery["final"]["man"] == 1
        assert live["moves"] is recovery["moves"] is False

    def test_override_without_ignore_options_drives_both_and_clears_man(self):
        """Live closes right over an unprotected manual position and clears man -
        the caught-up closing must do exactly the same, not conservatively hold."""
        s = scenario(brightness="40", helper={"man": 1})
        live, recovery = assert_paired(s)
        assert live["entered"] and live["moves"]
        assert live["final"]["man"] == 0 and recovery["final"]["man"] == 0

    def test_opening_override_cases(self):
        morning = dict(brightness="5000", is_opening_phase=True, is_daytime_phase=True,
                       is_closing_phase=False, is_evening_phase=False,
                       helper={"bas": "cls", "man": 1}, current_position=0)
        blocked = scenario(**morning,
                           override_flags={"opening": True, "closing": False,
                                           "ventilation": False, "shading": False})
        live, recovery = assert_paired(blocked, "opening")
        assert live["entered"] is True
        assert live["final"]["bas"] == recovery["final"]["bas"] == "opn"
        assert live["moves"] is recovery["moves"] is False
        allowed = scenario(**morning)
        live, recovery = assert_paired(allowed, "opening")
        assert live["moves"] and recovery["final"]["man"] == 0

    def test_an_expired_override_is_the_post_repair_reconciliation(self):
        """Recovery-only composition, deliberate: the reset the outage swallowed is
        applied first (man -> 0), then the flip proceeds - live's timeline depends on
        an unknowable event order, and its reset (BRANCH 10 default) clears man
        without ever driving, leaving the missed movement missed."""
        s = scenario(brightness="40", helper={"man": 1}, override_expired=True,
                     override_flags={"opening": False, "closing": True,
                                     "ventilation": False, "shading": False})
        recovery = run_recovery(s)
        assert recovery["final"]["bas"] == "cls"
        assert recovery["moves"] and recovery["final"]["man"] == 0


# ════════════════════════════════════════════════════════════════════════════
# Once-a-day guards
# ════════════════════════════════════════════════════════════════════════════
class TestOncePerDayParity:
    def test_a_second_closing_of_the_day_blocks_both(self):
        closed_at = NOW.replace(hour=18, minute=0).timestamp()
        s = scenario(brightness="40",
                     prevent_flags=dict(SCENARIO_DEFAULTS["prevent_flags"],
                                        closing_multiple_times=True),
                     helper_ts_close=closed_at, helper_ts_man=closed_at + 600)
        live, recovery = assert_paired(s)
        assert live["entered"] is False and recovery["final"]["bas"] == "opn"

    def test_a_second_opening_of_the_day_blocks_both(self):
        s = scenario(brightness="5000", is_opening_phase=True, is_daytime_phase=True,
                     is_closing_phase=False, is_evening_phase=False,
                     helper={"bas": "cls"}, current_position=0,
                     prevent_flags=dict(SCENARIO_DEFAULTS["prevent_flags"],
                                        opening_multiple_times=True),
                     helper_ts_open=NOW_TS - 3600, helper_ts_man=NOW_TS - 600)
        live, recovery = assert_paired(s, "opening")
        assert live["entered"] is False and recovery["final"]["bas"] == "cls"


# ════════════════════════════════════════════════════════════════════════════
# Windows: the ventilation condition, the lockout paths
# ════════════════════════════════════════════════════════════════════════════
class TestWindowParity:
    def test_full_window_lockout_overrules_opening_manual_and_resident(self):
        s = scenario(
            brightness="5000", is_opening_phase=True, is_daytime_phase=True,
            is_closing_phase=False, is_evening_phase=False,
            window="opn", current_position=40, state_resident=True,
            resident_config=[], helper={"bas": "cls", "man": 1},
            override_flags={"opening": True, "closing": False,
                            "ventilation": False, "shading": False},
        )
        live, recovery = assert_paired(s, "opening")
        assert live["moves"] and recovery["moves"]
        assert live["target"] == recovery["target"] == 100

    def test_recovery_lockout_overrules_closing_manual_and_resident(self):
        s = scenario(
            brightness="40", window="opn", current_position=40,
            state_resident=True, resident_config=[], helper={"man": 1},
            override_flags={"opening": False, "closing": True,
                            "ventilation": True, "shading": False},
        )
        recovery = run_recovery(s)
        assert recovery["state"] == "lock"
        assert recovery["moves"] and recovery["target"] == 100

    def test_tilted_window_goes_to_ventilation_in_both_paths(self):
        live, recovery = assert_paired(scenario(
            brightness="40", window="tlt",
            is_cover_tilt_enabled_and_possible=True,
        ))
        assert live["moves"] and live["target"] == 50
        assert recovery["state"] == "vnt" and recovery["tilt"] == 60
        assert recovery["action_set"] == "ventilate"

    def test_refused_ventilation_condition_closes_both_paths(self):
        """THE regression the hand-written oracle hid: with auto_ventilate_condition
        false the live closing falls through its ventilation leaf and closes fully.
        The recovery used to bypass the condition (the cascade cannot evaluate
        !input) and drove to the ventilation position instead. It now evaluates the
        SAME anchored condition node and falls back to the same target."""
        verdicts = dict(DEFAULT_VERDICTS, auto_ventilate_condition=False)
        s = scenario(brightness="40", window="tlt")
        live, recovery = assert_paired(s, verdicts=verdicts)
        assert live["entered"] and live["moves"] and live["target"] == 0
        assert recovery["state"] == "cls"
        assert recovery["target"] == 0 and recovery["action_set"] == "down"

    def test_tilted_lockout_option_holds_both_paths(self):
        s = scenario(brightness="40", window="tlt", lockout_tilted_when_closing=True)
        live, recovery = assert_paired(s)
        assert live["entered"] and live["moves"] is False
        assert recovery["moves"] is False
        assert live["final"]["bas"] == recovery["final"]["bas"] == "cls"

    def test_tilted_lockout_option_holds_even_with_the_condition_refused(self):
        """C-A sits BEFORE the ventilation leaf and never evaluates the condition -
        the masked cascade ('cls') must not lower the cover onto the tilted window."""
        verdicts = dict(DEFAULT_VERDICTS, auto_ventilate_condition=False)
        s = scenario(brightness="40", window="tlt", lockout_tilted_when_closing=True)
        live, recovery = assert_paired(s, verdicts=verdicts)
        assert live["moves"] is False and recovery["moves"] is False

    def test_open_window_lockout_records_the_closing_in_both_paths(self):
        """Live C-A: status only. The recovery reconciles the position to the lockout
        target - the outcome the (equally swallowed) contact-opened handler
        establishes; at the lockout position the two paths are identical. The win
        marker difference is the declared hygiene field (sensor truth vs. C-A's
        'opn' stamp - here both are 'opn')."""
        s = scenario(brightness="40", window="opn")
        live, recovery = assert_paired(s)
        assert live["entered"] and live["moves"] is False
        assert recovery["state"] == "lock" and recovery["moves"] is False
        assert live["final"]["win"] == recovery["final"]["win"] == "opn"

    def test_open_window_away_from_lockout_position_is_reconciled(self):
        """DOCUMENTED recovery-only step (recovery-parity.md): with the cover away
        from the lockout position, the live closing leaves it (the contact event
        already ran, live) while the recovery catches that swallowed contact-handler
        movement up. Same target the contact handler drives to."""
        s = scenario(brightness="40", window="opn", current_position=40)
        recovery = run_recovery(s)
        assert recovery["state"] == "lock"
        assert recovery["moves"] and recovery["target"] == 100
        contact = _branch("Contact sensor state changed")
        lockout_leaf = next(
            b for step in contact["sequence"] if isinstance(step, dict) and "choose" in step
            for b in step["choose"] if "Full ventilation (lockout)" in str(b.get("alias", "")))
        assert lockout_leaf is not None   # the live handler that owns this movement

    def test_refused_ventilation_condition_does_not_recover_to_lockout(self):
        """The live contact-opened leaf is gated by the user's ventilation
        condition. Recovery must not perform the movement that leaf refused."""
        verdicts = dict(DEFAULT_VERDICTS, auto_ventilate_condition=False)
        s = scenario(brightness="40", window="opn", current_position=40)
        live, recovery = assert_paired(s, verdicts=verdicts)
        assert live["entered"] and live["moves"] is False
        assert recovery["state"] == "lock"
        assert recovery["moves"] is False


# ════════════════════════════════════════════════════════════════════════════
# Shading interplay
# ════════════════════════════════════════════════════════════════════════════
class TestShadingParity:
    def test_closing_shortcut_clears_shading_and_pending(self):
        s = scenario(
            brightness="40", current_position=0, live_force="cls",
            helper={"bas": "opn", "frc": "cls", "shd": 1, "pnd": "beg"},
            helper_ts_pending_due=NOW_TS + 600,
            helper_ts_pending_arm=NOW_TS - 60,
        )
        live = run_live(s, "closing")
        assert live["entered"] and live["moves"] is False
        assert live["final"]["bas"] == "cls"
        assert live["final"]["shd"] == 0
        assert live["final"]["pnd"] == "non"
        assert live["final"]["ts_due"] == live["final"]["ts_arm"] == 0

    def test_refused_ventilation_condition_does_not_remove_the_shading_floor(self):
        """The live shading-start floor has no auto_ventilate_condition gate.
        A global recovery mask must therefore not turn its VENT target into SHD."""
        verdicts = dict(DEFAULT_VERDICTS, auto_ventilate_condition=False)
        s = scenario(brightness="40", window="tlt",
                     helper={"bas": "cls", "shd": 1},
                     current_position=50)
        recovery = run_recovery(s, verdicts)
        assert recovery["new_base"] == "cls"
        assert recovery["state"] == "vnt"
        assert recovery["moves"] is False

    def test_a_caught_up_closing_ends_the_shading_in_both_paths(self):
        s = scenario(brightness="40", helper={"shd": 1},
                     current_position=20)
        live, recovery = assert_paired(s)
        assert live["moves"] and live["target"] == 0
        assert recovery["state"] == "cls"
        assert live["final"]["shd"] == recovery["final"]["shd"] == 0
        assert live["final"]["pnd"] == recovery["final"]["pnd"] == "non"

    def test_a_caught_up_closing_drops_an_armed_pending_like_live_does(self):
        s = scenario(brightness="40", helper={"pnd": "beg"},
                     helper_ts_pending_due=NOW_TS + 600,
                     helper_ts_pending_arm=NOW_TS - 60)
        live, recovery = assert_paired(s)
        assert live["final"]["pnd"] == recovery["final"]["pnd"] == "non"
        assert live["final"]["ts_due"] == recovery["final"]["ts_due"] == 0
        assert live["final"]["ts_arm"] == recovery["final"]["ts_arm"] == 0

    def test_prevent_lowering_when_shaded_holds_both_paths(self):
        s = scenario(brightness="40", helper={"shd": 1}, current_position=20,
                     close_position=30, effective_shading_position=20,
                     prevent_flags=dict(SCENARIO_DEFAULTS["prevent_flags"],
                                        lowering_when_closing_if_shaded=True))
        live, recovery = assert_paired(s)
        assert live["entered"] and live["moves"] is False
        assert recovery["moves"] is False
        assert live["final"]["bas"] == recovery["final"]["bas"] == "cls"

    def test_prevent_higher_position_closing_holds_both_paths(self):
        s = scenario(brightness="40", current_position=10, close_position=30,
                     prevent_flags=dict(SCENARIO_DEFAULTS["prevent_flags"],
                                        higher_position_closing=True))
        live, recovery = assert_paired(s)
        assert live["moves"] is False and recovery["moves"] is False


# ════════════════════════════════════════════════════════════════════════════
# Opening parity
# ════════════════════════════════════════════════════════════════════════════
class TestOpeningParity:
    def _morning(self, **over):
        base = dict(brightness="40", is_opening_phase=True, is_daytime_phase=True,
                    is_closing_phase=False, is_evening_phase=False,
                    helper={"bas": "cls"}, current_position=0)
        base.update(over)
        return scenario(**base)

    def test_a_dark_morning_blocks_both(self):
        live, recovery = assert_paired(self._morning(), "opening")
        assert live["entered"] is False and recovery["final"]["bas"] == "cls"

    def test_a_bright_morning_opens_both(self):
        live, recovery = assert_paired(self._morning(brightness="5000"), "opening")
        assert live["moves"] and live["target"] == 100
        assert recovery["final"]["bas"] == "opn"
        assert recovery["final"]["ts_opn"] == live["final"]["ts_opn"] == "now"
        assert recovery["action_set"] == "up"

    def test_the_ultimate_opening_time_opens_both(self):
        live, recovery = assert_paired(self._morning(is_time_up_late=True), "opening")
        assert live["moves"] and recovery["moves"]

    def test_an_active_shading_moves_both_paths_to_the_shading_position(self):
        """Live O-C ('Shading detected') and the recovery keep shd and drive to the
        shading position instead of opening."""
        s = self._morning(brightness="5000", helper={"bas": "cls", "shd": 1},
                          current_position=0)
        live, recovery = assert_paired(s, "opening")
        assert live["moves"] and live["target"] == 20
        assert recovery["state"] == "shd" and recovery["target"] == 20
        assert live["final"]["shd"] == recovery["final"]["shd"] == 1

    def test_a_resident_blocked_opening_does_not_become_a_closing_drive(self):
        """Live only records the opening edge; recovery also repairs the
        resident/privacy target whose event may have been swallowed."""
        s = self._morning(brightness="5000", state_resident=True,
                          resident_config=[], current_position=100)
        live = run_live(s, "opening")
        recovery = run_recovery(s)
        assert live["entered"] and live["moves"] is False
        assert recovery["state"] == "cls"
        assert recovery["moves"] and recovery["target"] == 0

    def test_an_open_window_still_uses_the_opening_lockout_target(self):
        """The user ventilation condition blocks lockout actuation in both
        paths, while the background opening and window state still progress."""
        verdicts = dict(DEFAULT_VERDICTS, auto_ventilate_condition=False)
        s = self._morning(brightness="5000", window="opn", current_position=40)
        live, recovery = assert_paired(s, "opening", verdicts)
        assert live["moves"] is False
        assert recovery["state"] == "lock"
        assert recovery["moves"] is False


# ════════════════════════════════════════════════════════════════════════════
# Force and pause
# ════════════════════════════════════════════════════════════════════════════
class TestForceAndPauseParity:
    def test_position_match_but_wrong_tilt_is_a_real_drive_in_both_paths(self):
        s = scenario(
            brightness="40", current_position=0, current_tilt_position=100,
            is_cover_tilt_enabled_and_possible=True,
        )
        live, recovery = assert_paired(s)
        assert live["moves"] and recovery["moves"]
        assert live["target"] == recovery["target"] == 0
        assert live["tilt"] == recovery["tilt"] == 0

    def test_matching_position_and_tilt_is_a_true_noop(self):
        s = scenario(
            brightness="40", current_position=0, current_tilt_position=0,
            is_cover_tilt_enabled_and_possible=True,
        )
        live, recovery = assert_paired(s)
        assert live["moves"] is recovery["moves"] is False

    def test_a_conflicting_force_suppresses_the_drive_in_both_paths(self):
        s = scenario(brightness="40", force_allows_close=False)
        live, recovery = assert_paired(s, hygiene=("win", "man"))
        assert live["entered"] and live["moves"] is False
        assert recovery["moves"] is False
        assert live["final"]["bas"] == recovery["final"]["bas"] == "cls"

    def test_the_force_pause_suppresses_the_drive_in_both_paths(self):
        s = scenario(brightness="40", is_paused=True)
        live, recovery = assert_paired(s, hygiene=("win", "man"))
        assert live["moves"] is False and recovery["moves"] is False

    def test_an_active_force_wins_in_the_recovery_cascade(self):
        s = scenario(brightness="40", live_force="cls",
                     helper={"frc": "cls", "bas": "cls"})
        recovery = run_recovery(s)
        assert recovery["state"] == "cls"

    def test_a_caught_up_closing_does_not_execute_a_conflicting_force_target(self):
        """Recovery reconciles the current cascade, so a force that became
        active during the outage wins over the simultaneous base flip."""
        s = scenario(brightness="40", current_position=40, live_force="opn",
                     helper={"frc": "opn"}, force_allows_close=False)
        live = run_live(s, "closing")
        recovery = run_recovery(s)
        assert live["entered"] and live["moves"] is False
        assert recovery["state"] == "opn"
        assert recovery["moves"] and recovery["target"] == 100


# ════════════════════════════════════════════════════════════════════════════
# Resident overlay
# ════════════════════════════════════════════════════════════════════════════
class TestResidentParity:
    def test_privacy_closing_targets_close_in_both_cascades(self):
        s = scenario(brightness="40", state_resident=True,
                     resident_config=["resident_closing_enabled"])
        live, recovery = assert_paired(s)
        assert live["moves"] and live["target"] == 0
        assert recovery["state"] == "cls"


# ════════════════════════════════════════════════════════════════════════════
# Structural: the entry-condition shape is CLOSED
# ════════════════════════════════════════════════════════════════════════════
class TestClosedEntryStructure:
    """Whitelist, not blocklist: the live open/close entries and the recovery flip
    conditions must consist of EXACTLY the known terms. Any new inline business
    predicate - '{{ holiday_allows_closing }}' included - fails this test until it
    is routed through the shared projections (references/recovery-parity.md)."""

    def _flip_gate(self):
        from test_restart_recovery import _walk_steps
        return next(s for s in _walk_steps(_branch_body(RECOVERY))
                    if "additional condition" in str(s.get("alias", "")))

    def _flip(self, direction):
        return next(b for b in self._flip_gate()["choose"] if direction in b["alias"])

    @pytest.mark.parametrize("direction,alias,flag,input_name", [
        ("opening", "Check for opening", "is_up_enabled", "auto_up_condition"),
        ("closing", "Check for closing", "is_down_enabled", "auto_down_condition"),
    ])
    def test_the_live_entry_is_exactly_the_known_shape(self, direction, alias, flag,
                                                       input_name):
        conds = _branch(alias)["conditions"]
        assert conds[0] == "{{ %s }}" % flag
        assert conds[1] == "{{ trigger.id is defined }}"
        assert "trigger.id | regex_match" in conds[2]
        assert conds[3] == {"condition": input_name}
        assert conds[4:] == [
            "{{ base_gates.%s.once_ok }}" % direction,
            "{{ base_gates.%s.schedule_ok }}" % direction,
        ]

    def test_the_opening_flip_is_exactly_the_known_shape(self):
        conds = self._flip("opening")["conditions"]
        assert conds == [
            "{{ recovery_catch_up and recovered_base == 'opn' and helper_state_base != 'opn' }}",
            "{{ base_gates.opening.schedule_ok }}",
            "{{ base_gates.opening.once_ok }}",
            {"condition": "auto_up_condition"},
        ]

    def test_the_closing_flip_is_exactly_the_known_shape(self):
        conds = self._flip("closing")["conditions"]
        assert conds == [
            "{{ recovery_catch_up and recovered_base == 'cls' and helper_state_base != 'cls' }}",
            "{{ not is_evening_phase or base_gates.closing.schedule_ok }}",
            "{{ base_gates.closing.once_ok }}",
            {"condition": "auto_down_condition"},
        ]

    @pytest.mark.parametrize("direction,alias,input_name", [
        ("opening", "Check for opening", "auto_up_condition"),
        ("closing", "Check for closing", "auto_down_condition"),
    ])
    def test_the_input_condition_is_the_same_yaml_node(self, direction, alias,
                                                       input_name):
        live_node = next(c for c in _branch(alias)["conditions"]
                         if isinstance(c, dict) and "condition" in c)
        flip_node = next(c for c in self._flip(direction)["conditions"]
                         if isinstance(c, dict) and "condition" in c)
        assert live_node["condition"] == input_name
        assert live_node is flip_node

    def test_the_ventilate_condition_is_the_same_yaml_node_everywhere(self):
        """The recovery anchors auto_ventilate_condition; every live consumer must
        alias that node - a fresh `condition: !input auto_ventilate_condition`
        elsewhere would be a second, driftable copy."""
        def nodes(node):
            if isinstance(node, dict):
                if node.get("condition") == "auto_ventilate_condition":
                    yield node
                for value in node.values():
                    yield from nodes(value)
            elif isinstance(node, list):
                for item in node:
                    yield from nodes(item)

        found = list(nodes(BP["actions"]))
        assert len(found) >= 8            # the anchor + at least 7 aliased consumers
        assert all(n is found[0] for n in found)

    def test_the_closing_position_hold_is_shared(self):
        closing = _branch("Check for closing")
        nested = next(s["choose"] for s in closing["sequence"]
                      if isinstance(s, dict) and "choose" in s)
        live = next(b for b in nested if "Only status change" in str(b.get("alias", "")))
        assert live["conditions"] == ["{{ closing_position_hold }}"]
        from test_restart_recovery import _branch_var
        assert "closing_position_hold" in _branch_var(RECOVERY, "caught_up_closing_hold")

    def test_the_projections_are_defined_exactly_once(self):
        gates = _action_var("base_gates")
        for direction in ("opening", "closing"):
            assert set(gates[direction]) == {"override_ok", "once_ok", "schedule_ok"}
