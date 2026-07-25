"""
Tests for the optional Full Ventilation Position (lockout position) feature.

The feature adds an optional `lockout_position` input. When the window opens
completely (LOCKOUT), the cover drives to this position instead of the open
position — for setups where "open" is not "cover fully up" (e.g. a terrace-door
blind whose everyday open position is 0 % with open slats, forum request by
Tincup81). The active target is derived via the central
`effective_lockout_position` variable, which falls back to `open_position`
when the input is unset (backward compatible, mirrors the
`effective_shading_position` pattern from #580).

Key properties verified here:
  - Backward compatibility: with the input unset, effective == open_position.
  - state_targets.lock / state_gates.lock read the effective value and the
    dedicated in_lockout_position checker.
  - The contact-opened branches gate/drive on the lockout position, not the
    open position.
  - The two flows that deliberately drive toward the open target while the
    lockout window may be open — "Normal opening of the cover" (Bug Pattern AG
    fall-through) and the shading-end "Move cover after shading end" — swap
    their target to the lockout position when effective_state == 'lock'.
    Without the swap they would pull the cover DOWN onto an open window in a
    split-position config (lockout violation).

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


def _blueprint_text() -> str:
    return BLUEPRINT_PATH.read_text(encoding="utf-8")


def _load_blueprint_yaml() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor(
        "!input", lambda loader, node: loader.construct_scalar(node)
    )
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


def _env() -> jinja2.Environment:
    return jinja2.Environment(undefined=jinja2.Undefined)


def _find_input(node, name):
    if isinstance(node, dict):
        if name in node and isinstance(node[name], dict) and "selector" in node[name]:
            return node[name]
        for v in node.values():
            found = _find_input(v, name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_input(item, name)
            if found is not None:
                return found
    return None


def _find_variable_definition(blueprint, name: str):
    def walk(node):
        if isinstance(node, dict):
            variables = node.get("variables")
            if isinstance(variables, dict) and name in variables:
                return variables[name]
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


def _branch_drive_plan(branch: dict) -> dict:
    for step in branch.get("sequence", []):
        if isinstance(step, dict) and "variables" in step:
            plan = step["variables"].get("drive_plan")
            if plan is not None:
                return plan
    return {}


# ════════════════════════════════════════════════════════════════════════════
# Input
# ════════════════════════════════════════════════════════════════════════════
class TestInput:
    def test_input_defined(self):
        assert "lockout_position:" in _blueprint_text()

    def test_input_is_optional_number_selector(self):
        inp = _find_input(_load_blueprint_yaml(), "lockout_position")
        assert inp is not None
        assert inp["default"] == []
        assert inp["selector"]["number"]["min"] == 0.0
        assert inp["selector"]["number"]["max"] == 100.0

    def test_input_bound_in_trigger_variables(self):
        bp = _load_blueprint_yaml()
        assert bp["trigger_variables"]["lockout_position"] == "lockout_position"


# ════════════════════════════════════════════════════════════════════════════
# effective_lockout_position — the central mechanism
# ════════════════════════════════════════════════════════════════════════════
class TestEffectiveLockoutPosition:
    @pytest.fixture(scope="class")
    def tmpl(self):
        return _load_blueprint_yaml()["variables"]["effective_lockout_position"]

    def _render(self, tmpl, *, lockout, open_position=100):
        out = (
            _env()
            .from_string(tmpl)
            .render(lockout_position=lockout, open_position=open_position)
            .strip()
        )
        return int(out)

    def test_unset_falls_back_to_open_position(self, tmpl):
        # Input unset — byte-for-byte the old behavior.
        assert self._render(tmpl, lockout=[], open_position=100) == 100
        assert self._render(tmpl, lockout=[], open_position=0) == 0

    def test_set_overrides_open_position(self, tmpl):
        # The reported scenario: open position 0 (blind down, slats open),
        # terrace door opens -> drive fully up.
        assert self._render(tmpl, lockout=100, open_position=0) == 100

    def test_zero_is_a_valid_configured_value(self, tmpl):
        assert self._render(tmpl, lockout=0, open_position=100) == 0

    def test_defined_before_its_consumers(self):
        keys = list(_load_blueprint_yaml()["variables"].keys())
        assert keys.index("effective_lockout_position") < keys.index(
            "in_lockout_position"
        )


# ════════════════════════════════════════════════════════════════════════════
# in_lockout_position — position checker
# ════════════════════════════════════════════════════════════════════════════
class TestInLockoutPosition:
    @pytest.fixture(scope="class")
    def tmpl(self):
        return _load_blueprint_yaml()["variables"]["in_lockout_position"]

    def test_uses_effective_value_with_tolerance(self, tmpl):
        assert "effective_lockout_position - position_tolerance" in tmpl
        assert "effective_lockout_position + position_tolerance" in tmpl

    def test_tilt_check_uses_open_tilt_position(self, tmpl):
        # The lock state keeps the open tilt target (state_targets.lock).
        assert "open_tilt_position" in tmpl

    def _render(self, tmpl, *, current, target, tolerance=0):
        out = (
            _env()
            .from_string(tmpl)
            .render(
                effective_lockout_position=target,
                position_tolerance=tolerance,
                current_position=current,
                is_cover_tilt_enabled_and_possible=False,
                current_tilt_position=0,
                open_tilt_position=100,
                tilt_position_tolerance=0,
            )
            .strip()
        )
        return out == "True"

    def test_matches_within_tolerance(self, tmpl):
        assert self._render(tmpl, current=99, target=100, tolerance=1) is True

    def test_does_not_match_outside_tolerance(self, tmpl):
        assert self._render(tmpl, current=0, target=100, tolerance=1) is False


# ════════════════════════════════════════════════════════════════════════════
# Consumers use the effective value, not the raw open position
# ════════════════════════════════════════════════════════════════════════════
class TestConsumersUseEffective:
    def test_state_targets_lock_uses_effective(self):
        targets = _find_variable_definition(_load_blueprint_yaml(), "state_targets")
        assert "effective_lockout_position" in str(targets["lock"]["target"])
        # The open state itself keeps the raw open position.
        assert "open_position" in str(targets["opn"]["target"])
        assert "effective_lockout_position" not in str(targets["opn"]["target"])

    def test_state_gates_lock_uses_in_lockout_position(self):
        gates = _find_variable_definition(_load_blueprint_yaml(), "state_gates")
        assert "in_lockout_position" in gates["lock"]
        assert "in_open_position" not in gates["lock"]
        # The open gate keeps the open-position check.
        assert "in_open_position" in gates["opn"]

    def test_contact_opened_drive_branch(self):
        branch = _find_branch_by_alias(
            _load_blueprint_yaml()["actions"],
            "Window opened - Full ventilation (lockout)",
        )
        assert branch is not None
        conds = str(branch["conditions"])
        assert "not in_lockout_position" in conds
        assert "in_open_position" not in conds
        plan = _branch_drive_plan(branch)
        assert plan["target"] == "{{ effective_lockout_position | int }}"
        assert plan["target_tilt"] == "{{ open_tilt_position | int }}"

    def test_contact_opened_sync_branch(self):
        branch = _find_branch_by_alias(
            _load_blueprint_yaml()["actions"],
            "Window opened - Cover already at open position, update win",
        )
        assert branch is not None
        conds = str(branch["conditions"])
        assert "in_lockout_position" in conds
        assert "in_open_position" not in conds

    def test_no_unswapped_open_target_outside_state_targets(self):
        # After the feature, the only plain open-position drive target left is
        # state_targets.opn — every other former site either reads the
        # projection or carries the effective_state == 'lock' swap.
        assert _blueprint_text().count('target: "{{ open_position | int }}"') == 1


# ════════════════════════════════════════════════════════════════════════════
# Lockout-window fall-throughs must not pull the cover down (Bug Pattern AG)
# ════════════════════════════════════════════════════════════════════════════
SWAP = "{{ effective_lockout_position | int if effective_state == 'lock' else open_position | int }}"


class TestLockoutFallThroughTargets:
    """The opening handler is deliberately reachable with the lockout window
    open (Bug Pattern AG routes the lockout morning through "Normal opening"),
    and the shading-end move branch is reachable at the lockout position
    because the shading-end lockout branch gates on current_below_ventilate.
    With a split lockout position both must drive to the lockout target, or
    they would lower the cover onto an open window."""

    @pytest.mark.parametrize(
        "alias",
        [
            "Normal opening of the cover",
            "Move cover after shading end - conditions still valid",
        ],
    )
    def test_target_swaps_to_lockout_when_locked(self, alias):
        branch = _find_branch_by_alias(_load_blueprint_yaml()["actions"], alias)
        assert branch is not None, f"branch not found: {alias!r}"
        seq = str(branch["sequence"])
        assert SWAP in seq, f"{alias}: open-drive target must swap on lock"

    def test_swap_template_semantics(self):
        tmpl = _env().from_string(SWAP)
        # Window open (lock): drive to the lockout position.
        assert (
            tmpl.render(
                effective_state="lock", effective_lockout_position=100, open_position=0
            ).strip()
            == "100"
        )
        # No lockout: plain opening to the open position.
        assert (
            tmpl.render(
                effective_state="opn", effective_lockout_position=100, open_position=0
            ).strip()
            == "0"
        )
        # Input unset (fallback already resolved upstream): identical either way.
        assert (
            tmpl.render(
                effective_state="lock",
                effective_lockout_position=100,
                open_position=100,
            ).strip()
            == "100"
        )
