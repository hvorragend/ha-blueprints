"""Tests for the ventilation floor on the slat angle (Issue #719).

VENT (priority 4) is a floor, not a target: a tilted window must not let the
cover drop *below* the ventilation position. Bug Pattern AE implemented that
floor by cover depth (`position_comparisons.shading_below_ventilate`). On
venetian setups shading and ventilation share one cover position and differ by
slat angle only, so the depth floor never binds - the shading start and the
elevation-based tilt stages drove the slats to the shading angle while the
window was tilted, below the ventilation angle (#719: ventilate tilt 30,
shading stages 0/16/24/33, every cover position 0).

The fix: `vent_tilt_floor_binds` / `shading_tilt_target` floor the applied
shading angle at the ventilation angle while the window is tilted (ventilation
enabled and allowed, shading not prioritised over ventilation). Consumers are
the two sites that apply the shading angle while VENT is in charge:

  - the "Start Shading" drive (tilted first, then shading starts), and
  - the tilt-stage re-drive (branch 3), which while tilted may only move the
    slats *to* the floor - never away from it (a stage above the floor stays
    frozen, as before; the window-closed return restores the real stage angle
    via `state_targets.shd`).

Everything else is unchanged: `shading_over_ventilation` keeps letting the
shading angle win, a fully open window still blocks, and an untilted window
applies the stage angle as before.

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

SHADING_TILT_ALIAS = "Check for shading tilt"
SHADING_ALT_ALIAS = "Check for alternate shading position"
START_SHADING_ALIAS = "Start Shading"
VENT_FLOOR_ALIAS = "Shading start - hold ventilation floor (window tilted)"
RETURN_ALIAS = "Window closed - Return to background state"


def _blueprint_text() -> str:
    return BLUEPRINT_PATH.read_text(encoding="utf-8")


def _load_blueprint_yaml() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


BP = _load_blueprint_yaml()


def _find_branch_by_alias(node, alias: str):
    if isinstance(node, dict):
        if node.get("alias") == alias:
            return node
        for value in node.values():
            found = _find_branch_by_alias(value, alias)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_branch_by_alias(item, alias)
            if found is not None:
                return found
    return None


def _action_var(name: str):
    for step in BP["actions"]:
        if isinstance(step, dict) and name in step.get("variables", {}):
            return step["variables"][name]
    raise AssertionError(f"action-level variable {name!r} not found")


def _branch_variables(branch: dict) -> dict:
    for step in branch.get("sequence", []):
        if isinstance(step, dict) and "variables" in step:
            return step["variables"]
    raise AssertionError("variables step not found")


def _render(template: str, entity_states: dict | None = None, **variables) -> str:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    states = entity_states or {}
    env.globals["states"] = lambda entity_id: states.get(entity_id, "unknown")
    env.filters["regex_search"] = lambda v, p: re.search(p, str(v)) is not None
    return env.from_string(template).render(**variables).strip()


def _render_bool(template: str, entity_states: dict | None = None, **variables) -> bool:
    out = _render(template, entity_states, **variables)
    assert out in ("True", "False"), f"boolean variable rendered {out!r} (HA literal_eval trap)"
    return out == "True"


def _floor(**variables) -> bool:
    return _render_bool(_action_var("vent_tilt_floor_binds"), **variables)


def _target(**variables) -> str:
    """shading_tilt_target reads vent_tilt_floor_binds - render the chain like HA does."""
    return _render(_action_var("shading_tilt_target"),
                   vent_tilt_floor_binds=_floor(**variables), **variables)


# The #719 reporter's configuration: venetian blind, every cover position 0,
# ventilate tilt 30, shading stages 0 / 16 / 24 / 33 at elevations 0 / 32 / 50.
ISSUE_719 = dict(
    open_position=100, close_position=0, ventilate_position=0, shading_position=0,
    position_tolerance=0, ventilate_tilt_position=30,
    shading_tilt_elevation_1=0, shading_tilt_elevation_2=32, shading_tilt_elevation_3=50,
    shading_tilt_position_0=0, shading_tilt_position_1=16,
    shading_tilt_position_2=24, shading_tilt_position_3=33,
)


def _floor_vars(**over) -> dict:
    """Variables for vent_tilt_floor_binds / shading_tilt_target: the tilted
    window case of the reporter at tilt stage 2 (24 < 30) unless overridden."""
    base = dict(
        is_ventilation_enabled=True,
        shading_over_ventilation=False,
        window_tilted_now=True,
        window_opened_now=False,
        force_allows_ventilate=True,
        resident_flags={"allow_ventilate": True, "allow_shade": True},
        is_cover_tilt_enabled_and_possible=True,
        shading_tilt_position=24,
        ventilate_tilt_position=30,
    )
    base.update(over)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# The projection
# ─────────────────────────────────────────────────────────────────────────────


class TestFloorProjection:
    FLOOR = _action_var("vent_tilt_floor_binds")

    def test_binds_in_the_reported_setup(self):
        assert _floor(**_floor_vars()) is True
        assert _target(**_floor_vars()) == "30"

    def test_a_stage_above_the_ventilation_angle_is_not_floored(self):
        """Stage 3 (33) clears the floor - the shading angle applies."""
        assert _floor(**_floor_vars(shading_tilt_position=33)) is False
        assert _target(**_floor_vars(shading_tilt_position=33)) == "33"

    def test_a_stage_equal_to_the_ventilation_angle_is_not_floored(self):
        assert _floor(**_floor_vars(shading_tilt_position=30)) is False
        assert _target(**_floor_vars(shading_tilt_position=30)) == "30"

    def test_closed_window_applies_the_shading_angle(self):
        assert _floor(**_floor_vars(window_tilted_now=False)) is False
        assert _target(**_floor_vars(window_tilted_now=False)) == "24"

    def test_opened_beats_tilted(self):
        """Invariant 5: a fully open window is LOCKOUT, never a ventilation floor."""
        assert _floor(**_floor_vars(window_opened_now=True)) is False

    def test_shading_over_ventilation_lets_the_shading_angle_win(self):
        assert _floor(**_floor_vars(shading_over_ventilation=True)) is False
        assert _target(**_floor_vars(shading_over_ventilation=True)) == "24"

    def test_ventilation_disabled_ignores_the_contacts(self):
        assert _floor(**_floor_vars(is_ventilation_enabled=False)) is False

    def test_non_tilt_cover_has_no_slat_floor(self):
        assert _floor(**_floor_vars(is_cover_tilt_enabled_and_possible=False)) is False

    def test_resident_ventilation_ban_removes_the_floor(self):
        """Mirrors the cascade: without allow_ventilate VENT does not apply."""
        assert _floor(**_floor_vars(
            resident_flags={"allow_ventilate": False, "allow_shade": True})) is False

    def test_a_force_that_outranks_ventilation_removes_the_floor(self):
        assert _floor(**_floor_vars(force_allows_ventilate=False)) is False

    def test_floor_renders_as_a_single_expression(self):
        """Code style: boolean variables must be one {{ }} expression."""
        assert "{%" not in self.FLOOR
        assert self.FLOOR.count("{{") == 1


class TestReportedStages:
    """The real shading_tilt_position template with the reporter's values."""

    STAGE = BP["variables"]["shading_tilt_position"]

    @pytest.mark.parametrize("elevation, stage, expected", [
        (55, 33, 33),   # stage 3 above the floor: shading angle applies
        (40, 24, 30),   # stage 2 below the floor: held at the ventilation angle
        (10, 16, 30),   # stage 1 below the floor
        (-2, 0, 30),    # stage 0 below the floor
    ])
    def test_tilted_window_floors_the_stage(self, elevation, stage, expected):
        rendered_stage = int(_render(self.STAGE, current_sun_elevation=elevation, **ISSUE_719))
        assert rendered_stage == stage
        assert _target(**_floor_vars(shading_tilt_position=rendered_stage)) == str(expected)

    @pytest.mark.parametrize("elevation, stage", [(55, 33), (40, 24), (10, 16), (-2, 0)])
    def test_closed_window_keeps_the_stage(self, elevation, stage):
        rendered_stage = int(_render(self.STAGE, current_sun_elevation=elevation, **ISSUE_719))
        assert _target(**_floor_vars(
            shading_tilt_position=rendered_stage, window_tilted_now=False)) == str(stage)


# ─────────────────────────────────────────────────────────────────────────────
# The consumers
# ─────────────────────────────────────────────────────────────────────────────


def _gate_vars(**over) -> dict:
    base = dict(
        is_paused=False,
        manual_allows_event={"shd": True},
        force_allows_shade=True,
        resident_flags={"allow_shade": True},
        is_ventilation_enabled=True,
        window_opened_now=False,
        window_tilted_now=True,
        shading_over_ventilation=False,
        vent_tilt_floor_binds=True,
        cover_status_helper="input_text.cca_status",
    )
    base.update(over)
    return base


class TestShadingTiltBranch:
    """Branch 3: the stage re-drive while the window is tilted."""

    @pytest.fixture(scope="class")
    def branch(self):
        branch = _find_branch_by_alias(BP["actions"], SHADING_TILT_ALIAS)
        assert branch is not None
        return branch

    def _drives(self, branch, **over) -> bool:
        gate = _branch_variables(branch)["will_drive"]
        return _render_bool(gate, {"input_text.cca_status": '{"shd":1}'}, **_gate_vars(**over))

    def test_targets_the_floored_angle(self, branch):
        plan = _branch_variables(branch)["drive_plan"]
        assert plan["target_tilt"] == "{{ shading_tilt_target | int }}"
        assert plan["move"] == "tilt"

    def test_tilted_window_drives_to_the_floor(self, branch):
        """#719: the stage drops below the ventilation angle - slats go to the floor."""
        assert self._drives(branch, vent_tilt_floor_binds=True) is True

    def test_tilted_window_stays_frozen_above_the_floor(self, branch):
        """Unchanged (#397): a stage at/above the ventilation angle is not applied
        while tilted - the window-closed return brings the real stage angle."""
        assert self._drives(branch, vent_tilt_floor_binds=False) is False

    def test_opened_window_always_blocks(self, branch):
        for binds in (False, True):
            assert self._drives(branch, window_opened_now=True, window_tilted_now=False,
                                vent_tilt_floor_binds=binds) is False

    def test_closed_window_drives_as_before(self, branch):
        assert self._drives(branch, window_tilted_now=False, vent_tilt_floor_binds=False) is True

    def test_shading_over_ventilation_drives_as_before(self, branch):
        assert self._drives(branch, shading_over_ventilation=True, vent_tilt_floor_binds=False) is True

    def test_other_gates_still_apply_at_the_floor(self, branch):
        """The floor only lifts the tilted-window block; pause, manual, force,
        resident and the helper marker still gate the drive."""
        assert self._drives(branch, is_paused=True) is False
        assert self._drives(branch, manual_allows_event={"shd": False}) is False
        assert self._drives(branch, force_allows_shade=False) is False
        assert self._drives(branch, resident_flags={"allow_shade": False}) is False

    def test_log_line_names_the_floor(self, branch):
        log_user = _branch_variables(branch)["log_user"]
        assert "ventilation angle" in _render(log_user, vent_tilt_floor_binds=True)
        assert "ventilation angle" not in _render(log_user, vent_tilt_floor_binds=False)

    def test_no_state_change(self, branch):
        """A stage re-drive is pure actuation (unchanged)."""
        assert _branch_variables(branch)["update_values"] == {}


class TestStartShading:
    """Tilted first, then shading starts on a venetian setup."""

    @pytest.fixture(scope="class")
    def branch(self):
        branch = _find_branch_by_alias(BP["actions"], START_SHADING_ALIAS)
        assert branch is not None
        return branch

    def test_targets_the_floored_angle(self, branch):
        plan = _branch_variables(branch)["drive_plan"]
        assert plan["target_tilt"] == "{{ shading_tilt_target | int }}"
        assert plan["target"] == "{{ effective_shading_position | int }}"
        assert plan["action_set"] == "shading_start"

    def test_still_marks_the_shading_active(self, branch):
        """The floor only changes the applied angle; shd/pnd/ts stay as before, so
        the window-closed return (return_target 'shd') restores the stage angle."""
        uv = _branch_variables(branch)["update_values"]
        assert uv["shd"] == 1
        assert uv["pnd"] == "non"
        assert uv["ts"]["due"] == 0 and uv["ts"]["arm"] == 0

    def test_log_line_names_the_floor(self, branch):
        log_user = _branch_variables(branch)["log_user"]
        assert "ventilation angle" in _render(log_user, vent_tilt_floor_binds=True)
        assert _render(log_user, vent_tilt_floor_binds=False) == "sun shading started"

    def test_depth_floor_branch_is_untouched(self):
        """Bug Pattern AE keeps handling shading depths below the ventilation
        position; the slat floor complements it for equal depths."""
        branch = _find_branch_by_alias(BP["actions"], VENT_FLOOR_ALIAS)
        assert "{{ position_comparisons.shading_below_ventilate }}" in branch["conditions"]
        plan = _branch_variables(branch)["drive_plan"]
        assert plan["target_tilt"] == "{{ ventilate_tilt_position | int }}"


class TestReturnRestoresTheStageAngle:
    """When the window closes, the cover goes back to the real shading angle."""

    def test_shading_target_is_not_floored(self):
        targets = _action_var("state_targets")
        assert targets["shd"]["target_tilt"] == "{{ shading_tilt_position | int }}"

    def test_return_branch_drives_the_shading_target(self):
        branch = _find_branch_by_alias(BP["actions"], RETURN_ALIAS)
        assert branch is not None
        seq = str(branch["sequence"])
        assert "state_targets[return_target]" in seq

    def test_alternate_depth_branch_is_untouched(self):
        """3b stays blocked while tilted (option off) and keeps the raw stage angle."""
        branch = _find_branch_by_alias(BP["actions"], SHADING_ALT_ALIAS)
        plan = _branch_variables(branch)["drive_plan"]
        assert plan["target_tilt"] == "{{ shading_tilt_position | int }}"
        assert "vent_tilt_floor_binds" not in str(_branch_variables(branch)["will_drive"])


class TestFloorIsScopedToTheTwoSites:
    def test_consumers(self):
        text = _blueprint_text()
        assert text.count("shading_tilt_target | int") == 2, (
            "the floored angle is applied by exactly two drive sites: "
            "'Start Shading' and the tilt-stage re-drive"
        )
