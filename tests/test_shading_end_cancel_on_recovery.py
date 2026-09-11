"""
Issue #696: the shading-end waiting time must be canceled when an end condition
recovers before the waiting time has elapsed.

Before the fix, the end conditions were only *sampled* — at the first drop
(arming the end pending) and when the pending expired (plus every retry). The
#554 cancel branch only fires on a start-pending edge with the START conditions
met (brightness above the *start* value), so brightness recovering to anywhere
between the end and the start value never canceled anything and the shading
ended after the first sample that happened to land on a cloud.

Every end-pending trigger now has a mirrored `t_shading_end_cancel_N` trigger
that fires when the condition is valid again (nominal threshold), enters the end
handler through its `^(t_shading_end)` prefix and lands in the `else` of
`shading_end_conditions_met`, where the pending is cleared. The next drop is a
fresh false -> true edge of the end-pending trigger and restarts the wait.

Run with: pytest tests/ -v
"""
import pathlib
import re

import jinja2
import pytest
import yaml


BLUEPRINT_PATH = (
    pathlib.Path(__file__).parent.parent
    / "blueprints"
    / "automation"
    / "cover_control_automation.yaml"
)

CANCEL_ALIAS = "Shading end conditions recovered. Cancel pending shading end"
STALE_ALIAS = "Shading end execution: clear stale pending"
ARM_ALIAS = "Shading end detected. Save next execution time and pending status"

# Same numbering as the end-pending triggers.
CANCEL_IDS = [f"t_shading_end_cancel_{n}" for n in range(1, 9)]
PENDING_IDS = [f"t_shading_end_pending_{n}" for n in range(1, 9)]

INVALID_STATES = ["", "unavailable", "unknown", "none", "None"]

HELPER_END_PENDING = (
    '{"bas":"opn","shd":1,"pnd":"end","win":"cls","frc":"non","res":1,"man":0,'
    '"ts":{"opn":0,"cls":0,"shd":1779701945,"due":1779705000,"arm":1779701945,"man":0},"v":6,"t":0}'
)
HELPER_SHADED_NO_PENDING = (
    '{"bas":"opn","shd":1,"pnd":"non","win":"cls","frc":"non","res":1,"man":0,'
    '"ts":{"opn":0,"cls":0,"shd":1779701945,"due":0,"arm":0,"man":0},"v":6,"t":0}'
)
HELPER_START_PENDING = (
    '{"bas":"opn","shd":0,"pnd":"beg","win":"cls","frc":"non","res":1,"man":0,'
    '"ts":{"opn":0,"cls":0,"shd":1779701945,"due":1779705000,"arm":1779701945,"man":0},"v":6,"t":0}'
)


def _load_blueprint_yaml() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


@pytest.fixture(scope="module")
def blueprint() -> dict:
    return _load_blueprint_yaml()


def _find_branch_by_alias(node, alias: str):
    if isinstance(node, dict):
        if node.get("alias") == alias:
            return node
        for v in node.values():
            found = _find_branch_by_alias(v, alias)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_branch_by_alias(item, alias)
            if found is not None:
                return found
    return None


def _trigger(blueprint: dict, trigger_id: str) -> dict:
    for trig in blueprint["triggers"]:
        if trig.get("id") == trigger_id:
            return trig
    raise AssertionError(f"trigger {trigger_id!r} not found")


def _branch_update_values(branch: dict) -> dict:
    for step in branch["sequence"]:
        if isinstance(step, dict) and "variables" in step and "update_values" in step["variables"]:
            return step["variables"]["update_values"]
    raise AssertionError("update_values not found in branch")


# ─────────────────────────────────────────────────────────────────────────────
# Trigger shape
# ─────────────────────────────────────────────────────────────────────────────


class TestCancelTriggersMirrorTheEndPendingTriggers:
    @pytest.mark.parametrize("cancel_id, pending_id", zip(CANCEL_IDS, PENDING_IDS))
    def test_every_end_pending_trigger_has_a_cancel_twin(self, blueprint, cancel_id, pending_id):
        cancel = _trigger(blueprint, cancel_id)
        pending = _trigger(blueprint, pending_id)
        assert cancel["trigger"] == "template"
        # Same enablement: the twin watches the same sensor under the same option.
        assert cancel["enabled"] == pending["enabled"], (
            f"{cancel_id} must be enabled exactly when {pending_id} is"
        )

    @pytest.mark.parametrize("cancel_id", CANCEL_IDS)
    def test_cancel_ids_enter_the_end_handler_but_not_the_pending_or_execution_paths(self, cancel_id):
        # The end handler is entered by prefix; the arm and execution branches
        # match narrower prefixes that a cancel id must not satisfy.
        assert re.match(r"^(t_shading_end)", cancel_id)
        assert not re.match(r"^(t_shading_end_pending)", cancel_id)
        assert not re.match(r"^(t_shading_end_execution)", cancel_id)
        assert not re.match(r"^t_shading_end_pending_[1-8]$", cancel_id)

    def test_cancel_triggers_are_covered_by_the_forecast_and_calendar_load_gates(self):
        # The cancel branch re-evaluates shading_end_conditions_met, so a forecast
        # end condition needs fresh data on these triggers (Bug Pattern T family).
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        m = re.search(r"regex_match\('(\^\(t_shading_start\|[^']*)'\)", text)
        assert m, "forecast-load gate regex not found"
        for cancel_id in CANCEL_IDS:
            assert re.match(m.group(1), cancel_id)
        assert "regex_match('^t_shading_end')" in text, "calendar load gate prefix missing"


class TestCancelTriggerThresholds:
    """The cancel edge is the *nominal* threshold; the arm edge stays at
    threshold - hysteresis. The band in between is the anti-flap dead band."""

    def _render(self, blueprint, trigger_id, state, **variables):
        trig = _trigger(blueprint, trigger_id)
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        env.globals["states"] = lambda entity_id: state
        env.globals["state_attr"] = lambda entity_id, attr: state
        env.filters["float"] = _ha_float
        rendered = env.from_string(trig["value_template"]).render(
            invalid_states=INVALID_STATES, **variables
        ).strip()
        assert rendered in ("True", "False"), rendered
        return rendered == "True"

    def test_brightness_cancels_at_the_end_value_not_at_the_start_value(self, blueprint):
        vars_ = dict(shading_brightness_sensor="sensor.lux", shading_sun_brightness_end=25000,
                     shading_sun_brightness_hysteresis=2000)
        assert self._render(blueprint, "t_shading_end_cancel_3", "25000", **vars_) is True
        assert self._render(blueprint, "t_shading_end_cancel_3", "30000", **vars_) is True
        # Inside the dead band [end - h, end): neither arm nor cancel.
        assert self._render(blueprint, "t_shading_end_cancel_3", "24000", **vars_) is False
        assert self._render(blueprint, "t_shading_end_cancel_3", "22000", **vars_) is False
        assert self._render(blueprint, "t_shading_end_cancel_3", "unavailable", **vars_) is False

    def test_brightness_arm_and_cancel_edges_do_not_overlap(self, blueprint):
        vars_ = dict(shading_brightness_sensor="sensor.lux", shading_sun_brightness_end=25000,
                     shading_sun_brightness_hysteresis=2000)
        for value in ("22999", "24000", "24999", "25000", "27000"):
            arm = self._render(blueprint, "t_shading_end_pending_3", value, **vars_)
            cancel = self._render(blueprint, "t_shading_end_cancel_3", value, **vars_)
            assert not (arm and cancel), f"arm and cancel both true at {value}"

    def test_temperature_cancels_at_the_threshold(self, blueprint):
        vars_ = dict(shading_temperatur_sensor1="sensor.t1", shading_min_temperatur1=25,
                     shading_temperature_hysteresis1=2)
        assert self._render(blueprint, "t_shading_end_cancel_1", "25", **vars_) is True
        assert self._render(blueprint, "t_shading_end_cancel_1", "24", **vars_) is False
        assert self._render(blueprint, "t_shading_end_cancel_1", "unknown", **vars_) is False
        vars2 = dict(shading_temperatur_sensor2="sensor.t2", shading_min_temperatur2=25,
                     shading_temperature_hysteresis2=2)
        assert self._render(blueprint, "t_shading_end_cancel_2", "25.5", **vars2) is True
        assert self._render(blueprint, "t_shading_end_cancel_2", "20", **vars2) is False

    def test_sun_back_in_range(self, blueprint):
        vars_ = dict(default_sun_sensor="sun.sun", shading_azimuth_start=100, shading_azimuth_end=250,
                     shading_elevation_min=10, shading_elevation_max=60)
        assert self._render(blueprint, "t_shading_end_cancel_5", "150", **vars_) is True
        assert self._render(blueprint, "t_shading_end_cancel_5", "90", **vars_) is False
        assert self._render(blueprint, "t_shading_end_cancel_5", "260", **vars_) is False
        assert self._render(blueprint, "t_shading_end_cancel_5", None, **vars_) is False
        assert self._render(blueprint, "t_shading_end_cancel_7", "30", **vars_) is True
        assert self._render(blueprint, "t_shading_end_cancel_7", "5", **vars_) is False
        assert self._render(blueprint, "t_shading_end_cancel_7", "70", **vars_) is False
        assert self._render(blueprint, "t_shading_end_cancel_7", None, **vars_) is False

    def test_weather_forecast_temp_and_custom_sensor(self, blueprint):
        assert self._render(blueprint, "t_shading_end_cancel_4", "sunny",
                            shading_forecast_sensor="weather.home",
                            shading_weather_conditions=["sunny", "partlycloudy"]) is True
        assert self._render(blueprint, "t_shading_end_cancel_4", "rainy",
                            shading_forecast_sensor="weather.home",
                            shading_weather_conditions=["sunny", "partlycloudy"]) is False
        vars_ = dict(shading_forecast_temp_sensor="sensor.fc", shading_forecast_temp=28,
                     shading_forecast_temp_hysteresis=1)
        assert self._render(blueprint, "t_shading_end_cancel_6", "28", **vars_) is True
        assert self._render(blueprint, "t_shading_end_cancel_6", "27.5", **vars_) is False
        assert self._render(blueprint, "t_shading_end_cancel_8", "on",
                            shading_custom_sensor="binary_sensor.c") is True
        assert self._render(blueprint, "t_shading_end_cancel_8", "off",
                            shading_custom_sensor="binary_sensor.c") is False
        assert self._render(blueprint, "t_shading_end_cancel_8", "unavailable",
                            shading_custom_sensor="binary_sensor.c") is False


def _ha_float(value, default=None):
    """Mirror HA's `float` filter with a default."""
    try:
        return float(value)
    except (TypeError, ValueError):
        if default is None:
            raise
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Global gate
# ─────────────────────────────────────────────────────────────────────────────


def _global_trigger_gate_template(blueprint: dict) -> str:
    for cond in blueprint.get("conditions") or []:
        if isinstance(cond, dict) and cond.get("condition") == "template":
            vt = str(cond.get("value_template", ""))
            if "t_shading_start_pending" in vt:
                return vt
    raise AssertionError("global trigger gate template not found")


class TestGlobalGateAdmitsCancelOnlyWhileEndPending:
    def _gate(self, blueprint, trigger_id, helper_json):
        template = _global_trigger_gate_template(blueprint)
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        env.tests["match"] = lambda value, pattern: bool(re.match(pattern, str(value)))
        env.filters["regex_search"] = lambda value, pattern: bool(re.search(pattern, str(value)))
        env.globals["states"] = lambda entity_id: helper_json
        rendered = env.from_string(template).render(
            trigger={"id": trigger_id},
            cover_status_helper="input_text.cca_helper",
            invalid_states=INVALID_STATES,
        ).strip()
        assert rendered in ("True", "False", "true", "false"), rendered
        return rendered in ("True", "true")

    @pytest.mark.parametrize("cancel_id", CANCEL_IDS)
    def test_passes_while_an_end_pending_is_armed(self, blueprint, cancel_id):
        assert self._gate(blueprint, cancel_id, HELPER_END_PENDING) is True

    @pytest.mark.parametrize("cancel_id", CANCEL_IDS)
    def test_blocked_without_an_end_pending(self, blueprint, cancel_id):
        # A recovered condition while simply shaded (or start-pending) has nothing
        # to cancel — the run is cheap noise and must not reach the actions.
        assert self._gate(blueprint, cancel_id, HELPER_SHADED_NO_PENDING) is False
        assert self._gate(blueprint, cancel_id, HELPER_START_PENDING) is False

    def test_end_pending_triggers_keep_their_own_gate(self, blueprint):
        # Unchanged: arming needs shd == 1, not pnd == 'end'.
        assert self._gate(blueprint, "t_shading_end_pending_3", HELPER_SHADED_NO_PENDING) is True


# ─────────────────────────────────────────────────────────────────────────────
# The cancel branch
# ─────────────────────────────────────────────────────────────────────────────


class TestCancelBranch:
    @pytest.fixture
    def branch(self, blueprint):
        b = _find_branch_by_alias(blueprint, CANCEL_ALIAS)
        assert b is not None, f"branch not found: {CANCEL_ALIAS!r}"
        return b

    @pytest.fixture
    def end_handler(self, blueprint):
        b = _find_branch_by_alias(blueprint, "Check for shading end")
        assert b is not None
        return b

    def test_branch_is_gated_on_cancel_trigger_and_end_pending(self, branch):
        flat = " ".join(str(c) for c in branch["conditions"])
        assert "t_shading_end_cancel" in flat
        assert "helper_state_pending_end" in flat

    def test_branch_lives_in_the_conditions_not_met_path(self, end_handler):
        # The branch must sit in the else of `shading_end_conditions_met`: a
        # recovered condition may still leave the combined end result met (OR
        # group with another invalid condition) — then the pending must survive.
        if_step = next(s for s in end_handler["sequence"] if isinstance(s, dict) and "if" in s)
        assert "shading_end_conditions_met" in " ".join(str(c) for c in if_step["if"])
        assert _find_branch_by_alias(if_step["else"], CANCEL_ALIAS) is not None
        assert _find_branch_by_alias(if_step["then"], CANCEL_ALIAS) is None
        # The pre-existing stale-pending clear (#395) stays next to it.
        assert _find_branch_by_alias(if_step["else"], STALE_ALIAS) is not None

    def test_cancel_is_a_terminal_pending_state(self, branch):
        uv = _branch_update_values(branch)
        assert uv.get("pnd") == "non"
        assert uv.get("ts", {}).get("due") == 0
        assert uv.get("ts", {}).get("arm") == 0

    def test_cancel_keeps_shading_and_does_not_touch_manual_or_ts_shd(self, branch):
        # No drive happens: man must not be cleared (Invariant 7), shd stays 1 and
        # ts.shd is not restamped (no real shd 0<->1 change, Invariant 8).
        uv = _branch_update_values(branch)
        assert uv.get("shd", 1) == 1
        assert "man" not in uv
        assert "shd" not in (uv.get("ts") or {})
        for step in branch["sequence"]:
            if isinstance(step, dict) and isinstance(step.get("variables"), dict):
                assert "drive_plan" not in step["variables"], "cancel must not plan a drive"

    def test_cancel_ends_in_apply_transition_and_stops(self, branch):
        assert "input_text.set_value" in str(branch["sequence"])
        assert any(isinstance(s, dict) and "stop" in s for s in branch["sequence"])

    def test_arm_branch_still_requires_an_end_pending_trigger(self, blueprint):
        # A cancel id must never arm a pending (it is in the same handler).
        arm = _find_branch_by_alias(blueprint, ARM_ALIAS)
        flat = " ".join(str(c) for c in arm["conditions"])
        assert "^(t_shading_end_pending)" in flat


class TestScenario696:
    """Brightness drops (arm), sun returns to between end and start value
    (cancel), brightness drops again (fresh arm): the wait restarts."""

    def _edge(self, blueprint, trigger_id, value, **vars_):
        trig = _trigger(blueprint, trigger_id)
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        env.globals["states"] = lambda entity_id: value
        env.filters["float"] = _ha_float
        return env.from_string(trig["value_template"]).render(
            invalid_states=INVALID_STATES, **vars_).strip() == "True"

    def test_sequence(self, blueprint):
        vars_ = dict(shading_brightness_sensor="sensor.lux",
                     shading_sun_brightness_start=35000, shading_sun_brightness_end=25000,
                     shading_sun_brightness_hysteresis=0)
        timeline = ["40000", "20000", "30000", "20000"]
        arm = [self._edge(blueprint, "t_shading_end_pending_3", v, **vars_) for v in timeline]
        cancel = [self._edge(blueprint, "t_shading_end_cancel_3", v, **vars_) for v in timeline]
        start = [self._edge(blueprint, "t_shading_start_pending_2", v, **vars_) for v in timeline]
        # 20000: arm edge; 30000: cancel edge but NO start edge (that is the gap
        # #554 left open); 20000 again: a fresh arm edge.
        assert arm == [False, True, False, True]
        assert cancel == [True, False, True, False]
        assert start == [True, False, False, False]
