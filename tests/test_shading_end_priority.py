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


def _find_variable(node, name: str):
    if isinstance(node, dict):
        variables = node.get("variables")
        if isinstance(variables, dict) and name in variables:
            return variables[name]
        for value in node.values():
            found = _find_variable(value, name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_variable(item, name)
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
        if "condition" in cond:
            return variables.get("_input_verdicts", {}).get(
                cond["condition"], True
            )
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
        "lockout_now": {
            "shading_end": entity_states.get("binary_sensor.window_opened") in ("on", "true"),
        },
        "position_comparisons": {
            "current_below_ventilate": True,
            "current_above_ventilate": False,
        },
        "current_position": 25,
        "ventilate_position": 50,
        "position_tolerance": 3,
        "in_ventilate_position": False,
        "current_tilt_position": 0,
        "ventilate_tilt_position": 60,
        "shading_end_conditions_met": True,
        "shading_end_state": (
            "lock" if entity_states.get("binary_sensor.window_opened") in ("on", "true")
            else "vnt" if entity_states.get("binary_sensor.window_tilted") in ("on", "true")
            else "opn"
        ),
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

    def test_issue_650_unavailable_opened_contact_still_selects_ventilation(self, choose):
        # Pattern AT (#650): a battery opened-contact that reads 'unavailable'
        # must count as "not open" (AN premise: an invalid contact reads as
        # 'off' in every handler). The vent branch used to demand an explicit
        # 'off' via window_opened_clear and fell through to a branch that
        # drives past the tilted window.
        entity_states = {
            "binary_sensor.window_opened": "unavailable",
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
        variables["shading_end_state"] = "opn"
        alias = _first_matching_alias(_env(entity_states), choose, variables)
        assert alias == "Only tilt open after shading ends"


class TestShadingEndProspectiveCascade:
    @staticmethod
    def _render_state(**over):
        branch = _find_branch_by_alias(
            _load_blueprint_yaml(), "Check for shading end"
        )
        template = _find_variable(branch, "shading_end_state")
        variables = {
            "helper_state_force": "non",
            "is_ventilation_enabled": True,
            "window_opened_now": False,
            "window_tilted_now": False,
            "state_resident": False,
            "resident_flags": {
                "closing_trigger": False,
                "allow_open": True,
                "allow_ventilate": True,
            },
            "helper_state_base": "opn",
            "is_opening_scheduled": True,
            "ventilation_flags": {"after_shading_end": False},
        }
        variables.update(over)
        return _env().from_string(template).render(**variables).strip()

    def test_privacy_close_is_the_target_after_background_shading_ends(self):
        rendered = self._render_state(
            state_resident=True,
            resident_flags={"closing_trigger": True, "allow_open": True,
                            "allow_ventilate": True},
        )
        assert rendered == "cls"

        branch = _find_branch_by_alias(
            _load_blueprint_yaml(), "Check for shading end"
        )
        move = _find_branch_by_alias(
            branch, "Move cover after shading end - conditions still valid"
        )
        assert "state_targets[shading_end_state]" in str(
            _find_variable(move, "drive_plan")
        )
        update = _find_variable(move, "update_values")
        assert "bas" not in update and update["shd"] == 0
        assert update["pnd"] == "non"

        open_update = next(
            step for step in move["sequence"]
            if isinstance(step, dict)
            and step.get("if") == "{{ shading_end_state == 'opn' }}"
        )
        condition = _env().from_string(open_update["if"])
        assert condition.render(shading_end_state="opn").strip() == "True"
        assert condition.render(shading_end_state="cls").strip() == "False"

    def test_ventilation_after_shading_option_overrides_scheduled_open_floor(self):
        assert self._render_state(window_tilted_now=True) == "opn"
        assert self._render_state(
            window_tilted_now=True,
            ventilation_flags={"after_shading_end": True},
        ) == "vnt"

    def test_scheduleless_tilt_keeps_the_normal_ventilation_floor(self):
        assert self._render_state(
            window_tilted_now=True, is_opening_scheduled=False
        ) == "vnt"

    @pytest.mark.parametrize("contact", ["opened", "tilted"])
    def test_ventilation_disabled_ignores_window_contacts(self, contact):
        overrides = {
            "is_ventilation_enabled": False,
            "window_opened_now": contact == "opened",
            "window_tilted_now": contact == "tilted",
            "ventilation_flags": {"after_shading_end": True},
        }
        assert self._render_state(**overrides) == "opn"

    def test_tilted_window_keeps_the_ventilation_floor_over_privacy(self, choose):
        entity_states = {
            "binary_sensor.window_opened": "off",
            "binary_sensor.window_tilted": "on",
        }
        variables = _base_execution_vars(entity_states)
        variables["shading_end_state"] = "vnt"
        alias = _first_matching_alias(_env(entity_states), choose, variables)
        assert alias == "Ventilation after shading ends"

    def test_stay_shaded_option_only_blocks_the_open_target(self):
        move = _find_branch_by_alias(
            _load_blueprint_yaml(),
            "Move cover after shading end - conditions still valid",
        )
        gate = _find_variable(move, "shading_end_opening_allows")
        env = _env()
        flags = {"opening_after_shading_end": True}
        assert env.from_string(gate).render(
            shading_end_state="opn", prevent_flags=flags
        ).strip() == "False"
        for target in ("cls", "lock", "vnt", "shd"):
            assert env.from_string(gate).render(
                shading_end_state=target, prevent_flags=flags
            ).strip() == "True"

        ventilation_gate = _find_variable(
            move, "shading_end_ventilation_allows"
        )
        assert env.from_string(ventilation_gate).render(
            shading_end_state="vnt",
            ventilation_flags={"after_shading_end": False},
        ).strip() == "False"

    def test_refused_ventilation_condition_cannot_fall_through_to_drive(self):
        move = _find_branch_by_alias(
            _load_blueprint_yaml(),
            "Move cover after shading end - conditions still valid",
        )
        gate_step = next(
            step for step in move["sequence"]
            if isinstance(step, dict)
            and any(
                branch.get("alias") ==
                "Shading end reconciliation: ventilation target allowed"
                for branch in step.get("choose", [])
            )
        )

        def verdict(state, allowed):
            variables = {
                "shading_end_state": state,
                "_input_verdicts": {
                    "auto_ventilate_condition": allowed,
                },
            }
            alias = _first_matching_alias(_env(), gate_step["choose"], variables)
            if alias is None:
                return gate_step["default"][0]["variables"][
                    "shading_end_target_condition_ok"
                ]
            branch = next(b for b in gate_step["choose"] if b["alias"] == alias)
            return branch["sequence"][0]["variables"][
                "shading_end_target_condition_ok"
            ]

        assert verdict("vnt", False) is False
        assert verdict("lock", False) is False
        assert verdict("vnt", True) is True
        assert verdict("lock", True) is True
        assert verdict("opn", False) is True

    def test_non_open_shading_end_leaves_preserve_schedule_base_and_open_stamp(self):
        blueprint = _load_blueprint_yaml()
        for alias in (
            "Lockout protection when shading ends",
            "Ventilation after shading ends",
            "Only tilt open after shading ends",
        ):
            update = _find_variable(
                _find_branch_by_alias(blueprint, alias), "update_values"
            )
            assert "bas" not in update, alias
            assert "opn" not in update.get("ts", {}), alias

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
        # ventilate tilt. Until 2026.07.20 the tilt alternative required
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

    def test_issue_667_tilt_cover_near_ventilate_position_selects_ventilation(self, choose):
        # Same venetian setup as #608, but the motor reports the resting
        # position a point off the commanded one (#538: tilt movement shifts
        # the reported position). Within position_tolerance and with the
        # slats off the ventilate angle, the ventilation branch must still
        # win — the exact-equality alternative alone left the event to the
        # reconciliation branch (contact handler: swallowed it entirely).
        entity_states = {
            "binary_sensor.window_opened": "off",
            "binary_sensor.window_tilted": "on",
        }
        variables = _base_execution_vars(entity_states)
        variables["position_comparisons"] = {
            "current_below_ventilate": False,
            "current_above_ventilate": True,  # raw comparison: 1 > 0
        }
        variables["current_position"] = 1
        variables["ventilate_position"] = 0
        variables["position_tolerance"] = 3
        variables["in_ventilate_position"] = False  # slats off the vent angle
        variables["current_tilt_position"] = 30
        variables["ventilate_tilt_position"] = 70
        alias = _first_matching_alias(_env(entity_states), choose, variables)
        assert alias == "Ventilation after shading ends"
