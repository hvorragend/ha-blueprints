"""
Tests for the independent shading hold (#605).

Option `shading_independent_holds_end` (in `shading_config`): while the
independent temperature threshold is (still) exceeded, an active shading must
not end during the day. The single source of truth is the variable
`independent_shading_holds`, consumed at exactly one choke point inside
`shading_end_conditions_met`.

All templates are extracted verbatim from the blueprint so the tests exercise
the real code, not a copy.
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

INVALID_STATES = ["", "unavailable", "unknown", "none", "None", "null", "query failed", []]


def _load_blueprint() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


BP = _load_blueprint()


def _action_var(name: str) -> str:
    for step in BP["actions"]:
        if isinstance(step, dict) and name in step.get("variables", {}):
            return step["variables"][name]
    raise AssertionError(f"action-level variable {name!r} not found")


HOLDS_TEMPLATE = _action_var("independent_shading_holds")
END_MET_TEMPLATE = _action_var("shading_end_conditions_met")


def _env(entity_states: dict | None = None) -> jinja2.Environment:
    entity_states = entity_states or {}

    def states(entity_id):
        if isinstance(entity_id, list):
            return "unknown"
        return entity_states.get(entity_id, "unknown")

    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.globals["states"] = states
    return env


def _render_bool(template_str: str, entity_states: dict | None = None, **variables) -> bool:
    out = _env(entity_states).from_string(template_str).render(**variables).strip()
    if out == "True":
        return True
    if out == "False":
        return False
    return bool(out)  # non-empty string is truthy - exactly the HA literal_eval trap


BASE_VARS = {
    "shading_config": ["shading_temp_comparison_independent", "shading_independent_holds_end"],
    "shading_independent_temp": 25,
    "shading_forecast_temp_hysteresis": 0.5,
    "forecast_temp_raw": None,
    "shading_temperatur_sensor2": [],
    "invalid_states": INVALID_STATES,
}


def _holds(**overrides) -> bool:
    entity_states = overrides.pop("entity_states", None)
    return _render_bool(HOLDS_TEMPLATE, entity_states, **{**BASE_VARS, **overrides})


class TestIndependentShadingHolds:
    def test_holds_while_forecast_above_threshold(self):
        assert _holds(forecast_temp_raw=30) is True

    def test_holds_inside_the_low_side_hysteresis_band(self):
        # Start requires > threshold + hysteresis; the hold keeps going down to
        # threshold - hysteresis so it does not flap around the threshold.
        assert _holds(forecast_temp_raw=24.8) is True

    def test_released_below_threshold_minus_hysteresis(self):
        assert _holds(forecast_temp_raw=24.4) is False

    def test_requires_the_hold_option(self):
        assert _holds(
            forecast_temp_raw=30,
            shading_config=["shading_temp_comparison_independent"],
        ) is False

    def test_requires_the_independent_mode(self):
        assert _holds(
            forecast_temp_raw=30,
            shading_config=["shading_independent_holds_end"],
        ) is False

    def test_no_hold_without_any_temperature_source(self):
        assert _holds(forecast_temp_raw=None) is False

    def test_sensor2_holds_when_compare_option_enabled(self):
        assert _holds(
            forecast_temp_raw=None,
            shading_config=BASE_VARS["shading_config"] + ["shading_compare_forecast_with_sensor2"],
            shading_temperatur_sensor2="sensor.temp2",
            entity_states={"sensor.temp2": "31.0"},
        ) is True

    def test_sensor2_ignored_without_compare_option(self):
        assert _holds(
            forecast_temp_raw=None,
            shading_temperatur_sensor2="sensor.temp2",
            entity_states={"sensor.temp2": "31.0"},
        ) is False

    def test_unavailable_sensor2_does_not_hold(self):
        assert _holds(
            forecast_temp_raw=None,
            shading_config=BASE_VARS["shading_config"] + ["shading_compare_forecast_with_sensor2"],
            shading_temperatur_sensor2="sensor.temp2",
            entity_states={"sensor.temp2": "unavailable"},
        ) is False


class TestEndConditionsChokePoint:
    def _end_met(self, holds: bool) -> bool:
        return _render_bool(
            END_MET_TEMPLATE,
            is_shading_enabled=True,
            independent_shading_holds=holds,
            shading_end_and_result=True,
            shading_end_or_result=True,
        )

    def test_hold_blocks_the_end_even_when_all_end_conditions_are_met(self):
        assert self._end_met(holds=True) is False

    def test_end_conditions_apply_normally_without_the_hold(self):
        assert self._end_met(holds=False) is True

    def test_end_met_references_the_hold_variable(self):
        # The hold must stay a single choke point inside shading_end_conditions_met -
        # do not move it into individual end branches.
        assert "independent_shading_holds" in END_MET_TEMPLATE


class TestForecastLoadGate:
    def test_forecast_gate_covers_shading_end_triggers(self):
        """Bug Pattern T family: without forecast data on end triggers,
        forecast_temp_raw is None and the hold's forecast branch never applies."""
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        m = re.search(r"regex_match\('(\^\(t_shading_start\|[^']*)'\)", text)
        assert m, "forecast-load gate regex not found"
        pattern = m.group(1)
        for trigger_id in [
            "t_shading_end_pending_5",
            "t_shading_end_execution",
            "t_shading_start_pending_1",
            "t_shading_start_execution",
            "t_open_1",
            "t_calendar_event_start",
            "t_recovery",
        ]:
            assert re.match(pattern, trigger_id), f"{trigger_id} not covered by {pattern}"

    def test_selector_offers_the_hold_option(self):
        options = (
            BP["blueprint"]["input"]["shading_section"]["input"]["shading_config"]
            ["selector"]["select"]["options"]
        )
        values = [o["value"] for o in options]
        assert "shading_independent_holds_end" in values
