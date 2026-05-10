"""
Unit tests for the `environment_allows_opening` template.

Regression for issue #436: when only one of brightness/sun-elevation is enabled
and the operator is OR (default), the disabled sensor's short-circuit
must NOT dominate the OR result. The single active sensor's check must decide.

The template is extracted verbatim from
blueprints/automation/cover_control_automation.yaml (variable
`environment_allows_opening`).
"""
import pytest
from conftest import make_jinja_env


ENVIRONMENT_ALLOWS_OPENING = """
{%- set brightness_ok = (
  default_brightness_sensor == [] or
  states(default_brightness_sensor) | float(default=brightness_up) > (brightness_up + brightness_hysteresis)
) -%}
{%- set sun_ok = (
  default_sun_sensor == [] or
  current_sun_elevation | float(default=sun_elevation_up_current) > sun_elevation_up_current
) -%}
{%- if is_brightness_enabled and is_sun_elevation_enabled -%}
  {{ (brightness_ok and sun_ok) if use_and_operator else (brightness_ok or sun_ok) }}
{%- elif is_brightness_enabled -%}
  {{ brightness_ok }}
{%- elif is_sun_elevation_enabled -%}
  {{ sun_ok }}
{%- else -%}
  true
{%- endif -%}
"""


def render(env_states: dict, **variables) -> bool:
    env = make_jinja_env(env_states)
    template = env.from_string(ENVIRONMENT_ALLOWS_OPENING)
    result = template.render(**variables).strip()
    if result == "True" or result == "true":
        return True
    if result == "False" or result == "false":
        return False
    raise AssertionError(f"unexpected template result: {result!r}")


def base_vars(**overrides):
    v = {
        "is_brightness_enabled": False,
        "is_sun_elevation_enabled": False,
        "use_and_operator": False,
        "default_brightness_sensor": [],
        "default_sun_sensor": [],
        "current_sun_elevation": 0.0,
        "sun_elevation_up_current": 0.0,
        "brightness_up": 0,
        "brightness_hysteresis": 0,
    }
    v.update(overrides)
    return v


# ─────────────────────────────────────────────────────────────────────────────
# Regression for #436: only one sensor enabled with OR operator
# ─────────────────────────────────────────────────────────────────────────────

class TestSingleSensorWithOrOperator:
    """
    When only one of brightness/sun-elevation is enabled, the disabled sensor
    must not influence the result. The single active sensor's check decides
    regardless of operator.
    """

    def test_only_sun_enabled_or_below_threshold_returns_false(self):
        """
        Issue #436: time trigger at 05:00, brightness sensor disabled,
        sun elevation enabled at threshold -3, current elevation -10 → must NOT open.
        """
        result = render(
            env_states={},
            **base_vars(
                is_brightness_enabled=False,
                is_sun_elevation_enabled=True,
                use_and_operator=False,
                default_sun_sensor="sun.sun",
                current_sun_elevation=-10.0,
                sun_elevation_up_current=-3.0,
            ),
        )
        assert result is False, "Disabled brightness must not let the cover open via OR"

    def test_only_sun_enabled_or_above_threshold_returns_true(self):
        result = render(
            env_states={},
            **base_vars(
                is_brightness_enabled=False,
                is_sun_elevation_enabled=True,
                use_and_operator=False,
                default_sun_sensor="sun.sun",
                current_sun_elevation=5.0,
                sun_elevation_up_current=-3.0,
            ),
        )
        assert result is True

    def test_only_brightness_enabled_or_below_threshold_returns_false(self):
        """Symmetric case: only brightness active, value below threshold."""
        result = render(
            env_states={"sensor.bright": "100"},
            **base_vars(
                is_brightness_enabled=True,
                is_sun_elevation_enabled=False,
                use_and_operator=False,
                default_brightness_sensor="sensor.bright",
                brightness_up=500,
                brightness_hysteresis=50,
            ),
        )
        assert result is False

    def test_only_brightness_enabled_or_above_threshold_returns_true(self):
        result = render(
            env_states={"sensor.bright": "800"},
            **base_vars(
                is_brightness_enabled=True,
                is_sun_elevation_enabled=False,
                use_and_operator=False,
                default_brightness_sensor="sensor.bright",
                brightness_up=500,
                brightness_hysteresis=50,
            ),
        )
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# Same matrix with AND operator — must remain unchanged by the fix
# ─────────────────────────────────────────────────────────────────────────────

class TestSingleSensorWithAndOperator:
    def test_only_sun_enabled_and_below_threshold_returns_false(self):
        result = render(
            env_states={},
            **base_vars(
                is_brightness_enabled=False,
                is_sun_elevation_enabled=True,
                use_and_operator=True,
                default_sun_sensor="sun.sun",
                current_sun_elevation=-10.0,
                sun_elevation_up_current=-3.0,
            ),
        )
        assert result is False

    def test_only_sun_enabled_and_above_threshold_returns_true(self):
        result = render(
            env_states={},
            **base_vars(
                is_brightness_enabled=False,
                is_sun_elevation_enabled=True,
                use_and_operator=True,
                default_sun_sensor="sun.sun",
                current_sun_elevation=5.0,
                sun_elevation_up_current=-3.0,
            ),
        )
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# Both sensors enabled — operator must combine them as before
# ─────────────────────────────────────────────────────────────────────────────

class TestBothSensorsEnabled:
    def test_or_one_pass_one_fail_returns_true(self):
        result = render(
            env_states={"sensor.bright": "800"},
            **base_vars(
                is_brightness_enabled=True,
                is_sun_elevation_enabled=True,
                use_and_operator=False,
                default_brightness_sensor="sensor.bright",
                brightness_up=500,
                brightness_hysteresis=50,
                default_sun_sensor="sun.sun",
                current_sun_elevation=-10.0,
                sun_elevation_up_current=-3.0,
            ),
        )
        assert result is True

    def test_or_both_fail_returns_false(self):
        result = render(
            env_states={"sensor.bright": "100"},
            **base_vars(
                is_brightness_enabled=True,
                is_sun_elevation_enabled=True,
                use_and_operator=False,
                default_brightness_sensor="sensor.bright",
                brightness_up=500,
                brightness_hysteresis=50,
                default_sun_sensor="sun.sun",
                current_sun_elevation=-10.0,
                sun_elevation_up_current=-3.0,
            ),
        )
        assert result is False

    def test_and_one_pass_one_fail_returns_false(self):
        result = render(
            env_states={"sensor.bright": "800"},
            **base_vars(
                is_brightness_enabled=True,
                is_sun_elevation_enabled=True,
                use_and_operator=True,
                default_brightness_sensor="sensor.bright",
                brightness_up=500,
                brightness_hysteresis=50,
                default_sun_sensor="sun.sun",
                current_sun_elevation=-10.0,
                sun_elevation_up_current=-3.0,
            ),
        )
        assert result is False

    def test_and_both_pass_returns_true(self):
        result = render(
            env_states={"sensor.bright": "800"},
            **base_vars(
                is_brightness_enabled=True,
                is_sun_elevation_enabled=True,
                use_and_operator=True,
                default_brightness_sensor="sensor.bright",
                brightness_up=500,
                brightness_hysteresis=50,
                default_sun_sensor="sun.sun",
                current_sun_elevation=5.0,
                sun_elevation_up_current=-3.0,
            ),
        )
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# Neither sensor enabled — caller controls whether the gate applies
# ─────────────────────────────────────────────────────────────────────────────

class TestNoSensorsEnabled:
    def test_returns_true(self):
        """With no environment sensors enabled the gate must be transparent."""
        result = render(env_states={}, **base_vars())
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# Wiring test: blueprint template matches the structure tested here
# ─────────────────────────────────────────────────────────────────────────────

import pathlib

BLUEPRINT_PATH = pathlib.Path(__file__).parent.parent / "blueprints" / "automation" / "cover_control_automation.yaml"


class TestBlueprintTemplateWiring:
    def test_blueprint_contains_branched_structure(self):
        """
        Guard against silent reintroduction of the buggy short-circuit shape.
        The blueprint must select between brightness-only / sun-only / both
        based on is_*_enabled flags, not rely on a `not is_*_enabled` clause
        inside the *_ok set.
        """
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        # Locate the environment_allows_opening template
        anchor = "environment_allows_opening: >-"
        idx = text.find(anchor)
        assert idx != -1, "environment_allows_opening not found in blueprint"
        # Look at a generous window after the anchor
        snippet = text[idx:idx + 1500]

        # Buggy shape MUST be gone
        assert "not is_brightness_enabled or" not in snippet, (
            "Buggy short-circuit 'not is_brightness_enabled or' reappeared. "
            "Disabled sensor must not be set to TRUE inside the OR combination."
        )
        assert "not is_sun_elevation_enabled or" not in snippet, (
            "Buggy short-circuit 'not is_sun_elevation_enabled or' reappeared."
        )

        # New shape MUST be present
        assert "if is_brightness_enabled and is_sun_elevation_enabled" in snippet
        assert "elif is_brightness_enabled" in snippet
        assert "elif is_sun_elevation_enabled" in snippet
