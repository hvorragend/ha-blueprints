"""
Tests for restart/outage handling: the availability gates and the recovery branch.

Two halves that only work together:

  1. The GATE (global conditions) stops a run while a state-critical entity has no
     usable state, so no wrong status can be persisted.
  2. The RECOVERY (t_recovery -> the recovery gate) replays what the outage swallowed:
     time/calendar triggers of that period never fire again, and template/numeric
     triggers only fire on a false->true transition, which is consumed while the
     run is blocked.

The dangerous part of a gate is what it ORPHANS. Three cases needed an exception
and each has a test here:

  * contact triggers    -> gate exemption   (else the gate blocks the very event
                           that would clear `win`, deadlocking itself)
  * helper `unknown`    -> gate blocks on `unavailable` only (else the init/repair
                           step is unreachable and the automation is dead forever)
  * override reset      -> re-evaluated in the recovery gate (`override_expired`), because
                           t_reset_timeout/t_reset_position latch and never re-fire

All templates are extracted verbatim from the blueprint, so these tests exercise
the real logic rather than a copy of it.
"""
import datetime
import pathlib
import re
import types

import jinja2
import pytest
import yaml


BLUEPRINT_PATH = (
    pathlib.Path(__file__).parent.parent
    / "blueprints"
    / "automation"
    / "cover_control_automation.yaml"
)

INVALID_STATES = ["", "unavailable", "unknown", "none", "None", "null", "query failed", []]

# Fixed clock so timestamp arithmetic is deterministic
NOW = datetime.datetime(2026, 7, 12, 21, 0, 0)
NOW_TS = NOW.timestamp()


def _load_blueprint() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


BP = _load_blueprint()


class _States:
    """HA's `states` is both callable (`states(x)`) and subscriptable (`states[x].last_changed`)."""

    def __init__(self, entity_states: dict, last_changed: dict):
        self._states = entity_states
        self._last_changed = last_changed

    def __call__(self, entity_id):
        if isinstance(entity_id, list):  # unconfigured input -> []
            return "unknown"
        return self._states.get(entity_id, "unknown")

    def __getitem__(self, entity_id):
        return types.SimpleNamespace(
            state=self(entity_id),
            last_changed=self._last_changed.get(entity_id, NOW),
        )


def _env(entity_states: dict | None = None, last_changed: dict | None = None,
         strict: bool = True) -> jinja2.Environment:
    """Jinja env with the HA globals/filters the blueprint templates use.

    strict=True makes an unset variable an error instead of an empty string. Without it
    a mutation that swaps a variable for one the test does not pass would render '' and
    look like a behaviour change - a false kill. Only the branch-dispatch test, which
    renders gates in isolation, opts out.
    """

    def today_at(value="00:00:00"):
        hh, mm, ss = (list(map(int, str(value).split(":"))) + [0, 0])[:3]
        return NOW.replace(hour=hh, minute=mm, second=ss, microsecond=0)

    def timestamp_custom(ts, fmt="%Y-%m-%d", local=True):
        return datetime.datetime.fromtimestamp(float(ts)).strftime(fmt)

    env = jinja2.Environment(undefined=jinja2.StrictUndefined if strict else jinja2.Undefined)
    env.globals["states"] = _States(entity_states or {}, last_changed or {})
    env.globals["now"] = lambda: NOW
    env.globals["today_at"] = today_at
    env.globals["as_timestamp"] = lambda value, default=None: (
        value.timestamp() if isinstance(value, datetime.datetime) else float(value)
    )
    env.filters["timestamp_custom"] = timestamp_custom
    env.filters["regex_match"] = lambda v, p, ignorecase=False: re.match(p, str(v)) is not None
    env.filters["regex_search"] = lambda v, p, ignorecase=False: re.search(p, str(v)) is not None
    env.tests["match"] = lambda v, p, ignorecase=False: re.match(p, str(v)) is not None
    return env


def _render(template_str: str, entity_states: dict | None = None, last_changed: dict | None = None,
            strict: bool = True, **variables) -> str:
    env = _env(entity_states, last_changed, strict)
    return env.from_string(template_str).render(**variables).strip()


def _render_bool(template_str: str, entity_states: dict | None = None, last_changed: dict | None = None,
                 strict: bool = True, **variables) -> bool:
    """Render and parse like HA does (literal_eval); a bare 'false' would be TRUTHY."""
    out = _render(template_str, entity_states, last_changed, strict, **variables)
    if out == "True":
        return True
    if out == "False":
        return False
    return bool(out)  # non-empty string is truthy - exactly the HA trap


def _condition(match: str) -> str:
    """Return the global condition whose value_template contains `match`."""
    for cond in BP["conditions"]:
        if isinstance(cond, dict) and match in str(cond.get("value_template", "")):
            return cond["value_template"]
    raise AssertionError(f"no global condition containing {match!r}")


def _top_level_branches() -> list[dict]:
    for step in BP["actions"]:
        if isinstance(step, dict) and "choose" in step and len(step["choose"]) > 5:
            return step["choose"]
    raise AssertionError("top-level choose not found")


def _branch(alias_prefix: str) -> dict:
    """A dispatch branch of the main choose, or a pre-dispatch step (the recovery gate,
    which is deliberately NOT one of the numbered branches - it runs before the dispatch)."""
    for b in _top_level_branches():
        if b.get("alias", "").startswith(alias_prefix):
            return b
    for step in BP["actions"]:
        if isinstance(step, dict) and str(step.get("alias", "")).startswith(alias_prefix):
            return step
    raise AssertionError(f"branch {alias_prefix!r} not found")


def _branch_body(alias_prefix: str) -> list:
    """The steps a branch runs: `sequence:` in a choose branch, `then:` in an if-step."""
    b = _branch(alias_prefix)
    return b.get("sequence") or b.get("then")


def _branch_gate(alias_prefix: str) -> list:
    """The entry conditions: `conditions:` in a choose branch, `if:` in an if-step."""
    b = _branch(alias_prefix)
    return b.get("conditions") or b.get("if")


def _branch_var(alias_prefix: str, name: str) -> str:
    """Pull one variable template out of a branch's body."""
    for step in _branch_body(alias_prefix):
        if isinstance(step, dict) and name in step.get("variables", {}):
            return step["variables"][name]
    raise AssertionError(f"variable {name!r} not found in branch {alias_prefix!r}")


def _action_var(name: str):
    """Pull one variable out of the action-level `variables:` steps (the shared
    projections the refactor introduced: state_targets, shading_once_guard_ok, ...)."""
    for step in BP["actions"]:
        if isinstance(step, dict) and name in step.get("variables", {}):
            return step["variables"][name]
    raise AssertionError(f"action-level variable {name!r} not found")


def _top_var(name: str) -> str:
    return BP["variables"][name]


def _state_targets(**variables) -> dict:
    """Render the real state_targets map from the blueprint, so tests that build a
    drive_plan exercise the same projection the automation uses (incl. the
    alternate shading position)."""
    return {
        state: {key: _render(tpl, {}, **variables) for key, tpl in params.items()}
        for state, params in _action_var("state_targets").items()
    }


def _shading_once_guard_ok(**variables) -> bool:
    return _render_bool(_action_var("shading_once_guard_ok"), {}, **variables)


RECOVERY = "Recovery after restart or outage"


def _recovery_update_values() -> dict:
    return _branch_var(RECOVERY, "update_values")


# ════════════════════════════════════════════════════════════════════════════
# GATE: state-critical entities
# ════════════════════════════════════════════════════════════════════════════
class TestCriticalEntitiesGate:
    def test_helper_is_not_critical_so_it_stays_repairable(self):
        """An `unknown` helper must NOT be blocked - the init step must be reachable."""
        assert "cover_status_helper" not in BP["trigger_variables"]["critical_entities"]

    def test_cover_and_position_sensor_are_critical(self):
        tpl = BP["trigger_variables"]["critical_entities"]
        assert "blind" in tpl
        assert "custom_position_sensor" in tpl

    def test_list_contains_cover(self):
        out = _render(
            BP["trigger_variables"]["critical_entities"],
            blind="cover.x",
            cover_status_helper="input_text.h",
            position_source="current_position_attr",
            custom_position_sensor=[],
        )
        assert "cover.x" in out and "input_text.h" not in out

    def test_position_sensor_only_when_it_is_the_source(self):
        args = dict(blind="cover.x", cover_status_helper="input_text.h", custom_position_sensor="sensor.pos")
        assert "sensor.pos" in _render(
            BP["trigger_variables"]["critical_entities"], position_source="custom_sensor", **args
        )
        assert "sensor.pos" not in _render(
            BP["trigger_variables"]["critical_entities"], position_source="current_position_attr", **args
        )

    @pytest.mark.parametrize("cover_state,ready", [
        ("open", True), ("closed", True), ("opening", True),
        ("unavailable", False), ("unknown", False),
    ])
    def test_gate_blocks_unusable_cover(self, cover_state, ready):
        gate = _condition("critical_entities")
        assert _render_bool(
            gate,
            {"cover.x": cover_state},
            critical_entities=["cover.x"],
            invalid_states=INVALID_STATES,
        ) is ready


# ════════════════════════════════════════════════════════════════════════════
# GATE: status helper - must stay repairable
# ════════════════════════════════════════════════════════════════════════════
class TestHelperGate:
    GATE = staticmethod(lambda: _condition("cover_status_helper == [] or states(cover_status_helper)"))

    @pytest.mark.parametrize("helper_state,passes", [
        ("unavailable", False),          # entity not loaded, stored value intact -> block
        ("unknown", True),               # no value left -> must pass so init can repair
        ("", True),                      # empty -> repairable
        ("garbage", True),               # corrupt -> repairable
        ('{"bas":"opn","v":6}', True),   # healthy
    ])
    def test_only_unavailable_blocks(self, helper_state, passes):
        assert _render_bool(
            self.GATE(),
            {"input_text.h": helper_state},
            cover_status_helper="input_text.h",
        ) is passes

    def test_unconfigured_helper_passes_so_validation_can_report_it(self):
        assert _render_bool(self.GATE(), {}, cover_status_helper=[]) is True

    def test_init_repair_step_exists(self):
        """The step the gate must not orphan."""
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        assert "Initialise empty helper with JSON default values" in text


# ════════════════════════════════════════════════════════════════════════════
# GATE: window contacts - last-known fallback + deadlock exemption
# ════════════════════════════════════════════════════════════════════════════
class TestContactGate:
    GATE = staticmethod(lambda: _condition("last_window_closed"))

    def _run(self, *, contact_state, win, trigger_id="t_close_1", vent=True):
        helper = '{"bas":"opn","shd":0,"pnd":"non","win":"%s","frc":"non","res":0,"man":0,"v":6}' % win
        return _render_bool(
            self.GATE(),
            {"input_text.h": helper, "binary_sensor.opened": contact_state, "binary_sensor.tilted": "off"},
            cover_status_helper="input_text.h",
            contact_window_opened="binary_sensor.opened",
            contact_window_tilted="binary_sensor.tilted",
            is_ventilation_enabled=vent,
            invalid_states=INVALID_STATES,
            trigger=types.SimpleNamespace(id=trigger_id),
        )

    def test_stateless_contact_passes_when_window_was_closed(self):
        """Battery sensor after a hub restart: 'reads as closed' matches the truth."""
        assert self._run(contact_state="unavailable", win="cls") is True

    @pytest.mark.parametrize("win", ["opn", "tlt"])
    def test_stateless_contact_blocks_when_window_was_open(self, win):
        """Acting would treat the window as closed and drop the lockout."""
        assert self._run(contact_state="unavailable", win=win) is False

    @pytest.mark.parametrize("trigger_id", ["t_contact_opened_changed", "t_contact_tilted_changed"])
    def test_contact_triggers_are_exempt(self, trigger_id):
        """DEADLOCK GUARD: without this, the event that would clear `win` is the one
        the gate blocks - so `win` stays 'opn' forever and CCA never runs again."""
        assert self._run(contact_state="unavailable", win="opn", trigger_id=trigger_id) is True

    @pytest.mark.parametrize("trigger_id", ["t_manual_position", "t_manual_tilt"])
    def test_manual_triggers_are_exempt(self, trigger_id):
        """A manual move during a contact outage must still be recorded (`man: 1`) -
        the handler only writes the helper, it never drives the cover. Without the
        exemption the recovery would later overrule the user's manual intervention."""
        assert self._run(contact_state="unavailable", win="opn", trigger_id=trigger_id) is True

    def test_healthy_contact_always_passes(self):
        assert self._run(contact_state="on", win="opn") is True

    def test_ventilation_disabled_ignores_contacts(self):
        assert self._run(contact_state="unavailable", win="opn", vent=False) is True


# ════════════════════════════════════════════════════════════════════════════
# state_resident: last-known fallback + the boolean render trap
# ════════════════════════════════════════════════════════════════════════════
class TestResidentFallback:
    TPL = staticmethod(lambda: BP["variables"]["state_resident"])

    def test_no_sensor_renders_real_false_not_the_string_false(self):
        """A bare `false` inside {% if %} renders the STRING 'false', which HA's
        literal_eval cannot parse - and a non-empty string is TRUTHY. That would
        report 'resident present' for every user without a sensor, flipping
        allow_open to false and closing the cover instead of opening it."""
        out = _render(self.TPL(), {}, resident_sensor=[], helper_json={}, invalid_states=INVALID_STATES)
        assert out == "False", f"must render the literal False, got {out!r}"

    @pytest.mark.parametrize("sensor_state,res,expected", [
        ("on", 0, True),
        ("off", 1, False),
        ("unavailable", 1, True),   # fallback: last known presence
        ("unavailable", 0, False),
        ("unknown", 1, True),
    ])
    def test_fallback_to_helper_while_sensor_is_unusable(self, sensor_state, res, expected):
        assert _render_bool(
            self.TPL(),
            {"binary_sensor.res": sensor_state},
            resident_sensor="binary_sensor.res",
            helper_json={"res": res},
            invalid_states=INVALID_STATES,
        ) is expected


# ════════════════════════════════════════════════════════════════════════════
# override_expired: the latching reset triggers
# ════════════════════════════════════════════════════════════════════════════
class TestOverrideExpired:
    TPL = staticmethod(lambda: BP["variables"]["override_expired"])

    def _run(self, **over):
        base = dict(
            helper_state_manual=True,
            is_reset_disabled=False,
            is_reset_timeout=True,
            is_reset_fixed_time=False,
            is_reset_position=False,
            in_reset_override_position=False,
            helper_ts_man=NOW_TS - 3600,   # override set 1 h ago
            reset_override_timeout=30,     # minutes
            reset_override_time="03:00:00",
        )
        base.update(over)
        return _render_bool(self.TPL(), {}, **base)

    def test_timeout_elapsed_during_outage_is_detected(self):
        """t_reset_timeout latches (`man==1 and now>=ts.man+timeout` stays true), so a
        restart swallows it and it never fires again -> the override would be eternal."""
        assert self._run() is True

    def test_timeout_not_yet_elapsed(self):
        assert self._run(reset_override_timeout=120) is False

    def test_no_manual_override_nothing_to_expire(self):
        assert self._run(helper_state_manual=False) is False

    def test_reset_disabled_never_expires(self):
        assert self._run(is_reset_disabled=True) is False

    def test_reset_in_position(self):
        assert self._run(
            is_reset_timeout=False, is_reset_position=True, in_reset_override_position=True
        ) is True
        assert self._run(
            is_reset_timeout=False, is_reset_position=True, in_reset_override_position=False
        ) is False

    def test_fixed_time_only_clears_overrides_older_than_todays_reset(self):
        # reset at 03:00, override set 1 h ago (20:00) -> must NOT clear until tomorrow
        assert self._run(is_reset_timeout=False, is_reset_fixed_time=True) is False
        # override set before today's 03:00 -> clear
        assert self._run(
            is_reset_timeout=False,
            is_reset_fixed_time=True,
            helper_ts_man=NOW.replace(hour=1).timestamp(),
        ) is True

    def test_the_manual_gate_blocks_the_drive_not_the_helper_hygiene(self):
        """The gate lives in recovery_allowed, NOT in the branch conditions. If it gated the
        branch, a manual override would also block the stale-day cleanup - so a shading from
        three days ago would survive the recovery whenever man == 1."""
        assert not any("helper_state_manual" in str(c) for c in _branch_gate(RECOVERY))
        allowed = _branch_var(RECOVERY, "recovery_allowed")
        assert "helper_state_manual" in allowed and "override_expired" in allowed

    def test_recovery_clears_man_when_expired(self):
        for step in _branch_body(RECOVERY):
            uv = step.get("variables", {}).get("update_values") if isinstance(step, dict) else None
            if uv and "man" in uv:
                assert "override_expired" in uv["man"]
                return
        raise AssertionError("recovery branch does not write man")


# ════════════════════════════════════════════════════════════════════════════
# Recovery gate: base state re-derived from the schedule
# ════════════════════════════════════════════════════════════════════════════
class TestRecoveredBase:
    TPL = staticmethod(lambda: _branch_var(RECOVERY, "recovered_base"))

    def _run(self, **over):
        base = dict(
            is_time_control_disabled=False,
            is_down_enabled=True,
            is_up_enabled=True,
            is_evening_phase=False,
            is_daytime_phase=False,
            helper_state_base="opn",
        )
        base.update(over)
        return _render(self.TPL(), {}, **base)

    def test_missed_closing_is_caught_up(self):
        """The 22:00 closing during a restart never fires again - nothing else moves bas."""
        assert self._run(is_evening_phase=True, helper_state_base="opn") == "cls"

    def test_missed_opening_is_caught_up(self):
        assert self._run(is_daytime_phase=True, helper_state_base="cls") == "opn"

    def test_night_keeps_the_helper_base(self):
        assert self._run(helper_state_base="cls") == "cls"

    def test_time_control_disabled_keeps_the_helper_base(self):
        assert self._run(is_time_control_disabled=True, is_evening_phase=True, helper_state_base="opn") == "opn"

    def test_no_closing_schedule_does_not_invent_one(self):
        assert self._run(is_down_enabled=False, is_evening_phase=True, helper_state_base="opn") == "opn"


# ════════════════════════════════════════════════════════════════════════════
# Recovery gate: recovered_state must stay in sync with effective_state
# ════════════════════════════════════════════════════════════════════════════
class TestCascadeParity:
    """recovered_state mirrors effective_state, but on the re-derived base state and
    the live force. Fed identical inputs, both MUST agree - this is the guard for the
    documented sync obligation between the two cascades."""

    CASES = [
        # (bas, shd, frc, opened, tilted, resident, cfg, is_opening_scheduled)
        ("opn", 0, "non", "off", "off", "off", [], True),
        ("cls", 0, "non", "off", "off", "off", [], True),
        ("opn", 1, "non", "off", "off", "off", [], True),
        ("cls", 1, "non", "off", "off", "off", [], True),
        ("opn", 0, "non", "on", "off", "off", [], True),          # lockout
        ("cls", 0, "non", "on", "off", "off", [], True),          # lockout
        ("cls", 0, "non", "on", "on", "off", [], True),           # Invariant 5: opened beats tilted
        ("cls", 1, "non", "on", "on", "off", [], True),
        ("opn", 0, "non", "off", "on", "off", [], True),          # base=opn beats vent
        ("opn", 0, "non", "off", "on", "off", [], False),         # no schedule -> vent (#553)
        ("cls", 0, "non", "off", "on", "off", [], True),          # vent floor
        ("cls", 1, "non", "off", "on", "off", [], True),          # vent floor over shading
        ("opn", 0, "cls", "off", "off", "off", [], True),         # force wins
        ("opn", 0, "shd", "on", "off", "off", [], True),          # force beats lockout
        ("opn", 0, "non", "off", "off", "on", ["resident_closing_enabled"], True),   # privacy
        ("opn", 1, "non", "off", "off", "on", ["resident_allow_shading"], True),
        ("opn", 0, "non", "off", "off", "on", [], True),          # present, opening not allowed
        ("cls", 1, "non", "off", "off", "on", [], True),
    ]

    @pytest.mark.parametrize("bas,shd,frc,opened,tilted,resident,cfg,sched", CASES)
    def test_both_cascades_agree(self, bas, shd, frc, opened, tilted, resident, cfg, sched):
        entities = {
            "binary_sensor.opened": opened,
            "binary_sensor.tilted": tilted,
            "binary_sensor.res": resident,
        }
        helper = {"bas": bas, "shd": shd, "frc": frc, "win": "cls", "res": 0, "man": 0, "pnd": "non"}
        present = resident == "on"
        shared = dict(
            contact_window_opened="binary_sensor.opened",
            contact_window_tilted="binary_sensor.tilted",
            state_resident=present,
            is_opening_scheduled=sched,
        )

        effective = _render(
            BP["variables"]["effective_state"], entities,
            helper_json=helper, resident_config=cfg, **shared,
        )
        recovered = _render(
            _branch_var(RECOVERY, "recovered_state"), entities,
            live_force=frc,
            recovered_base=bas,
            recovered_window=_render(_branch_var(RECOVERY, "recovered_window"), entities,
                                     helper_state_window=helper["win"], **shared),
            recovered_shade=(shd == 1),
            resident_flags={
                "closing_trigger": "resident_closing_enabled" in cfg,
                "allow_open": ("resident_allow_opening" in cfg) or not present,
                "allow_shade": ("resident_allow_shading" in cfg) or not present,
                "allow_ventilate": ("resident_allow_ventilation" in cfg) or not present,
            },
            **shared,
        )
        assert recovered == effective, (
            f"cascades diverged for bas={bas} shd={shd} frc={frc} "
            f"opened={opened} tilted={tilted} resident={resident}: "
            f"effective_state={effective!r} vs recovered_state={recovered!r}"
        )

    def test_recovered_state_uses_live_force_not_the_stale_helper(self):
        """A force switched off during the outage leaves frc stale in the helper."""
        tpl = _branch_var(RECOVERY, "recovered_state")
        assert "live_force" in tpl and "helper_state_force" not in tpl


# ════════════════════════════════════════════════════════════════════════════
# Recovery gate: recovered_state on inputs that DIVERGE from the helper
#
# The parity test above feeds both cascades the same base/force, so by construction
# it can never see whether recovered_state accidentally reads the stale helper. That
# is the whole point of the recovery, so it needs its own table.
# ════════════════════════════════════════════════════════════════════════════
class TestRecoveredStateUsesRecoveredInputs:
    def _run(self, *, recovered_base, live_force, helper_bas, helper_frc,
             window="cls", shade=False, present=False, cfg=(), sched=True):
        return _render(
            _branch_var(RECOVERY, "recovered_state"), {},
            recovered_base=recovered_base,
            live_force=live_force,
            recovered_window=window,
            helper_state_base=helper_bas,      # the stale values - must NOT be used
            helper_state_force=helper_frc,
            recovered_shade=shade,
            state_resident=present,
            is_opening_scheduled=sched,
            resident_flags={
                "closing_trigger": "resident_closing_enabled" in cfg,
                "allow_open": ("resident_allow_opening" in cfg) or not present,
                "allow_shade": ("resident_allow_shading" in cfg) or not present,
                "allow_ventilate": ("resident_allow_ventilation" in cfg) or not present,
            },
        )

    def test_missed_closing_drives_close_although_the_helper_still_says_open(self):
        """The 22:00 closing fell into the outage. bas is still 'opn' in the helper."""
        assert self._run(recovered_base="cls", helper_bas="opn",
                         live_force="non", helper_frc="non") == "cls"

    def test_missed_opening_drives_open_although_the_helper_still_says_closed(self):
        assert self._run(recovered_base="opn", helper_bas="cls",
                         live_force="non", helper_frc="non") == "opn"

    def test_force_switched_off_during_the_outage_is_not_resurrected(self):
        """frc is stale in the helper; the live switch is the truth."""
        assert self._run(recovered_base="opn", helper_bas="opn",
                         live_force="non", helper_frc="cls") == "opn"

    def test_force_switched_on_during_the_outage_wins(self):
        assert self._run(recovered_base="opn", helper_bas="opn",
                         live_force="cls", helper_frc="non") == "cls"


# ════════════════════════════════════════════════════════════════════════════
# live_force: a force entity is a switch/binary_sensor and can drop out too
# ════════════════════════════════════════════════════════════════════════════
class TestLiveForceFallback:
    TPL = staticmethod(lambda: BP["variables"]["live_force"])
    UNREADABLE = staticmethod(lambda: BP["variables"]["force_helper_unreadable"])

    FORCES = dict(
        auto_up_force="switch.up",
        auto_down_force="switch.down",
        auto_shading_start_force="switch.shade",
        auto_ventilate_force="switch.vent",
    )

    def _flags(self, entities):
        return dict(
            is_forced_open=entities.get("switch.up") in ("on", "true"),
            is_forced_close=entities.get("switch.down") in ("on", "true"),
            is_forced_shade=entities.get("switch.shade") in ("on", "true"),
            is_forced_vent=entities.get("switch.vent") in ("on", "true"),
        )

    def _run(self, entities, helper_frc, last_changed=None):
        unreadable = _render_bool(
            self.UNREADABLE(), entities,
            helper_state_force=helper_frc, invalid_states=INVALID_STATES, **self.FORCES,
        )
        return _render(
            self.TPL(), entities, last_changed,
            helper_state_force=helper_frc,
            force_helper_unreadable=unreadable,
            **self._flags(entities), **self.FORCES,
        )

    def test_all_switches_readable_and_off_means_no_force(self):
        entities = {"switch.up": "off", "switch.down": "off", "switch.shade": "off", "switch.vent": "off"}
        assert self._run(entities, helper_frc="non") == "non"

    def test_a_force_turned_off_during_the_outage_is_cleared(self):
        """The switch is readable and off - so we KNOW the force ended."""
        entities = {"switch.up": "off", "switch.down": "off", "switch.shade": "off", "switch.vent": "off"}
        assert self._run(entities, helper_frc="cls") == "non"

    @pytest.mark.parametrize("frc,entity", [
        ("opn", "switch.up"), ("cls", "switch.down"),
        ("shd", "switch.shade"), ("vnt", "switch.vent"),
    ])
    @pytest.mark.parametrize("bad", ["unavailable", "unknown"])
    def test_unreadable_switch_keeps_the_last_known_force(self, frc, entity, bad):
        """Without this, an unreadable switch reads as 'not on' -> the force is silently
        cancelled and the cover drives to the scheduled target. Its own triggers use
        from: 'on'/'off', so `unavailable -> on` never re-establishes it."""
        entities = {e: "off" for e in self.FORCES.values()}
        entities[entity] = bad
        assert self._run(entities, helper_frc=frc) == frc

    def test_an_unrelated_unreadable_switch_does_not_keep_the_force(self):
        """The helper's own force switch IS readable and off -> the force really ended."""
        entities = {e: "off" for e in self.FORCES.values()}
        entities["switch.up"] = "unavailable"
        assert self._run(entities, helper_frc="cls") == "non"

    def test_a_live_force_beats_the_fallback(self):
        entities = {e: "off" for e in self.FORCES.values()}
        entities["switch.up"] = "unavailable"   # helper's force, unreadable
        entities["switch.vent"] = "on"          # but this one is genuinely on
        assert self._run(entities, helper_frc="opn") == "vnt"

    def test_last_activated_wins(self):
        entities = {e: "off" for e in self.FORCES.values()}
        entities["switch.down"] = "on"
        entities["switch.shade"] = "on"
        older = NOW - datetime.timedelta(hours=2)
        assert self._run(entities, "non", {"switch.down": older, "switch.shade": NOW}) == "shd"
        assert self._run(entities, "non", {"switch.down": NOW, "switch.shade": older}) == "cls"

    @pytest.mark.parametrize("entity_input", [
        "auto_up_force", "auto_down_force", "auto_shading_start_force",
        "auto_ventilate_force", "force_pause",
    ])
    def test_force_entities_report_back(self, entity_input):
        """t_force_enabled_*/t_force_disabled_* use from: 'on'/'off', so a transition out
        of an unusable state does not fire them. Only t_recovery re-syncs the force."""
        recovery = [t for t in BP["triggers"] if t.get("id") == "t_recovery"]
        assert any(t.get("entity_id") == entity_input for t in recovery), entity_input


# ════════════════════════════════════════════════════════════════════════════
# Recovery gate: recovered_window
# ════════════════════════════════════════════════════════════════════════════
class TestRecoveredWindow:
    TPL = staticmethod(lambda: _branch_var(RECOVERY, "recovered_window"))

    def _run(self, opened, tilted, helper_win="cls", configured=True):
        entities = {"binary_sensor.opened": opened, "binary_sensor.tilted": tilted}
        return _render(
            self.TPL(), entities,
            contact_window_opened="binary_sensor.opened" if configured else [],
            contact_window_tilted="binary_sensor.tilted" if configured else [],
            helper_state_window=helper_win,
        )

    @pytest.mark.parametrize("opened,tilted,expected", [
        ("off", "off", "cls"),
        ("on", "off", "opn"),
        ("off", "on", "tlt"),
        ("on", "on", "opn"),   # Invariant 5: opened ALWAYS beats tilted
    ])
    def test_contact_precedence(self, opened, tilted, expected):
        assert self._run(opened, tilted) == expected

    @pytest.mark.parametrize("helper_win", ["cls", "tlt", "opn"])
    def test_no_contacts_configured_keeps_the_helper_window(self, helper_win):
        """Without contacts there is nothing to read - inventing 'cls' would drop the
        window state of a user who drives ventilation from the helper alone."""
        assert self._run("off", "off", helper_win=helper_win, configured=False) == helper_win


# ════════════════════════════════════════════════════════════════════════════
# Recovery gate: the shading pending - re-evaluated, not replayed
# ════════════════════════════════════════════════════════════════════════════
class TestRecoveredPending:
    STALE = staticmethod(lambda: _branch_var(RECOVERY, "pending_is_stale"))
    TPL = staticmethod(lambda: _branch_var(RECOVERY, "recovered_pending"))
    NEW = staticmethod(lambda: _branch_var(RECOVERY, "new_pending"))

    def _stale(self, pending, due, stale_day=False):
        return _render_bool(self.STALE(), {}, helper_state_pending=pending,
                            helper_ts_pending_due=due, stale_day=stale_day)

    def _run(self, **over):
        base = dict(
            is_recovery_enabled=True,
            is_shading_enabled=True,
            helper_state_pending="non",
            pending_is_stale=False,
            recovered_shade=False,
            shading_start_warranted=True,
            shading_end_conditions_met=False,
            prevent_flags={"shading_multiple_times": False},
            helper_ts_shade=0,
        )
        base.update(over)
        # The once-per-day guard is the shared action-level projection; render the real
        # one from the blueprint so this still exercises prevent_flags / helper_ts_shade.
        base["shading_once_guard_ok"] = _shading_once_guard_ok(
            prevent_flags=base["prevent_flags"], helper_ts_shade=base["helper_ts_shade"])
        return _render(self.TPL(), {}, **base)

    def _new(self, recovered, stale, current):
        return _render(self.NEW(), {}, recovered_pending=recovered,
                       pending_is_stale=stale, helper_state_pending=current)

    # --- pending_is_stale ---
    def test_a_due_time_in_the_past_is_stale(self):
        """Its execution trigger fired during the outage and was blocked - and it only
        fires on false->true, so it can never fire again. The pending is dead."""
        assert self._stale("beg", NOW_TS - 60) is True

    def test_a_due_time_in_the_future_is_not_stale(self):
        assert self._stale("beg", NOW_TS + 600) is False

    def test_no_pending_is_never_stale(self):
        assert self._stale("non", 0) is False

    def test_a_pending_from_an_earlier_day_is_stale_even_with_a_future_due_time(self):
        assert self._stale("beg", NOW_TS + 600, stale_day=True) is True

    # --- recovered_pending ---
    def test_shading_due_now_arms_a_start(self):
        assert self._run() == "beg"

    def test_shading_over_arms_an_end(self):
        assert self._run(recovered_shade=True, shading_start_warranted=False,
                         shading_end_conditions_met=True) == "end"

    def test_nothing_to_do(self):
        assert self._run(shading_start_warranted=False) == "non"

    def test_shading_disabled_never_arms(self):
        assert self._run(is_shading_enabled=False) == "non"

    def test_an_armed_pending_that_is_still_alive_is_left_alone(self):
        """Re-arming would push ts.due forward on every recovering source and could
        starve the pending forever."""
        assert self._run(helper_state_pending="beg") == "non"
        assert self._new(recovered="non", stale=False, current="beg") == "beg"

    def test_a_stale_pending_is_re_evaluated_from_scratch(self):
        assert self._run(helper_state_pending="beg", pending_is_stale=True) == "beg"

    def test_a_stale_pending_with_no_conditions_left_is_cleared(self):
        assert self._run(helper_state_pending="beg", pending_is_stale=True,
                         shading_start_warranted=False) == "non"
        assert self._new(recovered="non", stale=True, current="beg") == "non"

    def test_once_per_day_guard_blocks_a_second_shading(self):
        assert self._run(prevent_flags={"shading_multiple_times": True},
                         helper_ts_shade=NOW_TS - 3600) == "non"

    def test_once_per_day_guard_allows_shading_on_a_new_day(self):
        yesterday = (NOW - datetime.timedelta(days=1)).timestamp()
        assert self._run(prevent_flags={"shading_multiple_times": True},
                         helper_ts_shade=yesterday) == "beg"

    # --- the opt-in only gates the arming, never the clean-up ---
    def test_without_the_opt_in_no_pending_is_armed(self):
        """Arming would drive the cover later, so it needs the opt-in."""
        assert self._run(is_recovery_enabled=False) == "non"
        assert self._run(is_recovery_enabled=False, recovered_shade=True,
                         shading_start_warranted=False,
                         shading_end_conditions_met=True) == "non"

    def test_without_the_opt_in_a_dead_pending_is_still_cleared(self):
        """Hygiene: a pending whose due time has passed can never execute again (its
        trigger only fires on false->true). Leaving it armed would block every new
        pending until the 23:55 reset - and clearing it moves nothing."""
        assert self._new(recovered="non", stale=True, current="beg") == "non"


# ════════════════════════════════════════════════════════════════════════════
# Recovery gate: recovered_due / recovered_arm mirror the arming branches
# ════════════════════════════════════════════════════════════════════════════
class TestRecoveredDueAndArm:
    DUE = staticmethod(lambda: _branch_var(RECOVERY, "recovered_due"))
    ARM = staticmethod(lambda: _branch_var(RECOVERY, "recovered_arm"))

    WINDOW_START = NOW.replace(hour=23, minute=0, second=0)  # opening still ahead

    def _run(self, tpl, **over):
        base = dict(
            recovered_pending="beg",
            pending_is_stale=False,
            is_time_control_disabled=False,
            is_shading_allowed_window=True,
            is_time_field_enabled=True,
            is_calendar_enabled=False,
            calendar_open_start=None,
            time_up_early_today="23:00:00",
            shading_waitingtime_start=300,
            shading_waitingtime_end=600,
            helper_ts_pending_due=1234,
            helper_ts_pending_arm=1000,
        )
        base.update(over)
        return int(_render(tpl, {}, **base))

    def test_inside_the_window_due_is_now_plus_the_waiting_time(self):
        assert self._run(self.DUE()) == int(NOW_TS) + 300

    def test_before_the_window_due_is_deferred_to_the_window_start(self):
        """Bug Pattern L: an execution that fires before the window aborts immediately."""
        due = self._run(self.DUE(), is_shading_allowed_window=False)
        assert due == int(self.WINDOW_START.timestamp()) + 1

    def test_before_the_window_arm_is_anchored_to_the_window_start(self):
        """Bug Pattern S: anchoring at the (early) arming moment silently eats the
        shading_start_max_duration budget with a wait that is not a retry."""
        arm = self._run(self.ARM(), is_shading_allowed_window=False)
        assert arm == int(self.WINDOW_START.timestamp())

    def test_inside_the_window_arm_is_now(self):
        assert self._run(self.ARM()) == int(NOW_TS)

    def test_calendar_window_start_is_honoured(self):
        cal_start = self.WINDOW_START.timestamp()
        assert self._run(self.DUE(), is_shading_allowed_window=False, is_time_field_enabled=False,
                         is_calendar_enabled=True, calendar_open_start=cal_start) == int(cal_start) + 1

    def test_end_pending_uses_the_end_waiting_time(self):
        assert self._run(self.DUE(), recovered_pending="end") == int(NOW_TS) + 600
        assert self._run(self.ARM(), recovered_pending="end") == int(NOW_TS)

    def test_a_stale_pending_clears_due_and_arm(self):
        assert self._run(self.DUE(), recovered_pending="non", pending_is_stale=True) == 0
        assert self._run(self.ARM(), recovered_pending="non", pending_is_stale=True) == 0

    def test_a_live_pending_keeps_its_due_and_arm(self):
        """Invariant 8: ts.arm is the retry anchor and must survive untouched."""
        assert self._run(self.DUE(), recovered_pending="non") == 1234
        assert self._run(self.ARM(), recovered_pending="non") == 1000


# ════════════════════════════════════════════════════════════════════════════
# Recovery gate: the drive - defer, lockout, target, force gate
# ════════════════════════════════════════════════════════════════════════════
class TestRecoveryDrive:
    LOCKOUT = staticmethod(lambda: _branch_var(RECOVERY, "lockout_blocks_shading"))
    DEFER = staticmethod(lambda: _branch_var(RECOVERY, "defer_to_shading"))
    TARGET = staticmethod(lambda: _branch_var(RECOVERY, "target_position"))
    TILT = staticmethod(lambda: _branch_var(RECOVERY, "target_tilt_position"))
    ALLOWED = staticmethod(lambda: _branch_var(RECOVERY, "recovery_allowed"))
    IN_POS = staticmethod(lambda: _branch_var(RECOVERY, "recovery_in_position"))

    def _lockout(self, window, vent=True, tilted_option=False):
        return _render_bool(self.LOCKOUT(), {}, recovered_window=window,
                            is_ventilation_enabled=vent,
                            lockout_tilted_when_shading_starts=tilted_option)

    def _defer(self, pending, state, lockout):
        return _render_bool(self.DEFER(), {}, recovered_pending=pending,
                            recovered_state=state, lockout_blocks_shading=lockout)

    # --- lockout_blocks_shading ---
    def test_an_open_window_blocks_shading(self):
        assert self._lockout("opn") is True

    def test_a_tilted_window_blocks_shading_only_with_the_option(self):
        assert self._lockout("tlt") is False
        assert self._lockout("tlt", tilted_option=True) is True

    def test_ventilation_disabled_means_the_contacts_do_not_exist(self):
        """Bug Pattern AC: every direct contact read must be scoped to is_ventilation_enabled."""
        assert self._lockout("opn", vent=False) is False

    # --- defer_to_shading ---
    def test_opening_is_deferred_to_the_shading_execution(self):
        """#555: driving open first and shading a second later would be a double move."""
        assert self._defer("beg", "opn", lockout=False) is True

    def test_no_defer_while_the_lockout_window_is_open(self):
        """Bug Pattern AG: the shading execution only STORES the intent under lockout -
        it never opens the cover. Deferring there dead-ends and the cover stays put."""
        assert self._defer("beg", "opn", lockout=True) is False

    def test_no_defer_without_a_start_pending(self):
        assert self._defer("non", "opn", lockout=False) is False
        assert self._defer("end", "opn", lockout=False) is False

    def test_no_defer_when_the_target_is_not_open(self):
        assert self._defer("beg", "cls", lockout=False) is False

    # --- targets ---
    POSITIONS = dict(open_position=100, close_position=0, ventilate_position=50, shading_position=30,
                     open_tilt_position=100, close_tilt_position=0,
                     ventilate_tilt_position=60, shading_tilt_position=40)

    def _targets(self, state, effective_shading_position=30):
        """Drive parameters via the real state_targets projection from the blueprint."""
        targets = _state_targets(effective_shading_position=effective_shading_position,
                                 **self.POSITIONS)
        return (int(_render(self.TARGET(), {}, recovered_state=state, state_targets=targets)),
                int(_render(self.TILT(), {}, recovered_state=state, state_targets=targets)))

    @pytest.mark.parametrize("state,pos,tilt", [
        ("lock", 100, 100), ("opn", 100, 100), ("vnt", 50, 60),
        ("shd", 30, 40), ("cls", 0, 0),
    ])
    def test_target_per_state(self, state, pos, tilt):
        assert self._targets(state) == (pos, tilt)

    def test_the_shading_target_honours_the_alternate_shading_position(self):
        """#580: every other shading drive uses effective_shading_position. If the recovery
        used the plain shading_position, a restart while the alternate position is active
        would drag the cover back to the normal one - and recovery_in_position (which
        compares against the recovery's own target) would not even notice."""
        assert self._targets("shd", effective_shading_position=70) == (70, 40)

    def test_the_recovery_drives_through_the_shared_projection(self):
        """Guard against re-hardcoding the position chain: the target must come from
        state_targets, not from a local if/else over the position inputs."""
        assert "state_targets" in self.TARGET()
        assert "state_targets" in self.TILT()

    # --- the user's drive actions on a caught-up movement ---
    def _action_set(self, state, in_position, will_drive=True):
        plan = _branch_var(RECOVERY, "drive_plan")
        targets = _state_targets(effective_shading_position=30, **self.POSITIONS)
        return _render(plan["action_set"], {}, recovered_state=state,
                       state_targets=targets, recovery_in_position=in_position,
                       will_drive=will_drive)

    @pytest.mark.parametrize("state,action_set", [
        ("opn", "up"), ("cls", "down"), ("vnt", "ventilate"),
        ("shd", "shading_start"), ("lock", "ventilate"),
    ])
    def test_a_caught_up_movement_runs_the_users_drive_actions(self, state, action_set):
        """A closing the outage swallowed and the recovery catches up IS a closing - it
        must run auto_down_action, exactly like the scheduled handler would have."""
        assert self._action_set(state, in_position=False) == action_set

    @pytest.mark.parametrize("state", ["opn", "cls", "vnt", "shd", "lock"])
    def test_no_drive_actions_when_the_cover_does_not_move(self, state):
        """recovery_allowed carries NO position check (unlike state_gates) - it must stay
        true so a tilt-only correction still runs. So drive_plan.run is true on virtually
        every recovery run and cover_move_action no-ops via its tolerance guard. But the
        before/after actions in drive_with_actions sit OUTSIDE that guard: without this
        gate each of the ~19 recovery sources would re-fire the user's notifications and
        scenes after a restart although nothing moved."""
        assert self._action_set(state, in_position=True) == ""

    @pytest.mark.parametrize("state", ["opn", "cls", "vnt", "shd", "lock"])
    def test_a_hygiene_only_run_runs_no_drive_actions(self, state):
        """Without the opt-in the gate cleans the helper and stops. It never drives, so
        the user's before/after actions must not fire either."""
        assert self._action_set(state, in_position=False, will_drive=False) == ""

    # --- recovery_allowed ---
    def _allowed(self, state, **over):
        base = dict(force_allows_open=True, force_allows_close=True,
                    force_allows_shade=True, force_allows_ventilate=True,
                    defer_to_shading=False, helper_state_manual=False, override_expired=False)
        base.update(over)
        return _render_bool(self.ALLOWED(), {}, recovered_state=state, **base)

    @pytest.mark.parametrize("state,blocking", [
        ("lock", "force_allows_ventilate"), ("vnt", "force_allows_ventilate"),
        ("opn", "force_allows_open"), ("shd", "force_allows_shade"),
        ("cls", "force_allows_close"),
    ])
    def test_a_conflicting_force_blocks_the_drive(self, state, blocking):
        assert self._allowed(state) is True
        assert self._allowed(state, **{blocking: False}) is False

    def test_deferring_to_shading_means_no_drive_here(self):
        assert self._allowed("opn", defer_to_shading=True) is False

    # --- the manual override gate (moved here from the branch conditions) ---
    def test_a_manual_override_blocks_the_drive(self):
        assert self._allowed("cls", helper_state_manual=True) is False

    def test_an_expired_manual_override_does_not_block(self):
        assert self._allowed("cls", helper_state_manual=True, override_expired=True) is True

    def test_lockout_overrules_a_manual_override(self):
        """Invariant 6: lockout is a safety feature and beats manual intent."""
        assert self._allowed("lock", helper_state_manual=True) is True

    # --- recovery_in_position ---
    @pytest.mark.parametrize("current,expected", [(100, True), (96, True), (94, False), (0, False)])
    def test_in_position_uses_the_tolerance(self, current, expected):
        assert _render_bool(self.IN_POS(), {}, target_position=100,
                            current_position=current, position_tolerance=5) is expected


# ════════════════════════════════════════════════════════════════════════════
# Recovery gate: what actually lands in the helper
# ════════════════════════════════════════════════════════════════════════════
class TestRecoveryPersists:
    """A recovery that computes the right thing and then writes the stale one is
    worthless - and every field here is read back as a fallback on the next outage."""

    def _render_field(self, field, **variables):
        return _render(_recovery_update_values()[field], {}, **variables)

    def test_the_re_derived_base_is_written(self):
        assert self._render_field("bas", new_base="cls") == "cls"

    def test_the_re_read_window_is_written(self):
        assert self._render_field("win", recovered_window="tlt") == "tlt"

    def test_the_live_force_is_written(self):
        assert self._render_field("frc", live_force="vnt") == "vnt"

    @pytest.mark.parametrize("present,expected", [(True, "1"), (False, "0")])
    def test_the_re_read_resident_is_written(self, present, expected):
        """res is the fallback state_resident reads on the NEXT sensor dropout. Leaving
        it stale after a presence change during the outage poisons that fallback."""
        assert self._render_field("res", state_resident=present) == expected

    def test_the_recovered_pending_is_written(self):
        assert self._render_field("pnd", new_pending="beg") == "beg"

    def test_base_timestamps_are_stamped_only_on_a_real_change(self):
        args = dict(helper_ts_open=111, helper_ts_close=222, stale_day=False)
        ts = _recovery_update_values()["ts"]
        assert _render(ts["cls"], {}, new_base="cls", helper_state_base="opn", **args) == "now"
        assert _render(ts["cls"], {}, new_base="cls", helper_state_base="cls", **args) == "222"
        assert _render(ts["opn"], {}, new_base="opn", helper_state_base="cls", **args) == "now"
        assert _render(ts["opn"], {}, new_base="opn", helper_state_base="opn", **args) == "111"

    def _man(self, **over):
        base = dict(override_expired=False, will_drive=True, recovery_in_position=False,
                    helper_json={"man": 1})
        base.update(over)
        return _render(_recovery_update_values()["man"], {}, **base)

    def test_man_is_cleared_when_the_recovery_actually_drives(self):
        assert self._man() == "0"

    def test_man_is_kept_when_nothing_moves(self):
        """Invariant 7: man: 0 only when the cover is actually driven."""
        assert self._man(recovery_in_position=True) == "1"
        assert self._man(will_drive=False) == "1"

    def test_an_expired_override_is_cleared_even_without_a_drive(self):
        assert self._man(override_expired=True, recovery_in_position=True) == "0"

    def test_the_users_override_reset_action_runs_for_a_swallowed_reset(self):
        """BRANCH 10 runs it on every reset. A reset caught up by the recovery must not
        silently skip the notification/scene the user wired to it."""
        steps = _branch_body(RECOVERY)
        assert any(
            isinstance(s, dict) and "override_expired" in str(s.get("if", ""))
            and "auto_override_reset_action" in str(s.get("then", ""))
            for s in steps
        ), "override_reset_action is not run when the recovery clears an expired override"


# ════════════════════════════════════════════════════════════════════════════
# The automation was switched off and on again
#
# This is NOT a restart. No entity became unavailable, and `homeassistant: start` does
# not fire. Nothing reports it - yet every latching trigger (shading execution, override
# reset) is already true when the triggers are re-attached, so it can never fire again.
# ════════════════════════════════════════════════════════════════════════════
class TestAutomationResumed:
    TPL = staticmethod(lambda: BP["variables"]["automation_resumed"])

    def _run(self, *, helper_written, attached):
        return _render_bool(self.TPL(), {}, helper_ts_write=helper_written,
                            this={"last_changed": attached})

    def test_a_helper_older_than_the_switch_on_means_resumed(self):
        """`this` is a snapshot taken when the triggers were attached, so last_changed is
        the moment the automation was switched on."""
        assert self._run(helper_written=NOW_TS - 86400 * 3, attached=NOW - datetime.timedelta(minutes=5)) is True

    def test_a_helper_written_after_the_switch_on_means_business_as_usual(self):
        """Self-clearing: once the recovery has written the helper, this must go false -
        otherwise EVERY subsequent trigger would be swallowed by the recovery."""
        assert self._run(helper_written=NOW_TS, attached=NOW - datetime.timedelta(minutes=5)) is False

    def test_a_fresh_helper_is_not_a_resume(self):
        """t == 0 means CCA never wrote it - there is nothing to recover, and the init
        step owns that case."""
        assert self._run(helper_written=0, attached=NOW - datetime.timedelta(minutes=5)) is False

    def test_no_this_available_degrades_to_not_resumed(self):
        assert _render_bool(self.TPL(), {}, helper_ts_write=NOW_TS - 3600, this=None) is False


class TestResumeTrigger:
    """The trigger that makes the resume noticeable at all - without polling."""

    def _tpl(self) -> str:
        for t in BP["triggers"]:
            if t.get("id") == "t_recovery" and "this.last_changed" in str(t.get("value_template", "")):
                return t["value_template"]
        raise AssertionError("resume trigger not found")

    def _run(self, *, helper_t, attached, now_offset_s):
        helper = '{"bas":"opn","shd":0,"pnd":"non","win":"cls","frc":"non","res":0,"man":0,"v":6,"t":%d}' % helper_t
        env = _env({"input_text.h": helper})
        env.globals["now"] = lambda: attached + datetime.timedelta(seconds=now_offset_s)
        env.filters["from_json"] = lambda v, default=None: __import__("json").loads(v)
        out = env.from_string(self._tpl()).render(
            cover_status_helper="input_text.h",
            invalid_states=INVALID_STATES,
            this={"last_changed": attached},
        ).strip()
        return out == "True"

    ATTACHED = NOW - datetime.timedelta(days=3)
    STALE_T = int((NOW - datetime.timedelta(days=4)).timestamp())

    def test_it_is_false_at_attach_time_which_is_what_arms_it(self):
        """THE WHOLE POINT. A template trigger only fires on false -> true. At attach time
        the helper is ALREADY stale, so without the 60 s offset the template would be true
        from the start, the trigger would never arm, and it would never fire."""
        assert self._run(helper_t=self.STALE_T, attached=self.ATTACHED, now_offset_s=0) is False
        assert self._run(helper_t=self.STALE_T, attached=self.ATTACHED, now_offset_s=59) is False

    def test_it_fires_a_minute_after_the_automation_came_back(self):
        assert self._run(helper_t=self.STALE_T, attached=self.ATTACHED, now_offset_s=61) is True

    def test_it_stays_quiet_when_the_helper_is_current(self):
        """No polling: an automation that was never off never fires this trigger."""
        fresh = int((NOW - datetime.timedelta(days=2)).timestamp())  # written after attach
        assert self._run(helper_t=fresh, attached=self.ATTACHED, now_offset_s=3600) is False

    def test_a_fresh_helper_does_not_fire_it(self):
        assert self._run(helper_t=0, attached=self.ATTACHED, now_offset_s=3600) is False

    def test_it_is_a_recovery_trigger(self):
        assert any(t.get("value_template") == self._tpl() and t["id"] == "t_recovery"
                   for t in BP["triggers"])


class TestResumedRunClaimsEveryTrigger:
    def test_the_recovery_gate_runs_before_the_dispatch(self):
        """On a resumed run the recovery accepts ANY trigger id. If a dispatch branch could
        run first, it would act on the untrusted helper before the recovery could fix it.
        The gate is a pre-dispatch step, not a numbered branch - so it cannot be reordered
        into the choose by accident, and it leaves the branch indices alone."""
        steps = BP["actions"]
        gate = next(i for i, s in enumerate(steps)
                    if isinstance(s, dict) and str(s.get("alias", "")).startswith(RECOVERY))
        choose = next(i for i, s in enumerate(steps)
                      if isinstance(s, dict) and isinstance(s.get("choose"), list)
                      and len(s["choose"]) > 5)
        assert gate < choose
        assert "if" in steps[gate] and "then" in steps[gate]
        assert not any(b.get("alias", "").startswith(RECOVERY) for b in _top_level_branches()), \
            "the recovery must not also live inside the dispatch choose"

    def test_any_trigger_is_claimed_while_resumed(self):
        gate = next(c for c in _branch_gate(RECOVERY) if "trigger.id ==" in str(c))
        for tid in ["t_open_1", "t_close_5", "t_contact_opened_changed",
                    "t_shading_start_pending_1", "t_reset_timeout"]:
            assert _render_bool(gate, {}, trigger=types.SimpleNamespace(id=tid),
                                automation_resumed=True) is True, tid

    @pytest.mark.parametrize("tid", ["t_manual_position", "t_manual_tilt"])
    def test_the_manual_triggers_are_exempt_from_the_claim(self, tid):
        """The one exception to the claim, and it mirrors the contact gate's exemption:
        the manual handler never drives, it only RECORDS the intervention (man: 1, ts.man).
        If the recovery claimed the run, man: 1 would never be written, the recovery would
        read the stale man: 0 as "no override" and drive the cover back to the cascade target
        - fighting the move the user just made."""
        gate = next(c for c in _branch_gate(RECOVERY) if "trigger.id ==" in str(c))
        assert _render_bool(gate, {}, trigger=types.SimpleNamespace(id=tid),
                            automation_resumed=True) is False
        # ... but an explicit t_recovery run is still a recovery, whatever else is going on
        assert _render_bool(gate, {}, trigger=types.SimpleNamespace(id="t_recovery"),
                            automation_resumed=True) is True

    def test_the_manual_handler_is_reachable_on_a_resumed_run(self):
        """The other half of the exemption: with the recovery not claiming it, the manual
        branch must actually be the one that runs - it is what writes man: 1."""
        manual = next(b for b in _top_level_branches()
                      if "manual position changes" in b.get("alias", ""))
        gate = [c for c in manual["conditions"] if "trigger.id in" in str(c)]
        assert gate and _render_bool(gate[0], {}, trigger=types.SimpleNamespace(id="t_manual_position"))

    def test_normal_runs_are_not_claimed(self):
        gate = next(c for c in _branch_gate(RECOVERY) if "trigger.id ==" in str(c))
        for tid in ["t_open_1", "t_close_5", "t_manual_position"]:
            assert _render_bool(gate, {}, trigger=types.SimpleNamespace(id=tid),
                                automation_resumed=False) is False, tid
        assert _render_bool(gate, {}, trigger=types.SimpleNamespace(id="t_recovery"),
                            automation_resumed=False) is True


# ════════════════════════════════════════════════════════════════════════════
# The date changed while the automation was off
# ════════════════════════════════════════════════════════════════════════════
class TestStaleDay:
    """The 23:55 midnight reset clears shd/pnd every night. If the automation was off, it
    never ran - so a shading from three days ago still reads as active, and the first
    trigger after switching on would drive the cover into the shading position."""

    STALE = staticmethod(lambda: BP["variables"]["stale_day"])
    SHADE = staticmethod(lambda: _branch_var(RECOVERY, "recovered_shade"))

    def test_a_write_from_an_earlier_day_is_a_stale_day(self):
        assert _render_bool(self.STALE(), {}, helper_ts_write=NOW_TS - 86400 * 3) is True

    def test_a_write_from_today_is_not(self):
        assert _render_bool(self.STALE(), {}, helper_ts_write=NOW_TS - 3600) is False

    def test_a_month_old_write_on_the_same_day_of_month_is_still_stale(self):
        """A day-of-month compare would collapse here and read as 'today'."""
        month_ago = NOW.replace(month=NOW.month - 1).timestamp()
        assert _render_bool(self.STALE(), {}, helper_ts_write=month_ago) is True

    def test_a_fresh_helper_is_not_a_stale_day(self):
        assert _render_bool(self.STALE(), {}, helper_ts_write=0) is False

    def test_shading_from_an_earlier_day_is_dropped(self):
        assert _render_bool(self.SHADE(), {}, helper_state_shade=True, stale_day=True) is False

    def test_shading_from_today_survives(self):
        assert _render_bool(self.SHADE(), {}, helper_state_shade=True, stale_day=False) is True

    def test_the_cleared_shading_is_persisted(self):
        uv = _recovery_update_values()
        assert _render(uv["shd"], {}, recovered_shade=False) == "0"
        assert _render(uv["shd"], {}, recovered_shade=True) == "1"

    def test_ts_shd_is_NOT_stamped_when_the_shading_is_cleared(self):
        """The midnight reset may stamp ts.shd because it runs at 23:55 on the SAME day.
        This branch runs on the new day - stamping it with today would make the
        once-per-day guard block today's shading (Bug Pattern V)."""
        assert "shd" not in _recovery_update_values()["ts"]

    @pytest.mark.parametrize("field,helper_ts", [("opn", "helper_ts_open"), ("cls", "helper_ts_close")])
    def test_base_timestamps_from_an_earlier_day_are_zeroed(self, field, helper_ts):
        """They gate the 'only open/close once a day' guards. A timestamp from days ago
        must not be able to suppress today's opening or closing."""
        ts = _recovery_update_values()["ts"][field]
        args = {"new_base": field, "helper_state_base": field,
                "helper_ts_open": 111, "helper_ts_close": 222}
        assert _render(ts, {}, stale_day=True, **args) == "0"
        assert _render(ts, {}, stale_day=False, **args) == ("111" if field == "opn" else "222")


class TestOpeningGuardIsDateSafe:
    """The 'only open once a day' guard compared the DAY OF MONTH, so a ts.opn from exactly
    one month ago read as 'already opened today' and suppressed the opening."""

    def _guard(self) -> str:
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        line = [ln for ln in text.splitlines() if "prevent_flags.opening_multiple_times and" in ln]
        assert line, "opening guard not found"
        return line[0].split("- ", 1)[1].strip().strip('"')

    def _run(self, ts_open):
        # ts_man above ts_open, so the manual clause (Issue #311) cannot mask the date check
        return _render_bool(self._guard(), {}, prevent_flags={"opening_multiple_times": True},
                            helper_ts_open=ts_open, helper_ts_man=NOW_TS)

    def test_opened_today_blocks(self):
        assert self._run(NOW_TS - 3600) is False

    def test_opened_yesterday_allows(self):
        assert self._run(NOW_TS - 86400) is True

    def test_opened_exactly_one_month_ago_allows(self):
        assert self._run(NOW.replace(month=NOW.month - 1).timestamp()) is True

    def test_a_never_opened_helper_allows(self):
        assert self._run(0) is True


# ════════════════════════════════════════════════════════════════════════════
# Contact handler: resident_now has the same fallback as state_resident
# ════════════════════════════════════════════════════════════════════════════
class TestContactHandlerResidentFallback:
    def _tpl(self) -> str:
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        block = re.search(r"resident_now: >-\n(.*?)\n\s+# ", text, re.S)
        assert block, "resident_now not found"
        return block.group(1)

    @pytest.mark.parametrize("sensor_state,res,expected", [
        ("on", 0, True),
        ("off", 1, False),
        ("unavailable", 1, True),   # fallback: last known presence
        ("unavailable", 0, False),
    ])
    def test_fallback_matches_state_resident(self, sensor_state, res, expected):
        """The contact handler re-reads presence after its delay. Without the same
        fallback, a dropped sensor reads as 'away' and the privacy close is lost."""
        assert _render_bool(
            self._tpl(),
            {"binary_sensor.res": sensor_state},
            resident_sensor="binary_sensor.res",
            helper_json={"res": res},
            invalid_states=INVALID_STATES,
        ) is expected


# ════════════════════════════════════════════════════════════════════════════
# Triggers + wiring
# ════════════════════════════════════════════════════════════════════════════
class TestRecoveryTriggers:
    def _recovery(self) -> list[dict]:
        return [t for t in BP["triggers"] if t.get("id") == "t_recovery"]

    def test_homeassistant_start_is_a_recovery_trigger(self):
        """Covers sources that restore straight to a value (no unavailable phase)."""
        assert any(t["trigger"] == "homeassistant" and t.get("event") == "start" for t in self._recovery())

    @pytest.mark.parametrize("entity_input", [
        "blind", "cover_status_helper", "custom_position_sensor",
        "contact_window_opened", "contact_window_tilted", "resident_sensor",
        "default_brightness_sensor", "default_sun_sensor", "shading_forecast_sensor",
        "calendar_entity", "workday_sensor",
    ])
    def test_every_source_reports_back(self, entity_input):
        """Condition-only sources (brightness, sun, forecast, calendar, workday) never
        block a run, but their return is what makes a missed shading re-evaluable."""
        assert any(t.get("entity_id") == entity_input for t in self._recovery()), entity_input

    def test_recovery_triggers_fire_on_recovery_only(self):
        for t in self._recovery():
            if t["trigger"] != "state":
                continue
            assert t["from"] == ["unavailable", "unknown"]
            assert t["not_to"] == ["unavailable", "unknown"]
            assert t["for"] == {"seconds": 30}

    def test_queue_survives_one_run_per_recovering_source(self):
        assert BP["max"] >= len(self._recovery())

    def _forecast_gate(self) -> list[str]:
        """The conditions of the `weather.get_forecasts` step in the actions."""
        for step in BP["actions"]:
            if not isinstance(step, dict) or "if" not in step:
                continue
            if any(str(a.get("action")) == "weather.get_forecasts"
                   for a in step.get("then", []) if isinstance(a, dict)):
                return [c for c in step["if"] if isinstance(c, str)]
        raise AssertionError("no weather.get_forecasts step found")

    def test_forecast_is_loaded_for_the_recovery(self):
        """Without it shading_start_warranted is false whenever a forecast condition
        is configured, and the recovery would never re-arm shading (Bug Pattern T)."""
        gate = next(c for c in self._forecast_gate() if "regex_match" in c)
        assert _render_bool(gate, {}, trigger=types.SimpleNamespace(id="t_recovery"),
                            automation_resumed=False) is True

    @pytest.mark.parametrize("tid", ["t_close_1", "t_resident_update", "t_contact_tilted_changed"])
    def test_forecast_is_loaded_on_a_resumed_run_claimed_by_any_trigger(self, tid):
        """The resumed-run backstop turns ANY trigger into a recovery, and that run evaluates
        shading_start_warranted for recovered_pending. Gating the forecast load on trigger ids
        alone left it unloaded there: forecast_temp_valid / forecast_weather_valid render false
        whenever the user configured those conditions, so the recovery refuses a shading the
        conditions actually warrant - and the helper write clears automation_resumed, so the
        miss is permanent for that day (the shading triggers latched during the off-period).
        Bug Pattern T, one trigger-id set further out."""
        gate = next(c for c in self._forecast_gate() if "regex_match" in c)
        assert _render_bool(gate, {}, trigger=types.SimpleNamespace(id=tid),
                            automation_resumed=False) is False, "premise: not an opening trigger"
        assert _render_bool(gate, {}, trigger=types.SimpleNamespace(id=tid),
                            automation_resumed=True) is True

    def _resume_trigger(self) -> dict:
        return next(t for t in self._recovery()
                    if t["trigger"] == "template" and "this.last_changed" in t["value_template"])

    FORCE_ENTITIES = ["auto_up_force", "auto_down_force",
                      "auto_shading_start_force", "auto_ventilate_force"]

    def _ungated(self) -> list[dict]:
        return [self._resume_trigger()] + [
            t for t in self._recovery() if t.get("entity_id") in self.FORCE_ENTITIES]

    def test_recovery_is_opt_in_and_defaults_to_off(self):
        """Users must explicitly opt in to cover movements after a restart. A source recovery
        trigger that exists to CATCH UP is gated at the trigger (no run, no trace, no drive
        while disabled - same rationale as the #550 trigger-level filtering)."""
        ungated = self._ungated()
        for t in self._recovery():
            if any(t is u for u in ungated):
                continue
            assert "is_recovery_enabled" in t.get("enabled", ""), t
        section = BP["blueprint"]["input"]["feature_section"]["input"]
        assert section["enable_recovery"]["default"] is False

    def test_the_resume_trigger_is_deliberately_not_gated(self):
        """The first exception, and the reason for the cause-vs-prevent rule. A resumed
        automation holds a helper that may be days old; acting on it drives the cover WRONGLY
        (a shading from an earlier day still reads as active, an override reset that came due
        while the automation was off can never fire again). The run it starts only cleans the
        helper and stops - will_drive gates the movement - so it prevents a wrong movement
        rather than causing one, which is not what the opt-in guards against."""
        assert "is_recovery_enabled" not in self._resume_trigger().get("enabled", "")

    @pytest.mark.parametrize("entity_input", FORCE_ENTITIES)
    def test_the_force_entity_triggers_are_not_gated_either(self, entity_input):
        """Same rule, second application. frc is a PERSISTED field that effective_state reads,
        so a stale frc does not merely miss an event - it holds the whole cascade in the force
        state and produces wrong movements on every later trigger. The force's own trigger uses
        from: "on", so unavailable -> off never fires it, and live_force deliberately keeps
        reading the recorded force as active while its entity is unreadable. Without this
        trigger the force would stay recorded indefinitely with the opt-in off."""
        t = next(t for t in self._recovery() if t.get("entity_id") == entity_input)
        assert "is_recovery_enabled" not in t.get("enabled", "")
        assert entity_input in t["enabled"], "still gated on the input being configured"

    def test_the_force_pause_trigger_stays_gated(self):
        """The counter-example that keeps the rule honest: is_paused is read live from the
        entity and nothing about the pause is persisted, so its return leaves no stale claim
        to correct. All a recovery run could do is drive the cover back into the force position
        the pause suspended - a catch-up, which is what the opt-in buys."""
        t = next(t for t in self._recovery() if t.get("entity_id") == "force_pause")
        assert "is_recovery_enabled" in t.get("enabled", "")

    def test_the_opt_in_gates_the_drive_not_the_hygiene(self):
        """The switch buys exactly one thing: permission to MOVE the cover."""
        assert "is_recovery_enabled" in _branch_var(RECOVERY, "will_drive")
        assert _branch_var(RECOVERY, "drive_plan")["run"] == "{{ will_drive }}"
        # ... and the helper clean-up must not depend on it (Invariant 7 keeps man tied
        # to the actual drive, so it may reference will_drive).
        uv = _recovery_update_values()
        for key in ("win", "res", "frc", "shd", "pnd"):
            assert "is_recovery_enabled" not in str(uv[key]), key
            assert "will_drive" not in str(uv[key]), key

    def test_catching_up_the_base_state_needs_the_opt_in(self):
        """Writing bas: 'cls' for a closing the outage swallowed is a deferred movement:
        a later branch would drive the cover into it. So the WRITE is opt-in, even though
        it does not drive here."""
        tpl = _branch_var(RECOVERY, "new_base")
        assert _render(tpl, {}, is_recovery_enabled=True,
                       recovered_base="cls", helper_state_base="opn") == "cls"
        assert _render(tpl, {}, is_recovery_enabled=False,
                       recovered_base="cls", helper_state_base="opn") == "opn"
        assert _recovery_update_values()["bas"] == "{{ new_base }}"

    def test_recovery_flag_is_a_static_trigger_variable(self):
        """`enabled:` is evaluated in the limited trigger context (Invariant 10) -
        the flag must be a plain !input, not a template calling states()."""
        assert "is_recovery_enabled" in BP["trigger_variables"]
        assert "states(" not in str(BP["trigger_variables"]["is_recovery_enabled"])


# ════════════════════════════════════════════════════════════════════════════
# Invariant 13: the top-level choose is a trigger.id dispatcher
# ════════════════════════════════════════════════════════════════════════════
class TestBranchDispatch:
    """Branch order only matters where two branches accept the SAME trigger id. That
    is true for exactly three ids, all deliberate fallbacks (earlier branch wins):

      t_open_1               -> Opening, falling back to Shading start
      t_calendar_event_start -> Opening, falling back to Closing (phase decides)
      t_calendar_event_end   -> ditto

    Everywhere else exactly one branch matches, so its position in the choose is
    irrelevant. Freezing that set here means an accidentally widened gate regex
    fails the suite instead of silently letting an earlier branch swallow a trigger.
    """

    EXPECTED_OVERLAPS = {"t_open_1", "t_calendar_event_start", "t_calendar_event_end"}

    def _matching_branches(self, trigger_id: str) -> list[str]:
        trigger = types.SimpleNamespace(id=trigger_id)
        hits = []
        for b in [_branch(RECOVERY)] + _top_level_branches():
            entry = b.get("conditions") or b.get("if") or []
            gates = [c for c in entry if isinstance(c, str) and "trigger.id" in c]
            if gates and all(_render_bool(g, {}, strict=False, trigger=trigger) for g in gates):
                hits.append(b.get("alias", "?"))
        return hits

    def _trigger_ids(self) -> set[str]:
        return {t["id"] for t in BP["triggers"] if t.get("id")}

    def test_every_trigger_reaches_exactly_one_branch_except_the_known_fallbacks(self):
        overlaps, orphans = set(), set()
        for tid in self._trigger_ids():
            hits = self._matching_branches(tid)
            if len(hits) > 1:
                overlaps.add(tid)
            elif not hits:
                orphans.add(tid)
        assert not orphans, f"triggers that reach no branch: {orphans}"
        assert overlaps == self.EXPECTED_OVERLAPS, (
            f"branch dispatch changed: {overlaps ^ self.EXPECTED_OVERLAPS}. A new overlap "
            f"means an earlier branch now swallows a trigger - order became load-bearing."
        )

    def test_recovery_is_reached_by_exactly_one_branch(self):
        """t_recovery is claimed by the pre-dispatch gate and by no dispatch branch."""
        hits = self._matching_branches("t_recovery")
        assert len(hits) == 1, hits
        assert hits[0].startswith(RECOVERY)

    def test_known_fallbacks_keep_their_order(self):
        """t_open_1 must hit Opening BEFORE Shading start; a calendar event must hit
        Opening before Closing. Reordering the branches would invert the fallback."""
        aliases = [b.get("alias", "") for b in _top_level_branches()]
        order = {a: i for i, a in enumerate(aliases)}
        assert order["Check for opening"] < order["Check for shading start"]
        assert order["Check for opening"] < order["Check for closing cover"]
