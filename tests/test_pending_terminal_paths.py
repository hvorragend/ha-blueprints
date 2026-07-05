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


class TestShadingEndMoveCoverPreventedPath:
    """With prevent_flags.opening_after_shading_end set and tilt not possible,
    the 'Move cover after shading end' branch used to hit stop without any
    helper write, leaving pnd='end'/shd=1 armed forever (#395 pattern)."""

    @pytest.fixture(scope="class")
    def outer_if(self):
        branch = _find_branch_by_alias(
            _load_blueprint_yaml(), "Move cover after shading end - conditions still valid"
        )
        assert branch is not None
        step = branch["sequence"][0]
        assert "if" in step and "then" in step
        return step

    def test_prevented_path_has_else(self, outer_if):
        assert "else" in outer_if, (
            "prevent_flags.opening_after_shading_end path must still clear the "
            "pending; without an else the sequence stops without a helper write"
        )

    def test_prevented_path_terminates_pending_without_drive(self, outer_if):
        else_steps = outer_if["else"]
        variables = else_steps[0]["variables"]
        uv = variables["update_values"]
        assert uv.get("shd") == 0
        assert uv.get("pnd") == "non"
        ts = uv.get("ts", {}) or {}
        assert ts.get("due") == 0 and ts.get("arm") == 0
        # No drive happens here -> no man reset (Invariant 7), no base change,
        # and no drive_plan (the apply_transition anchor only drives when a
        # drive_plan with run=true is set).
        assert "man" not in uv and "bas" not in uv
        assert "drive_plan" not in variables, (
            "prevented path must not set a drive_plan (no cover movement)"
        )
        assert _steps_write_helper(else_steps)
