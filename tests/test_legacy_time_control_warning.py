"""
The legacy time-control warning (CCA 2026.07.14).

The #544 breaking change (2026.07.12) made the time_control_enabled checkbox the
single authoritative time-control switch. Pre-consolidation configs (~2026.05)
store neither the checkbox nor the legacy 'time_control_disabled' selector value,
so the update silently switched their time windows off — hybrid setups then opened
covers around sunrise (#595). A stored config cannot be repaired from inside a
blueprint, so CCA detects the constellation heuristically and raises a persistent
notification on the first run after a restart, a reload or a save.

These tests pin:
 - the detection heuristic (legacy_time_control_lost), including that a deliberate
   uncheck on a clean config is never flagged,
 - the literal time-field default list against the blueprint's input defaults,
 - the pre-dispatch step's placement and its guarantees (no stop:, no helper write).
"""
import json
import pathlib

import jinja2
import pytest
import yaml

BLUEPRINT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "blueprints"
    / "automation"
    / "cover_control_automation.yaml"
)

WARNING_ALIAS = "Legacy config warning: time control lost by the options consolidation"
RECOVERY_ALIAS = "Recovery after restart or outage - restore target state"

TIME_FIELDS = [
    "time_up_early",
    "time_up_early_non_workday",
    "time_up_late",
    "time_up_late_non_workday",
    "time_down_early",
    "time_down_early_non_workday",
    "time_down_late",
    "time_down_late_non_workday",
]


def _load_blueprint_yaml() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor(
        "!input",
        lambda loader, node: loader.construct_scalar(node),
    )
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


def _time_input_defaults(blueprint: dict) -> dict:
    inputs = blueprint["blueprint"]["input"]["time_section"]["input"]
    return {field: inputs[field]["default"] for field in TIME_FIELDS}


def _render_lost(
    blueprint,
    auto_options,
    time_control="time_control_input",
    times: dict | None = None,
    workday_sensor=None,
    calendar_entity=None,
):
    template = blueprint["trigger_variables"]["legacy_time_control_lost"]
    variables = dict(_time_input_defaults(blueprint))
    variables.update(times or {})
    variables.update(
        auto_options=auto_options,
        time_control=time_control,
        workday_sensor_today=workday_sensor if workday_sensor is not None else [],
        calendar_entity=calendar_entity if calendar_entity is not None else [],
    )
    out = jinja2.Environment().from_string(template).render(**variables)
    result = out.strip()
    assert result in ("True", "False"), f"not a single boolean expression: {result!r}"
    return result == "True"


@pytest.fixture(scope="module")
def blueprint():
    return _load_blueprint_yaml()


class TestDetectionHeuristic:
    """legacy_time_control_lost — who is flagged, and who never is."""

    def test_legacy_config_with_custom_times_is_flagged(self, blueprint):
        # The #595 shape: pre-consolidation config, time fields customized,
        # sensor triggers still firing without their time fence.
        assert _render_lost(
            blueprint,
            auto_options=["auto_up_enabled", "auto_down_enabled", "auto_sun_enabled"],
            times={"time_up_early": "05:45:00"},
        ) is True

    def test_legacy_config_with_workday_sensor_is_flagged(self, blueprint):
        # All-default times, but a workday sensor only matters for time windows.
        assert _render_lost(
            blueprint,
            auto_options=["auto_up_enabled"],
            workday_sensor="binary_sensor.workday",
        ) is True

    def test_legacy_calendar_config_is_flagged(self, blueprint):
        assert _render_lost(
            blueprint,
            auto_options=["auto_up_enabled", "auto_down_enabled"],
            time_control="time_control_calendar",
            calendar_entity="calendar.covers",
        ) is True

    def test_legacy_explicitly_disabled_stays_silent(self, blueprint):
        # A pre-consolidation config that had chosen 'Disabled' keeps its intent —
        # even with customized (now unused) time fields.
        assert _render_lost(
            blueprint,
            auto_options=["auto_up_enabled"],
            time_control="time_control_disabled",
            times={"time_up_early": "05:45:00"},
        ) is False

    def test_checkbox_present_stays_silent(self, blueprint):
        # Time control is on — nothing was lost, whatever else is configured.
        assert _render_lost(
            blueprint,
            auto_options=["auto_up_enabled", "time_control_enabled"],
            times={"time_up_early": "05:45:00"},
            workday_sensor="binary_sensor.workday",
        ) is False

    def test_deliberate_uncheck_on_clean_config_stays_silent(self, blueprint):
        # Pure sensor control, default times, no workday sensor, no calendar:
        # the one population the heuristic must never flag.
        assert _render_lost(
            blueprint,
            auto_options=["auto_up_enabled", "auto_down_enabled", "auto_sun_enabled"],
        ) is False

    def test_calendar_value_without_calendar_entity_stays_silent(self, blueprint):
        # The Type selector alone is not a signal — it has a stored value in
        # every config; only a configured calendar entity is.
        assert _render_lost(
            blueprint,
            auto_options=["auto_up_enabled"],
            time_control="time_control_calendar",
        ) is False

    def test_without_any_opening_or_closing_stays_silent(self, blueprint):
        # Shading-only setups have no time windows to lose.
        assert _render_lost(
            blueprint,
            auto_options=["auto_shading_enabled"],
            times={"time_up_early": "05:45:00"},
            workday_sensor="binary_sensor.workday",
        ) is False

    def test_default_auto_options_include_the_checkbox(self, blueprint):
        # The heuristic's premise: an untouched new config gets the checkbox via
        # the default, so it can never look like a legacy config.
        auto = blueprint["blueprint"]["input"]["feature_section"]["input"]["auto_options"]
        assert "time_control_enabled" in auto["default"]


class TestDefaultListPin:
    """The literal default list in the template must match the input defaults."""

    def test_time_defaults_have_not_drifted(self, blueprint):
        # Rendered with exactly the blueprint's input defaults (and no other
        # legacy signal), the comparison must find equality — i.e. stay silent.
        # If an input default changes without the template literal, this flips.
        assert _render_lost(
            blueprint,
            auto_options=["auto_up_enabled", "auto_down_enabled"],
        ) is False

    def test_every_time_field_deviation_is_a_signal(self, blueprint):
        for field in TIME_FIELDS:
            assert _render_lost(
                blueprint,
                auto_options=["auto_up_enabled"],
                times={field: "03:21:00"},
            ) is True, f"a customized {field} must count as a legacy signal"


class TestPreDispatchStep:
    """Placement and guarantees of the warning step."""

    def _step(self, blueprint):
        steps = [
            s
            for s in blueprint["actions"]
            if isinstance(s, dict) and s.get("alias") == WARNING_ALIAS
        ]
        assert len(steps) == 1, "warning step missing or duplicated"
        return steps[0]

    def test_step_runs_before_the_recovery_gate(self, blueprint):
        aliases = [
            s.get("alias") for s in blueprint["actions"] if isinstance(s, dict)
        ]
        assert WARNING_ALIAS in aliases
        assert RECOVERY_ALIAS in aliases
        assert aliases.index(WARNING_ALIAS) < aliases.index(RECOVERY_ALIAS), (
            "the warning must fire before the recovery gate stops the resumed run"
        )

    def test_step_is_gated_on_resumed_run_and_heuristic(self, blueprint):
        conditions = " ".join(str(c) for c in self._step(blueprint)["if"])
        assert "automation_resumed" in conditions
        assert "legacy_time_control_lost" in conditions

    def test_step_never_stops_the_run(self, blueprint):
        serialized = json.dumps(self._step(blueprint))
        assert '"stop"' not in serialized, (
            "a warning must never block a run (recovery.md orphan-audit rule)"
        )

    def test_step_never_writes_the_helper(self, blueprint):
        # A helper write would clear automation_resumed and disarm the pending
        # resume trigger before the recovery gate ran.
        serialized = json.dumps(self._step(blueprint))
        assert "input_text.set_value" not in serialized

    def test_notification_id_is_per_automation(self, blueprint):
        serialized = json.dumps(self._step(blueprint))
        assert "this.entity_id" in serialized, (
            "multiple CCA instances must not overwrite each other's notification"
        )
