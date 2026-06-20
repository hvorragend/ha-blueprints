"""
Unit tests for the "Independent Temperature End" and "Early shading start" features
(GitHub issue #537).

Independent Temperature End:
  When 'shading_temp_comparison_independent_end' is selected in shading_config,
  the sun-position / brightness / weather END conditions are suppressed
  (their *_invalid flags become False), so only a temperature END condition can
  end the shading. Temperature *_invalid flags are unaffected.

Early shading start:
  When 'shading_early_start' is selected and a 'shading_window_start_time' is set,
  is_shading_allowed_window opens from that (earlier) time, before the normal
  opening time.

Templates are extracted verbatim from
blueprints/automation/cover_control_automation.yaml.
"""
import datetime
import pytest
from conftest import make_jinja_env, eval_condition


# --- Verbatim templates from the blueprint --------------------------------

AZIMUTH_INVALID = """
is_shading_enabled and
'shading_temp_comparison_independent_end' not in shading_config and
shading_end_condition_enabled.azimuth and
default_sun_sensor != [] and
(
  current_sun_azimuth | float(default=999) <= shading_azimuth_start or
  current_sun_azimuth | float(default=0) >= shading_azimuth_end
)
"""

ELEVATION_INVALID = """
is_shading_enabled and
'shading_temp_comparison_independent_end' not in shading_config and
shading_end_condition_enabled.elevation and
default_sun_sensor != [] and
(
  current_sun_elevation | float(default=999) <= shading_elevation_min or
  current_sun_elevation | float(default=0) >= shading_elevation_max
)
"""

BRIGHTNESS_INVALID = """
is_shading_enabled and
'shading_temp_comparison_independent_end' not in shading_config and
shading_end_condition_enabled.brightness and
shading_brightness_sensor != [] and
states(shading_brightness_sensor) not in invalid_states and
states(shading_brightness_sensor) | float(default=999999) < (shading_sun_brightness_end - shading_sun_brightness_hysteresis)
"""

FORECAST_WEATHER_INVALID = """
is_shading_enabled and
'shading_temp_comparison_independent_end' not in shading_config and
shading_end_condition_enabled.forecast_weather and
shading_weather_conditions != [] and
shading_forecast_sensor != [] and
forecast_weather_condition_raw is not none and
forecast_weather_condition_raw not in invalid_states and
forecast_weather_condition_raw not in shading_weather_conditions
"""

TEMP2_INVALID = """
is_shading_enabled and
shading_end_condition_enabled.temp2 and
shading_temperatur_sensor2 != [] and
states(shading_temperatur_sensor2) not in invalid_states and
states(shading_temperatur_sensor2) | float(default=999) < (shading_min_temperatur2 - shading_temperature_hysteresis2)
"""


@pytest.fixture
def env():
    return make_jinja_env()


def end_vars(**overrides):
    """Base vars: shading on, all end conditions enabled, sun sensor present,
    azimuth/elevation/brightness/weather currently *out of range* (would end)."""
    v = {
        "is_shading_enabled": True,
        "shading_config": [],  # independent-end NOT active by default
        "invalid_states": ["", "unavailable", "unknown", "none", "None"],
        "default_sun_sensor": "sun.sun",
        "shading_end_condition_enabled": {
            "azimuth": True, "elevation": True, "brightness": True,
            "temp1": True, "temp2": True, "forecast_temp": True,
            "forecast_weather": True,
        },
        # Azimuth out of range (above end)
        "current_sun_azimuth": 300.0,
        "shading_azimuth_start": 50.0,
        "shading_azimuth_end": 260.0,
        # Elevation above max
        "current_sun_elevation": 70.0,
        "shading_elevation_min": 10.0,
        "shading_elevation_max": 60.0,
        # Brightness below end threshold
        "shading_brightness_sensor": "sensor.lux",
        "shading_sun_brightness_end": 50000.0,
        "shading_sun_brightness_hysteresis": 0.0,
        # Weather not in configured (sunny) list
        "shading_weather_conditions": ["sunny"],
        "shading_forecast_sensor": "weather.home",
        "forecast_weather_condition_raw": "cloudy",
        # Temp2 still warm (NOT invalid)
        "shading_temperatur_sensor2": "sensor.temp2",
        "shading_min_temperatur2": 20.0,
        "shading_temperature_hysteresis2": 0.0,
    }
    v.update(overrides)
    return v


class TestIndependentEndSuppressesSunPosition:
    """Issue #537: independent-end must suppress sun/brightness/weather end."""

    def test_azimuth_invalid_true_without_option(self, env):
        assert eval_condition(env, AZIMUTH_INVALID, end_vars()) is True

    def test_azimuth_invalid_suppressed_with_option(self, env):
        v = end_vars(shading_config=["shading_temp_comparison_independent_end"])
        assert eval_condition(env, AZIMUTH_INVALID, v) is False

    def test_elevation_invalid_suppressed_with_option(self, env):
        v = end_vars(shading_config=["shading_temp_comparison_independent_end"])
        assert eval_condition(env, ELEVATION_INVALID, v) is False

    def test_brightness_invalid_suppressed_with_option(self, env):
        states = {"sensor.lux": "100"}  # below end threshold → would end
        e = make_jinja_env(states)
        v = end_vars(shading_config=["shading_temp_comparison_independent_end"])
        assert eval_condition(e, BRIGHTNESS_INVALID, v) is False

    def test_weather_invalid_suppressed_with_option(self, env):
        v = end_vars(shading_config=["shading_temp_comparison_independent_end"])
        assert eval_condition(env, FORECAST_WEATHER_INVALID, v) is False

    def test_temperature_end_still_active_with_option(self, env):
        """A temperature end condition must still be able to end shading."""
        states = {"sensor.temp2": "15"}  # below 20 → temp2 invalid (would end)
        e = make_jinja_env(states)
        v = end_vars(shading_config=["shading_temp_comparison_independent_end"])
        assert eval_condition(e, TEMP2_INVALID, v) is True

    def test_temperature_end_warm_does_not_end(self, env):
        states = {"sensor.temp2": "25"}  # above 20 → temp2 valid (stay shaded)
        e = make_jinja_env(states)
        v = end_vars(shading_config=["shading_temp_comparison_independent_end"])
        assert eval_condition(e, TEMP2_INVALID, v) is False


# --- Early shading start window -------------------------------------------

IS_SHADING_ALLOWED_WINDOW = """
is_time_control_disabled or
(
  'shading_early_start' in shading_config and
  is_time_field_enabled and
  shading_window_start_time not in ['', none, []] and
  now() >= today_at(shading_window_start_time) and
  now() <= today_at(time_down_late_today) + timedelta(seconds = 5)
) or
(
  is_time_field_enabled and
  now() >= today_at(time_up_early_today) and
  now() <= today_at(time_down_late_today) + timedelta(seconds = 5)
) or
(
  is_calendar_enabled and
  calendar_open_start is not none and
  calendar_close_end is not none and
  now_ts >= calendar_open_start and
  now_ts <= calendar_close_end
)
"""


def window_env(now_hhmm):
    """Build a jinja env with now()/today_at/timedelta mocked at a fixed clock."""
    base = datetime.datetime(2026, 6, 20, 0, 0, 0)
    now_dt = base.replace(hour=int(now_hhmm.split(":")[0]),
                          minute=int(now_hhmm.split(":")[1]))

    def now():
        return now_dt

    def today_at(t):
        h, m, s = (int(x) for x in str(t).split(":"))
        return base.replace(hour=h, minute=m, second=s)

    e = make_jinja_env()
    e.globals["now"] = now
    e.globals["today_at"] = today_at
    e.globals["timedelta"] = datetime.timedelta
    return e


def window_vars(**overrides):
    v = {
        "is_time_control_disabled": False,
        "is_calendar_enabled": False,
        "is_time_field_enabled": True,
        "shading_config": [],
        "shading_window_start_time": "05:00:00",
        "time_up_early_today": "07:00:00",
        "time_down_late_today": "21:00:00",
        "calendar_open_start": None,
        "calendar_close_end": None,
        "now_ts": 0,
    }
    v.update(overrides)
    return v


class TestEarlyShadingWindow:
    def test_before_opening_closed_without_option(self, env):
        """At 05:30, without early-start, the window is closed (opening is 07:00)."""
        e = window_env("05:30")
        assert eval_condition(e, IS_SHADING_ALLOWED_WINDOW, window_vars()) is False

    def test_before_opening_open_with_option(self, env):
        """At 05:30, with early-start (05:00), the window is open."""
        e = window_env("05:30")
        v = window_vars(shading_config=["shading_early_start"])
        assert eval_condition(e, IS_SHADING_ALLOWED_WINDOW, v) is True

    def test_before_early_time_still_closed(self, env):
        """At 04:30 (before the 05:00 direct time) the window is still closed."""
        e = window_env("04:30")
        v = window_vars(shading_config=["shading_early_start"])
        assert eval_condition(e, IS_SHADING_ALLOWED_WINDOW, v) is False

    def test_normal_window_unaffected_after_opening(self, env):
        """At 08:00 the window is open regardless of the early-start option."""
        e = window_env("08:00")
        assert eval_condition(e, IS_SHADING_ALLOWED_WINDOW, window_vars()) is True
