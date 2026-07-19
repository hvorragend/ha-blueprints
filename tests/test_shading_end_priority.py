"""
Tests for the shading-end execution branch priority and tilt target (Issue #583).

Two defects are covered:

1. The "Only tilt open after shading ends" branch (prevent option "Stay shaded:
   Don't open cover when sun shading ends") drove the slats to a hardcoded tilt
   of 50 instead of the user-configured `open_tilt_position` input (whose
   default happens to be 50, which is why the hardcoding went unnoticed).

2. The tilt-only branch was ordered BEFORE "Lockout protection when shading
   ends" and "Ventilation after shading ends" in the execution `choose:` and
   carries no window-contact condition. With both the prevent option and the
   ventilation option "Using the ventilation position when the sun shading is
   ended" enabled, a tilted window at shading end was swallowed by the
   tilt-only branch: the cover kept the shading position and tilted to 50
   instead of moving to `ventilate_position` / `ventilate_tilt_position`.
   Per the priority cascade (LOCKOUT prio 2 > VENT prio 4 > SHADING prio 6),
   lockout and ventilation must be evaluated first.

Branch conditions are extracted from the real blueprint YAML, not copied.

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


def _load_blueprint_yaml() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor(
        "!input", lambda loader, node: loader.construct_scalar(node)
    )
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


def _env(entity_states: dict | None = None) -> jinja2.Environment:
    entity_states = entity_states or {}
    env = jinja2.Environment(undefined=jinja2.Undefined)
    env.globals["states"] = lambda e: entity_states.get(e, "unknown")
    env.filters["regex_match"] = (
        lambda value, pattern: re.match(pattern, str(value)) is not None
    )
    env.filters["regex_search"] = (
        lambda value, pattern: re.search(pattern, str(value)) is not None
    )
    return env


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


def _shading_end_choose(blueprint: dict) -> list:
    """The choose: list inside the 'Check for shading end' branch."""
    outer = _find_branch_by_alias(blueprint, "Check for shading end")
    assert outer is not None, "'Check for shading end' branch not found"
    for step in outer["sequence"]:
        if isinstance(step, dict) and "if" in step:
            for then_step in step["then"]:
                if isinstance(then_step, dict) and "choose" in then_step:
                    return then_step["choose"]
    raise AssertionError("shading-end execution choose not found")


def _eval_condition(env: jinja2.Environment, cond, variables: dict) -> bool:
    """Evaluate one condition entry: a template string, an and:/or: block, or
    a `condition: !input ...` user condition (counts as passed)."""
    if isinstance(cond, str):
        return env.from_string(cond).render(**variables).strip() == "True"
    if isinstance(cond, dict):
        if "and" in cond:
            return all(_eval_condition(env, c, variables) for c in cond["and"])
        if "or" in cond:
            return any(_eval_condition(env, c, variables) for c in cond["or"])
        return True
    return True


def _eval_branch(env: jinja2.Environment, branch: dict, variables: dict) -> bool:
    return all(
        _eval_condition(env, cond, variables)
        for cond in branch.get("conditions", [])
    )


def _first_matching_alias(env, choose: list, variables: dict) -> str | None:
    for branch in choose:
        if _eval_branch(env, branch, variables):
            return branch.get("alias")
    return None


def _base_execution_vars(entity_states: dict) -> dict:
    """Variables shared by all execution-trigger scenarios below."""
    return {
        "trigger": {"id": "t_shading_end_execution"},
        "helper_state_pending_end": True,
        "helper_state_pending_start": False,
        "is_cover_tilt_enabled_and_possible": True,
        "is_ventilation_enabled": True,
        "resident_flags": {"allow_ventilate": True},
        "ventilation_flags": {"after_shading_end": True, "if_lower_enabled": False},
        "prevent_flags": {
            "opening_after_shading_end": True,
            "opening_after_shading_end_if_closed": False,
        },
        "lockout_tilted_when_shading_ends": False,
        "contact_window_opened": "binary_sensor.window_opened",
        "contact_window_tilted": "binary_sensor.window_tilted",
        # Normalized event flags (computed once per run in the blueprint's
        # post-forecast variables block), derived from the mocked states.
        "window_opened_now": entity_states.get("binary_sensor.window_opened") in ("on", "true"),
        "window_tilted_now": entity_states.get("binary_sensor.window_tilted") in ("on", "true"),
        "window_opened_clear": entity_states.get("binary_sensor.window_opened") in ("off", "false", None),
        "lockout_now": {
            "shading_end": entity_states.get("binary_sensor.window_opened") in ("on", "true"),
        },
        "position_comparisons": {
            "current_below_ventilate": True,
            "current_above_ventilate": False,
        },
        "current_position": 25,
        "ventilate_position": 50,
        "current_tilt_position": 0,
        "ventilate_tilt_position": 60,
        "shading_end_conditions_met": True,
        "shading_end_max_duration": 0,
        "is_shading_allowed_window": True,
    }


# ════════════════════════════════════════════════════════════════════════════
# Defect 1: tilt target must be the open_tilt_position input, not hardcoded 50
# ════════════════════════════════════════════════════════════════════════════
class TestTiltOnlyTarget:
    def test_tilt_only_branch_uses_open_tilt_position_input(self):
        bp = _load_blueprint_yaml()
        branch = _find_branch_by_alias(bp, "Only tilt open after shading ends")
        assert branch is not None
        for step in branch["sequence"]:
            if isinstance(step, dict) and "variables" in step:
                target = step["variables"]["drive_plan"]["target_tilt"]
                assert "open_tilt_position" in str(target)
                assert target != 50
                return
        raise AssertionError("drive_plan.target_tilt not found in tilt-only branch")


# ════════════════════════════════════════════════════════════════════════════
# Defect 2: lockout and ventilation must outrank the tilt-only branch
# ════════════════════════════════════════════════════════════════════════════
class TestShadingEndBranchOrder:
    def test_choose_order_matches_priority_cascade(self):
        choose = _shading_end_choose(_load_blueprint_yaml())
        aliases = [b.get("alias") for b in choose]
        lockout = aliases.index("Lockout protection when shading ends")
        vent = aliases.index("Ventilation after shading ends")
        tilt_only = aliases.index("Only tilt open after shading ends")
        move = aliases.index("Move cover after shading end - conditions still valid")
        assert lockout < vent < tilt_only < move


@pytest.fixture(scope="module")
def choose():
    return _shading_end_choose(_load_blueprint_yaml())


class TestShadingEndBranchSelection:
    def test_issue_583_tilted_window_selects_ventilation(self, choose):
        # Both options enabled, window tilted: ventilation must win so the
        # cover moves to ventilate_position/ventilate_tilt_position instead
        # of keeping the shading position with slats at the open tilt.
        entity_states = {
            "binary_sensor.window_opened": "off",
            "binary_sensor.window_tilted": "on",
        }
        variables = _base_execution_vars(entity_states)
        alias = _first_matching_alias(_env(entity_states), choose, variables)
        assert alias == "Ventilation after shading ends"

    def test_window_closed_selects_tilt_only(self, choose):
        entity_states = {
            "binary_sensor.window_opened": "off",
            "binary_sensor.window_tilted": "off",
        }
        variables = _base_execution_vars(entity_states)
        alias = _first_matching_alias(_env(entity_states), choose, variables)
        assert alias == "Only tilt open after shading ends"

    def test_window_fully_open_selects_lockout(self, choose):
        entity_states = {
            "binary_sensor.window_opened": "on",
            "binary_sensor.window_tilted": "off",
        }
        variables = _base_execution_vars(entity_states)
        alias = _first_matching_alias(_env(entity_states), choose, variables)
        assert alias == "Lockout protection when shading ends"

    def test_tilted_window_without_vent_option_selects_tilt_only(self, choose):
        # "Stay shaded" without the ventilation-after-shading-end option:
        # keep the shading position, only open the slats (previous behavior).
        entity_states = {
            "binary_sensor.window_opened": "off",
            "binary_sensor.window_tilted": "on",
        }
        variables = _base_execution_vars(entity_states)
        variables["ventilation_flags"] = {
            "after_shading_end": False,
            "if_lower_enabled": False,
        }
        alias = _first_matching_alias(_env(entity_states), choose, variables)
        assert alias == "Only tilt open after shading ends"

    def test_issue_608_tilt_cover_at_ventilate_position_selects_ventilation(self, choose):
        # Venetian-style setup where shading and ventilation share the same
        # cover position and only the slat angle differs (e.g. everything at
        # position 0, ventilate tilt 60). At shading end the cover already
        # rests AT the ventilate position, so current_below_ventilate is
        # false — the ventilation branch must still win via the tilt-cover
        # equality alternative (mirroring the contact handler), instead of
        # falling through to the tilt-only branch, which would open the
        # slats to open_tilt_position (Issue #608).
        entity_states = {
            "binary_sensor.window_opened": "off",
            "binary_sensor.window_tilted": "on",
        }
        variables = _base_execution_vars(entity_states)
        variables["position_comparisons"] = {
            "current_below_ventilate": False,
            "current_above_ventilate": False,
        }
        variables["current_position"] = 0
        variables["ventilate_position"] = 0
        variables["current_tilt_position"] = 0  # slats at shading angle
        variables["ventilate_tilt_position"] = 60
        alias = _first_matching_alias(_env(entity_states), choose, variables)
        assert alias == "Ventilation after shading ends"

    def test_issue_615_slats_above_ventilate_tilt_still_select_ventilation(self, choose):
        # Same equality setup, but the slats are already MORE open than the
        # ventilate tilt. Until 2026.07.19 the tilt alternative required
        # current_tilt_position <= ventilate_tilt_position ("do not pull the
        # slats down"), which made the configured ventilate state unreachable:
        # in_ventilate_position checks the tilt angle within tolerance, so a
        # cover with slats beyond the angle was NOT in the ventilate position,
        # yet no branch would drive it there (Issue #615). A tilted window now
        # always resolves to the ventilate target for a tilt cover at or below
        # the ventilate position, regardless of the current slat angle.
        entity_states = {
            "binary_sensor.window_opened": "off",
            "binary_sensor.window_tilted": "on",
        }
        variables = _base_execution_vars(entity_states)
        variables["position_comparisons"] = {
            "current_below_ventilate": False,
            "current_above_ventilate": False,
        }
        variables["current_position"] = 0
        variables["ventilate_position"] = 0
        variables["current_tilt_position"] = 80
        variables["ventilate_tilt_position"] = 60
        alias = _first_matching_alias(_env(entity_states), choose, variables)
        assert alias == "Ventilation after shading ends"
