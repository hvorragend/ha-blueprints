"""
Tests for restart/outage handling: the availability gates and the recovery branch.

Two halves that only work together:

  1. The GATE (global conditions) stops a run while a state-critical entity has no
     usable state, so no wrong status can be persisted.
  2. The RECOVERY (t_recovery -> BRANCH 12) replays what the outage swallowed:
     time/calendar triggers of that period never fire again, and template/numeric
     triggers only fire on a false->true transition, which is consumed while the
     run is blocked.

The dangerous part of a gate is what it ORPHANS. Three cases needed an exception
and each has a test here:

  * contact triggers    -> gate exemption   (else the gate blocks the very event
                           that would clear `win`, deadlocking itself)
  * helper `unknown`    -> gate blocks on `unavailable` only (else the init/repair
                           step is unreachable and the automation is dead forever)
  * override reset      -> re-evaluated in BRANCH 12 (`override_expired`), because
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


def _env(entity_states: dict | None = None) -> jinja2.Environment:
    """Jinja env with the HA globals/filters the blueprint templates use."""
    entity_states = entity_states or {}

    def states(entity_id):
        if isinstance(entity_id, list):  # unconfigured input -> []
            return "unknown"
        return entity_states.get(entity_id, "unknown")

    def today_at(value="00:00:00"):
        hh, mm, ss = (list(map(int, str(value).split(":"))) + [0, 0])[:3]
        return NOW.replace(hour=hh, minute=mm, second=ss, microsecond=0)

    def timestamp_custom(ts, fmt="%Y-%m-%d", local=True):
        return datetime.datetime.fromtimestamp(float(ts)).strftime(fmt)

    env = jinja2.Environment(undefined=jinja2.Undefined)
    env.globals["states"] = states
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


def _render(template_str: str, entity_states: dict | None = None, **variables) -> str:
    return _env(entity_states).from_string(template_str).render(**variables).strip()


def _render_bool(template_str: str, entity_states: dict | None = None, **variables) -> bool:
    """Render and parse like HA does (literal_eval); a bare 'false' would be TRUTHY."""
    out = _render(template_str, entity_states, **variables)
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
    for b in _top_level_branches():
        if b.get("alias", "").startswith(alias_prefix):
            return b
    raise AssertionError(f"branch {alias_prefix!r} not found")


def _branch_var(alias_prefix: str, name: str) -> str:
    """Pull one variable template out of a branch's sequence."""
    for step in _branch(alias_prefix)["sequence"]:
        if isinstance(step, dict) and name in step.get("variables", {}):
            return step["variables"][name]
    raise AssertionError(f"variable {name!r} not found in branch {alias_prefix!r}")


RECOVERY = "Recovery after restart or outage"


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

    def test_recovery_branch_lifts_its_skip_for_an_expired_override(self):
        """BRANCH 12 skips on man==1 - so without this the expired override could
        never be cleared by the recovery either (double lock)."""
        gates = [c for c in _branch(RECOVERY)["conditions"] if "helper_state_manual" in str(c)]
        assert gates and "override_expired" in gates[0]

    def test_recovery_clears_man_when_expired(self):
        for step in _branch(RECOVERY)["sequence"]:
            uv = step.get("variables", {}).get("update_values") if isinstance(step, dict) else None
            if uv and "man" in uv:
                assert "override_expired" in uv["man"]
                return
        raise AssertionError("recovery branch does not write man")


# ════════════════════════════════════════════════════════════════════════════
# BRANCH 12: base state re-derived from the schedule
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
# BRANCH 12: recovered_state must stay in sync with effective_state
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
            helper_state_shade=(shd == 1),
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

    def test_forecast_is_loaded_for_the_recovery(self):
        """Without it shading_start_warranted is false whenever a forecast condition
        is configured, and the recovery would never re-arm shading (Bug Pattern T)."""
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        gate = [ln for ln in text.splitlines() if "t_calendar_event_start|t_recovery" in ln]
        assert gate, "t_recovery missing from the weather.get_forecasts gate"


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
        for b in _top_level_branches():
            gates = [c for c in b.get("conditions", []) if isinstance(c, str) and "trigger.id" in c]
            if gates and all(_render_bool(g, {}, trigger=trigger) for g in gates):
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
        """Hence the position of the recovery branch in the choose is irrelevant."""
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
