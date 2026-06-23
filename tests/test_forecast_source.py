"""
Unit tests for the forecast_source gating variables:
  - use_sensor
  - use_weather
  - prevent_service

Regression for the bug where `use_weather` was gated on
`shading_forecast_temp_sensor in invalid_states`. An unset entity selector
(default: []) resolves to the empty list `[]`, which is NOT a member of the
string list `invalid_states`, so `use_weather` evaluated to False whenever a
weather entity was configured WITHOUT a direct temperature sensor — exactly the
primary/recommended setup. With use_weather False the weather.get_forecasts
service is never called, weather_forecast stays undefined, and
forecast_temp_raw / forecast_weather_condition_raw are null. Forecast-based
shading (especially as an AND condition) then never starts.

The templates below are extracted verbatim from
blueprints/automation/cover_control_automation.yaml.
"""
import pytest
from conftest import make_jinja_env, eval_condition


# invalid_states list, verbatim from the blueprint
INVALID_STATES = ["", "unavailable", "unknown", "none", "None", "null", "query failed"]

USE_SENSOR = "shading_forecast_temp_sensor != []"
USE_WEATHER = (
    "shading_forecast_sensor != [] and "
    "(shading_forecast_temp_sensor == [] or shading_forecast_temp_sensor in invalid_states)"
)
PREVENT_SERVICE = "'weather_attributes' in shading_forecast_type"


def _vars(weather, temp_sensor, forecast_type="daily"):
    return {
        "shading_forecast_sensor": weather,
        "shading_forecast_temp_sensor": temp_sensor,
        "shading_forecast_type": forecast_type,
        "invalid_states": INVALID_STATES,
    }


@pytest.fixture
def env():
    return make_jinja_env()


class TestUseWeather:
    def test_weather_entity_without_temp_sensor_default_list(self, env):
        """Primary setup: weather entity set, no temp sensor (unset = []).

        use_weather MUST be True so the forecast service is called.
        """
        v = _vars("weather.forecast_home", [])
        assert eval_condition(env, USE_WEATHER, v) is True

    def test_weather_entity_without_temp_sensor_empty_string(self, env):
        """Backward compatibility: some setups resolve an unset selector to ''."""
        v = _vars("weather.forecast_home", "")
        assert eval_condition(env, USE_WEATHER, v) is True

    def test_weather_entity_with_temp_sensor(self, env):
        """A configured temp sensor takes priority -> weather service not used."""
        v = _vars("weather.forecast_home", "sensor.forecast_high")
        assert eval_condition(env, USE_WEATHER, v) is False

    def test_no_weather_entity(self, env):
        v = _vars([], [])
        assert eval_condition(env, USE_WEATHER, v) is False


class TestUseSensor:
    def test_temp_sensor_configured(self, env):
        v = _vars("weather.forecast_home", "sensor.forecast_high")
        assert eval_condition(env, USE_SENSOR, v) is True

    def test_temp_sensor_unset(self, env):
        v = _vars("weather.forecast_home", [])
        assert eval_condition(env, USE_SENSOR, v) is False


class TestMutualExclusivity:
    """use_weather and use_sensor must not both drive the same path for the
    documented empty representation ([]) and a real sensor entity."""

    @pytest.mark.parametrize("temp_sensor", [[], "sensor.forecast_high"])
    def test_weather_and_sensor_never_both_active(self, env, temp_sensor):
        v = _vars("weather.forecast_home", temp_sensor)
        use_weather = eval_condition(env, USE_WEATHER, v)
        use_sensor = eval_condition(env, USE_SENSOR, v)
        assert not (use_weather and use_sensor)


class TestServiceCallGate:
    """The weather.get_forecasts service is gated on
    `use_weather and not prevent_service`."""

    def test_service_called_for_daily_weather_without_temp_sensor(self, env):
        v = _vars("weather.forecast_home", [], forecast_type="daily")
        gate = f"({USE_WEATHER}) and not ({PREVENT_SERVICE})"
        assert eval_condition(env, gate, v) is True

    def test_service_not_called_in_weather_attributes_mode(self, env):
        v = _vars("weather.forecast_home", [], forecast_type="weather_attributes")
        gate = f"({USE_WEATHER}) and not ({PREVENT_SERVICE})"
        assert eval_condition(env, gate, v) is False
