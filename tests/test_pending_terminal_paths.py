"""
Regression tests: every execution path of the shading start/end pending
machinery must terminate the pending state (helper write + stop).

Background: t_shading_start_execution / t_shading_end_execution are template
triggers on `now() >= ts.due`. Once due is in the past the template stays true
forever, so the trigger never re-fires. Any execution path that ends WITHOUT
writing the helper leaves `pnd` armed permanently (until the midnight reset)
and blocks new pending triggers.

Covered here:
  - Shading start execution: the inner drive choose (lockout / start / save)
    has a default that records the shading state and clears the pending.
  - Shading end "Move cover after shading end": the
    `prevent_flags.opening_after_shading_end` path must still clear the
    pending (else-branch), not fall through to stop without a helper write.
"""
import pathlib

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
        "!input",
        lambda loader, node: loader.construct_scalar(node),
    )
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


def _find_branch_by_alias(blueprint: dict, alias: str) -> dict | None:
    def walk(node):
        if isinstance(node, dict):
            if node.get("alias") == alias:
                return node
            for v in node.values():
                found = walk(v)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item)
                if found is not None:
                    return found
        return None

    return walk(blueprint)


def _steps_write_helper(steps: list) -> bool:
    """True when the step list contains a helper_update block (choose+default
    wrapping input_text.set_value) — i.e. the resolved *helper_update anchor."""
    flat = str(steps)
    return "input_text.set_value" in flat


def _find_variable_definition(node, name):
    if isinstance(node, dict):
        variables = node.get("variables")
        if isinstance(variables, dict) and name in variables:
            return variables[name]
        for value in node.values():
            found = _find_variable_definition(value, name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_variable_definition(item, name)
            if found is not None:
                return found
    return None


class TestShadingStartExecutionInnerDefault:
    """The drive choose (lockout / start shading / save for future) must have
    a default: a cover resting exactly at the shading position (non-tilt) or
    held at the ventilation floor matches none of the three branches."""

    @pytest.fixture(scope="class")
    def inner_choose(self):
        branch = _find_branch_by_alias(_load_blueprint_yaml(), "Shading start execution")
        assert branch is not None
        step = branch["sequence"][0]
        assert "then" in step, "expected the condition/override if-step"
        inner = step["then"][0]
        assert "choose" in inner
        return inner

    def test_default_exists(self, inner_choose):
        assert "default" in inner_choose, (
            "inner drive choose needs a default, otherwise the pending gets "
            "stuck when no drive branch matches (cover at shading position / "
            "ventilation floor)"
        )

    def test_default_terminates_pending(self, inner_choose):
        uv = inner_choose["default"][0]["variables"]["update_values"]
        assert uv.get("pnd") == "non"
        assert uv.get("shd") == 1, "shading state must be recorded (like save-for-future)"
        ts = uv.get("ts", {}) or {}
        assert ts.get("due") == 0 and ts.get("arm") == 0

    def test_default_does_not_clear_manual(self, inner_choose):
        # No drive happens in the default -> man must not be reset (Invariant 7)
        uv = inner_choose["default"][0]["variables"]["update_values"]
        assert "man" not in uv

    def test_default_writes_helper_and_stops(self, inner_choose):
        steps = inner_choose["default"]
        assert _steps_write_helper(steps)
        assert "stop" in steps[-1]


class TestShadingStartEntryLetsExecutionThrough:
    """Issue #632: the 'Check for shading start' branch-entry conditions must
    never reject a t_shading_start_execution run. The execution trigger fires
    exactly once (template `now() >= ts.due` never produces a new edge); a run
    rejected at branch entry falls into the dispatch default, which writes no
    helper — the armed pending freezes until the midnight reset, shd stays 0,
    and the global gate then suppresses every shading-end trigger for the day
    (cover parked at the shading position).

    Concretely: a non-tilt cover resting exactly at the shading position at
    execution time (e.g. reported position jitter around the shading position
    with position_tolerance 0) failed the positional entry OR. Every entry
    OR-group that can evaluate false while a start-pending is armed must carry
    the t_shading_start_execution bypass — as the once-per-day OR always has.
    (The is_shaded/window OR is safe by construction: helper_state_is_shaded
    is false whenever pnd == 'beg'.)"""

    @pytest.fixture(scope="class")
    def entry_or_groups(self):
        branch = _find_branch_by_alias(_load_blueprint_yaml(), "Check for shading start")
        assert branch is not None
        return [
            c["or"]
            for c in branch["conditions"]
            if isinstance(c, dict) and "or" in c
        ]

    def test_positional_entry_or_has_execution_bypass(self, entry_or_groups):
        positional = [
            group
            for group in entry_or_groups
            if any("in_shading_position" in str(alt) for alt in group)
        ]
        assert positional, "expected the positional entry OR-group"
        for group in positional:
            assert any("t_shading_start_execution" in str(alt) for alt in group), (
                "the positional entry check must not block "
                "t_shading_start_execution: a rejected execution run ends in "
                "the dispatch default without a helper write and freezes the "
                "armed pending for the rest of the day (#632)"
            )

    def test_once_per_day_entry_or_has_execution_bypass(self, entry_or_groups):
        once_groups = [
            group
            for group in entry_or_groups
            if any("shading_once_guard_ok" in str(alt) for alt in group)
        ]
        assert once_groups, "expected the once-per-day entry OR-group"
        for group in once_groups:
            assert any("t_shading_start_execution" in str(alt) for alt in group)


class TestShadingEndMoveCoverPreventedPath:
    """With prevent_flags.opening_after_shading_end set and tilt not possible,
    the 'Move cover after shading end' branch used to hit stop without any
    helper write, leaving pnd='end'/shd=1 armed forever (#395 pattern)."""

    @pytest.fixture(scope="class")
    def branch(self):
        branch = _find_branch_by_alias(
            _load_blueprint_yaml(), "Move cover after shading end - conditions still valid"
        )
        assert branch is not None
        return branch

    def test_prevent_flag_is_part_of_the_drive_gate(self, branch):
        will_drive = str(_find_variable_definition(branch, "will_drive"))
        opening_gate = str(
            _find_variable_definition(branch, "shading_end_opening_allows")
        )
        assert "shading_end_opening_allows" in will_drive
        assert "not prevent_flags.opening_after_shading_end" in opening_gate
        assert "shading_end_state != 'opn'" in opening_gate

    def test_prevented_path_terminates_pending_without_drive(self, branch):
        uv = _find_variable_definition(branch, "update_values")
        assert uv.get("shd") == 0
        assert uv.get("pnd") == "non"
        ts = uv.get("ts", {}) or {}
        assert ts.get("due") == 0 and ts.get("arm") == 0
        assert "bas" not in uv
        assert any(
            isinstance(step, dict)
            and step.get("if") == "{{ shading_end_state == 'opn' }}"
            for step in branch["sequence"]
        )
        assert "man" not in uv
        assert _steps_write_helper(branch["sequence"])
