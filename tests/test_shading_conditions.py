"""
Unit tests for the shading condition result variables:
  - shading_start_and_result
  - shading_start_or_result
  - shading_end_and_result
  - shading_end_or_result

Verify that ONLY user-selected conditions are evaluated, and that AND/OR
logic respects sensor availability (configured vs. empty input).

The condition templates are extracted verbatim from
blueprints/automation/cover_control_automation.yaml.
"""
import pytest
from conftest import make_jinja_env, eval_condition


START_AND_RESULT = """
(
  ('cond_azimuth' not in shading_conditions_start_and or
  default_sun_sensor == [] or
  shading_start_condition_states.azimuth_valid)
  and
  ('cond_elevation' not in shading_conditions_start_and or
  default_sun_sensor == [] or
  shading_start_condition_states.elevation_valid)
  and
  ('cond_brightness' not in shading_conditions_start_and or
  shading_brightness_sensor == [] or
  shading_start_condition_states.brightness_valid)
  and
  ('cond_temp1' not in shading_conditions_start_and or
  shading_temperatur_sensor1 == [] or
  shading_start_condition_states.temp1_valid)
  and
  ('cond_temp2' not in shading_conditions_start_and or
  shading_temperatur_sensor2 == [] or
  shading_start_condition_states.temp2_valid)
  and
  ('cond_forecast_temp' not in shading_conditions_start_and or
  shading_forecast_temp == [] or
  shading_start_condition_states.forecast_temp_valid)
  and
  ('cond_forecast_weather' not in shading_conditions_start_and or
  shading_weather_conditions == [] or
  shading_start_condition_states.forecast_weather_valid)
)
"""

START_OR_RESULT = """
(shading_conditions_start_or | count == 0) or
(
  ('cond_azimuth' in shading_conditions_start_or and
  default_sun_sensor != [] and
  shading_start_condition_states.azimuth_valid)
  or
  ('cond_elevation' in shading_conditions_start_or and
  default_sun_sensor != [] and
  shading_start_condition_states.elevation_valid)
  or
  ('cond_brightness' in shading_conditions_start_or and
  shading_brightness_sensor != [] and
  shading_start_condition_states.brightness_valid)
  or
  ('cond_temp1' in shading_conditions_start_or and
  shading_temperatur_sensor1 != [] and
  shading_start_condition_states.temp1_valid)
  or
  ('cond_temp2' in shading_conditions_start_or and
  shading_temperatur_sensor2 != [] and
  shading_start_condition_states.temp2_valid)
  or
  ('cond_forecast_temp' in shading_conditions_start_or and
  shading_forecast_temp != [] and
  shading_start_condition_states.forecast_temp_valid)
  or
  ('cond_forecast_weather' in shading_conditions_start_or and
  shading_weather_conditions != [] and
  shading_start_condition_states.forecast_weather_valid)
)
"""

END_AND_RESULT = """
shading_conditions_end_and | count > 0 and
(
  ('cond_azimuth' not in shading_conditions_end_and or
  default_sun_sensor == [] or
  shading_end_condition_states.azimuth_invalid)
  and
  ('cond_elevation' not in shading_conditions_end_and or
  default_sun_sensor == [] or
  shading_end_condition_states.elevation_invalid)
  and
  ('cond_brightness' not in shading_conditions_end_and or
  shading_brightness_sensor == [] or
  shading_end_condition_states.brightness_invalid)
  and
  ('cond_temp1' not in shading_conditions_end_and or
  shading_temperatur_sensor1 == [] or
  shading_end_condition_states.temp1_invalid)
  and
  ('cond_temp2' not in shading_conditions_end_and or
  shading_temperatur_sensor2 == [] or
  shading_end_condition_states.temp2_invalid)
  and
  ('cond_forecast_temp' not in shading_conditions_end_and or
  shading_forecast_temp == [] or
  shading_end_condition_states.forecast_temp_invalid)
  and
  ('cond_forecast_weather' not in shading_conditions_end_and or
  shading_weather_conditions == [] or
  shading_end_condition_states.forecast_weather_invalid)
)
"""

END_OR_RESULT = """
shading_conditions_end_or | count > 0 and
(
  ('cond_azimuth' in shading_conditions_end_or and
  shading_end_condition_states.azimuth_invalid)
  or
  ('cond_elevation' in shading_conditions_end_or and
  shading_end_condition_states.elevation_invalid)
  or
  ('cond_brightness' in shading_conditions_end_or and
  shading_end_condition_states.brightness_invalid)
  or
  ('cond_temp1' in shading_conditions_end_or and
  shading_end_condition_states.temp1_invalid)
  or
  ('cond_temp2' in shading_conditions_end_or and
  shading_end_condition_states.temp2_invalid)
  or
  ('cond_forecast_temp' in shading_conditions_end_or and
  shading_end_condition_states.forecast_temp_invalid)
  or
  ('cond_forecast_weather' in shading_conditions_end_or and
  shading_end_condition_states.forecast_weather_invalid)
)
"""


def base_vars(**overrides):
    """Default variable set: no sensors configured, no conditions selected, all *_valid/_invalid False."""
    v = {
        # User selections
        "shading_conditions_start_and": [],
        "shading_conditions_start_or": [],
        "shading_conditions_end_and": [],
        "shading_conditions_end_or": [],
        # Sensors (HA empty-input convention is [])
        "default_sun_sensor": [],
        "shading_brightness_sensor": [],
        "shading_temperatur_sensor1": [],
        "shading_temperatur_sensor2": [],
        "shading_forecast_temp": [],
        "shading_weather_conditions": [],
        # Per-condition state dicts
        "shading_start_condition_states": {
            "azimuth_valid": False,
            "elevation_valid": False,
            "brightness_valid": False,
            "temp1_valid": False,
            "temp2_valid": False,
            "forecast_temp_valid": False,
            "forecast_weather_valid": False,
        },
        "shading_end_condition_states": {
            "azimuth_invalid": False,
            "elevation_invalid": False,
            "brightness_invalid": False,
            "temp1_invalid": False,
            "temp2_invalid": False,
            "forecast_temp_invalid": False,
            "forecast_weather_invalid": False,
        },
    }
    v.update(overrides)
    return v


@pytest.fixture
def env():
    return make_jinja_env()


# ─────────────────────────────────────────────────────────────────────────────
# shading_start_and_result
# ─────────────────────────────────────────────────────────────────────────────

class TestStartAndResult:
    def test_no_conditions_selected_returns_true(self, env):
        """Empty start_and ⇒ all clauses pass via 'not in' ⇒ TRUE."""
        assert eval_condition(env, START_AND_RESULT, base_vars()) is True

    def test_unselected_condition_is_ignored(self, env):
        """cond_brightness invalid but not selected ⇒ TRUE."""
        v = base_vars(
            shading_conditions_start_and=["cond_temp1"],
            shading_temperatur_sensor1="sensor.t1",
            shading_brightness_sensor="sensor.b",
            shading_start_condition_states={
                "azimuth_valid": True, "elevation_valid": True,
                "brightness_valid": False,  # invalid but NOT selected
                "temp1_valid": True,
                "temp2_valid": True, "forecast_temp_valid": True, "forecast_weather_valid": True,
            },
        )
        assert eval_condition(env, START_AND_RESULT, v) is True

    def test_selected_condition_without_sensor_is_skipped(self, env):
        """cond_temp2 selected but no sensor ⇒ clause auto-passes ⇒ TRUE."""
        v = base_vars(
            shading_conditions_start_and=["cond_temp2"],
            shading_temperatur_sensor2=[],  # no sensor
        )
        assert eval_condition(env, START_AND_RESULT, v) is True

    def test_selected_condition_with_sensor_and_valid_returns_true(self, env):
        v = base_vars(
            shading_conditions_start_and=["cond_brightness"],
            shading_brightness_sensor="sensor.b",
            shading_start_condition_states={
                "azimuth_valid": False, "elevation_valid": False,
                "brightness_valid": True,
                "temp1_valid": False, "temp2_valid": False,
                "forecast_temp_valid": False, "forecast_weather_valid": False,
            },
        )
        assert eval_condition(env, START_AND_RESULT, v) is True

    def test_selected_condition_with_sensor_but_invalid_returns_false(self, env):
        v = base_vars(
            shading_conditions_start_and=["cond_brightness"],
            shading_brightness_sensor="sensor.b",
            # all *_valid stay False
        )
        assert eval_condition(env, START_AND_RESULT, v) is False

    def test_one_invalid_among_many_selected_returns_false(self, env):
        v = base_vars(
            shading_conditions_start_and=["cond_brightness", "cond_temp1"],
            shading_brightness_sensor="sensor.b",
            shading_temperatur_sensor1="sensor.t1",
            shading_start_condition_states={
                "azimuth_valid": True, "elevation_valid": True,
                "brightness_valid": True,
                "temp1_valid": False,  # one fails
                "temp2_valid": True, "forecast_temp_valid": True, "forecast_weather_valid": True,
            },
        )
        assert eval_condition(env, START_AND_RESULT, v) is False


# ─────────────────────────────────────────────────────────────────────────────
# shading_start_or_result
# ─────────────────────────────────────────────────────────────────────────────

class TestStartOrResult:
    def test_empty_or_returns_true(self, env):
        """Empty OR list means 'no OR requirement' ⇒ TRUE."""
        assert eval_condition(env, START_OR_RESULT, base_vars()) is True

    def test_one_selected_with_sensor_and_valid_returns_true(self, env):
        v = base_vars(
            shading_conditions_start_or=["cond_brightness"],
            shading_brightness_sensor="sensor.b",
            shading_start_condition_states={
                "azimuth_valid": False, "elevation_valid": False,
                "brightness_valid": True,
                "temp1_valid": False, "temp2_valid": False,
                "forecast_temp_valid": False, "forecast_weather_valid": False,
            },
        )
        assert eval_condition(env, START_OR_RESULT, v) is True

    def test_selected_without_sensor_clause_skipped(self, env):
        """cond_temp2 in OR without sensor ⇒ clause FALSE; another can still trigger."""
        v = base_vars(
            shading_conditions_start_or=["cond_temp2", "cond_brightness"],
            shading_brightness_sensor="sensor.b",
            shading_temperatur_sensor2=[],  # no sensor
            shading_start_condition_states={
                "azimuth_valid": False, "elevation_valid": False,
                "brightness_valid": True,
                "temp1_valid": False, "temp2_valid": True,  # would-be true but no sensor
                "forecast_temp_valid": False, "forecast_weather_valid": False,
            },
        )
        assert eval_condition(env, START_OR_RESULT, v) is True

    def test_only_unconfigured_condition_selected_returns_false(self, env):
        """Only cond_temp2 in OR but no sensor ⇒ no clause can trigger ⇒ FALSE."""
        v = base_vars(
            shading_conditions_start_or=["cond_temp2"],
            shading_temperatur_sensor2=[],
        )
        assert eval_condition(env, START_OR_RESULT, v) is False

    def test_unselected_condition_does_not_count(self, env):
        """cond_brightness valid but not in OR ⇒ doesn't trigger OR."""
        v = base_vars(
            shading_conditions_start_or=["cond_temp1"],
            shading_brightness_sensor="sensor.b",
            shading_temperatur_sensor1="sensor.t1",
            shading_start_condition_states={
                "azimuth_valid": False, "elevation_valid": False,
                "brightness_valid": True,  # valid but not selected
                "temp1_valid": False,      # selected but invalid
                "temp2_valid": False, "forecast_temp_valid": False, "forecast_weather_valid": False,
            },
        )
        assert eval_condition(env, START_OR_RESULT, v) is False


# ─────────────────────────────────────────────────────────────────────────────
# shading_end_and_result
# ─────────────────────────────────────────────────────────────────────────────

class TestEndAndResult:
    def test_empty_end_and_returns_false(self, env):
        """Default end_and is empty; count == 0 ⇒ FALSE (covered via end_or)."""
        assert eval_condition(env, END_AND_RESULT, base_vars()) is False

    def test_unselected_condition_is_ignored(self, env):
        """Only cond_brightness selected; other invalid flags don't matter."""
        v = base_vars(
            shading_conditions_end_and=["cond_brightness"],
            shading_brightness_sensor="sensor.b",
            shading_end_condition_states={
                "azimuth_invalid": False, "elevation_invalid": False,
                "brightness_invalid": True,
                "temp1_invalid": False, "temp2_invalid": False,
                "forecast_temp_invalid": False, "forecast_weather_invalid": False,
            },
        )
        assert eval_condition(env, END_AND_RESULT, v) is True

    def test_selected_condition_without_sensor_skipped_FIX(self, env):
        """
        FIX VERIFICATION: User selects cond_temp2 in end_and but has no temp2 sensor.
        Before fix: clause permanently FALSE → end_and never fires.
        After fix:  clause auto-passes via 'shading_temperatur_sensor2 == []'.
        Combined with another truly-invalid selected condition, end_and ⇒ TRUE.
        """
        v = base_vars(
            shading_conditions_end_and=["cond_temp2", "cond_brightness"],
            shading_brightness_sensor="sensor.b",
            shading_temperatur_sensor2=[],  # no sensor
            shading_end_condition_states={
                "azimuth_invalid": False, "elevation_invalid": False,
                "brightness_invalid": True,  # the real check
                "temp1_invalid": False,
                "temp2_invalid": False,  # cannot become true without sensor
                "forecast_temp_invalid": False, "forecast_weather_invalid": False,
            },
        )
        assert eval_condition(env, END_AND_RESULT, v) is True

    def test_selected_with_sensor_and_invalid_returns_true(self, env):
        v = base_vars(
            shading_conditions_end_and=["cond_temp2"],
            shading_temperatur_sensor2="sensor.t2",
            shading_end_condition_states={
                "azimuth_invalid": False, "elevation_invalid": False,
                "brightness_invalid": False,
                "temp1_invalid": False,
                "temp2_invalid": True,
                "forecast_temp_invalid": False, "forecast_weather_invalid": False,
            },
        )
        assert eval_condition(env, END_AND_RESULT, v) is True

    def test_selected_with_sensor_but_still_valid_returns_false(self, env):
        v = base_vars(
            shading_conditions_end_and=["cond_temp2"],
            shading_temperatur_sensor2="sensor.t2",
            # temp2_invalid stays False (still warm enough)
        )
        assert eval_condition(env, END_AND_RESULT, v) is False

    def test_one_still_valid_among_many_returns_false(self, env):
        v = base_vars(
            shading_conditions_end_and=["cond_brightness", "cond_temp1"],
            shading_brightness_sensor="sensor.b",
            shading_temperatur_sensor1="sensor.t1",
            shading_end_condition_states={
                "azimuth_invalid": False, "elevation_invalid": False,
                "brightness_invalid": True,
                "temp1_invalid": False,  # still warm
                "temp2_invalid": False,
                "forecast_temp_invalid": False, "forecast_weather_invalid": False,
            },
        )
        assert eval_condition(env, END_AND_RESULT, v) is False


# ─────────────────────────────────────────────────────────────────────────────
# shading_end_or_result
# ─────────────────────────────────────────────────────────────────────────────

class TestEndOrResult:
    def test_empty_end_or_returns_false(self, env):
        """Empty OR ⇒ FALSE (covered via end_and in shading_end_conditions_met)."""
        assert eval_condition(env, END_OR_RESULT, base_vars()) is False

    def test_one_selected_with_sensor_and_invalid_returns_true(self, env):
        v = base_vars(
            shading_conditions_end_or=["cond_brightness"],
            shading_brightness_sensor="sensor.b",
            shading_end_condition_states={
                "azimuth_invalid": False, "elevation_invalid": False,
                "brightness_invalid": True,
                "temp1_invalid": False, "temp2_invalid": False,
                "forecast_temp_invalid": False, "forecast_weather_invalid": False,
            },
        )
        assert eval_condition(env, END_OR_RESULT, v) is True

    def test_selected_without_sensor_clause_skipped(self, env):
        """cond_temp2 in OR without sensor ⇒ clause FALSE; brightness can still trigger."""
        v = base_vars(
            shading_conditions_end_or=["cond_temp2", "cond_brightness"],
            shading_brightness_sensor="sensor.b",
            shading_temperatur_sensor2=[],
            shading_end_condition_states={
                "azimuth_invalid": False, "elevation_invalid": False,
                "brightness_invalid": True,
                "temp1_invalid": False,
                "temp2_invalid": False,  # X_invalid stays False without sensor
                "forecast_temp_invalid": False, "forecast_weather_invalid": False,
            },
        )
        assert eval_condition(env, END_OR_RESULT, v) is True

    def test_unselected_condition_does_not_trigger(self, env):
        """cond_brightness invalid but not in OR ⇒ doesn't trigger end."""
        v = base_vars(
            shading_conditions_end_or=["cond_temp1"],
            shading_brightness_sensor="sensor.b",
            shading_temperatur_sensor1="sensor.t1",
            shading_end_condition_states={
                "azimuth_invalid": False, "elevation_invalid": False,
                "brightness_invalid": True,  # invalid but not selected
                "temp1_invalid": False,      # selected but still valid
                "temp2_invalid": False,
                "forecast_temp_invalid": False, "forecast_weather_invalid": False,
            },
        )
        assert eval_condition(env, END_OR_RESULT, v) is False
