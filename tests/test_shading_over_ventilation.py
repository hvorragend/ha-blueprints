"""Tests for the optional "sun shading beats the ventilation floor" option.

By default VENT (priority 4) outranks SHADING (priority 6): a tilted window caps
the cover at the ventilation position instead of letting it drop to the shading
position. That is harmless with the stock positions (ventilate 30, shading 25),
but it silently disables shading altogether when the ventilation position sits far
above the shading position (e.g. a terrace door at 95 vs. shading at 35).

The `shading_over_ventilation` option in `auto_ventilate_options` inverts exactly
that one pair. Everything else keeps the ventilation floor:
  - LOCKOUT (window fully open) is a safety feature and stays on top.
  - PRIVACY-close and BASE=CLS keep the floor - the option is about shading only.
  - With the option off, every outcome is byte-for-byte the old behaviour.

Verified here against the real templates/branches from the blueprint:
  - the cascade (`effective_state`) and its recovery mirror (`recovered_state`),
  - the shading-start vent-floor branch stands down,
  - the contact handler keeps the shading position instead of raising the cover,
  - the shading tilt / alternate-depth branches keep running while tilted.

Run with: pytest tests/ -v
"""
import pathlib

import jinja2
import pytest
import yaml


BLUEPRINT_PATH = (
    pathlib.Path(__file__).parent.parent
    / "blueprints"
    / "automation"
    / "cover_control_automation.yaml"
)

VENT_FLOOR_ALIAS = "Shading start - hold ventilation floor (window tilted)"
SHADING_FIRST_ALIAS = "Window tilted - Sun shading takes precedence"
PARTIAL_VENT_ALIAS = "Window tilted - Partial ventilation"
SHADING_TILT_ALIAS = "Check for shading tilt"
SHADING_ALT_ALIAS = "Check for alternate shading position"

TILTED_GATE = "not window_opened_now and (not window_tilted_now or shading_over_ventilation)"


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


def _find_variable_definition(node, name: str):
    if isinstance(node, dict):
        if name in node and not isinstance(node[name], (dict, list)):
            return node[name]
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


def _render(template: str, entity_states: dict, **variables) -> str:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.globals["states"] = lambda entity_id: entity_states.get(entity_id, "unknown")
    return env.from_string(template).render(**variables).strip()


# ─────────────────────────────────────────────────────────────────────────────
# The cascade
# ─────────────────────────────────────────────────────────────────────────────


class TestCascade:
    """effective_state with a tilted window and shading active."""

    def _state(self, *, shd=1, bas="opn", frc="non", opened=False, tilted=True,
               option=False, present=False, cfg=None, sched=True):
        helper = {"bas": bas, "shd": shd, "frc": frc, "win": "cls", "res": 0,
                  "man": 0, "pnd": "non"}
        entities = {
            "binary_sensor.opened": "on" if opened else "off",
            "binary_sensor.tilted": "on" if tilted else "off",
        }
        return _render(
            BP["variables"]["effective_state"], entities,
            helper_json=helper,
            resident_config=cfg if cfg is not None else [],
            state_resident=present,
            contact_window_opened="binary_sensor.opened",
            contact_window_tilted="binary_sensor.tilted",
            is_ventilation_enabled=True,
            is_opening_scheduled=sched,
            shading_over_ventilation=option,
        )

    def test_default_keeps_the_ventilation_floor(self):
        """Unchanged behaviour: tilted window caps the shading at the vent position."""
        assert self._state(bas="cls", option=False) == "vnt"

    def test_option_lets_the_shading_win(self):
        assert self._state(bas="cls", option=True) == "shd"

    def test_option_does_not_change_anything_without_shading(self):
        assert self._state(shd=0, bas="cls", option=True) == "vnt"

    def test_open_window_still_wins(self):
        """LOCKOUT is a safety feature and outranks the option."""
        assert self._state(bas="cls", opened=True, option=True) == "lock"

    def test_force_still_wins(self):
        assert self._state(bas="cls", frc="opn", option=True) == "opn"

    def test_privacy_close_keeps_the_floor(self):
        """The option covers VENT vs. SHADING only - a privacy close still ventilates."""
        assert self._state(shd=0, bas="opn", option=True, present=True,
                           cfg=["resident_closing_enabled",
                                "resident_allow_ventilation"]) == "vnt"

    def test_resident_shading_ban_keeps_the_floor(self):
        """Without allow_shade the base target is not 'shd', so the floor applies."""
        assert self._state(bas="cls", option=True, present=True,
                           cfg=["resident_allow_ventilation"]) == "vnt"

    def test_scheduled_opening_still_beats_everything_below(self):
        """base=opn with a real opening schedule and no shading: unchanged (#553/AL)."""
        assert self._state(shd=0, bas="opn", option=True) == "opn"

    def test_closed_window_is_unaffected(self):
        assert self._state(bas="cls", tilted=False, option=True) == "shd"


class TestRecoveryMirror:
    """recovered_state must reach the same verdict (Invariant 13). The exhaustive
    parity sweep lives in test_restart_recovery.TestCascadeParity; this is the
    explicit spot check for the new option."""

    def _recovered(self, *, option, shade=True, base="cls"):
        recovery = _find_branch_by_alias(
            BP["actions"], "Recovery: apply the additional condition to a caught-up base flip"
        )
        template = _find_variable_definition(recovery, "recovered_state")
        assert template is not None
        return _render(
            template, {},
            live_force="non",
            new_base=base,
            recovered_window="tlt",
            recovered_shade=shade,
            state_resident=False,
            is_opening_scheduled=True,
            resident_flags={"closing_trigger": False, "allow_open": True,
                            "allow_shade": True, "allow_ventilate": True},
            shading_over_ventilation=option,
        )

    def test_recovery_keeps_the_floor_by_default(self):
        assert self._recovered(option=False) == "vnt"

    def test_recovery_follows_the_option(self):
        assert self._recovered(option=True) == "shd"


# ─────────────────────────────────────────────────────────────────────────────
# The branches that act on the cascade
# ─────────────────────────────────────────────────────────────────────────────


class TestInputOption:
    def test_option_offered_in_the_ventilation_options(self):
        selector = (
            BP["blueprint"]["input"]["contacts_section"]["input"]
            ["auto_ventilate_options"]["selector"]["select"]
        )
        assert "shading_over_ventilation" in [o["value"] for o in selector["options"]]

    def test_flag_lives_in_trigger_variables(self):
        """The cascade reads it, so it must be resolved before the action scope -
        and it is pure list membership, which the limited context allows (Invariant 10)."""
        assert "shading_over_ventilation" in BP["trigger_variables"]
        assert "states(" not in BP["trigger_variables"]["shading_over_ventilation"]
        assert "shading_over_ventilation" not in BP["variables"]

    def test_default_is_off(self):
        """No option configured = the ventilation floor, exactly as before."""
        template = BP["trigger_variables"]["shading_over_ventilation"]
        assert _render(template, {}, auto_ventilate_options=[]) == "False"


class TestShadingStartBranch:
    def test_vent_floor_branch_stands_down(self):
        branch = _find_branch_by_alias(BP["actions"], VENT_FLOOR_ALIAS)
        assert branch is not None
        assert "{{ not shading_over_ventilation }}" in branch["conditions"]

    def test_vent_floor_branch_still_gated_on_the_position_relation(self):
        """Untouched: without the option the floor only applies when the shading
        position is actually below the ventilation position."""
        branch = _find_branch_by_alias(BP["actions"], VENT_FLOOR_ALIAS)
        assert "{{ position_comparisons.shading_below_ventilate }}" in branch["conditions"]


class TestContactHandler:
    def test_shading_first_branch_exists(self):
        assert _find_branch_by_alias(BP["actions"], SHADING_FIRST_ALIAS) is not None

    def test_shading_first_branch_precedes_the_ventilation_branch(self):
        """A choose: is first-match - the new leaf must sit above the vent leaf."""
        text = _blueprint_text()
        assert text.index(SHADING_FIRST_ALIAS) < text.index(PARTIAL_VENT_ALIAS)

    def test_shading_first_branch_is_scoped(self):
        branch = _find_branch_by_alias(BP["actions"], SHADING_FIRST_ALIAS)
        conds = branch["conditions"]
        assert "{{ shading_over_ventilation }}" in conds
        assert "{{ contact_tilted_now }}" in conds
        assert "{{ not contact_opened_now }}" in conds       # Invariant 5
        assert "{{ effective_state == 'shd' }}" in conds

    def test_shading_first_branch_drives_to_the_shading_target(self):
        branch = _find_branch_by_alias(BP["actions"], SHADING_FIRST_ALIAS)
        variables = branch["sequence"][0]["variables"]
        assert "state_targets.shd" in str(variables["drive_plan"])
        assert variables["will_drive"] == "{{ state_gates.shd }}"
        # Invariant 1: no position check in the branch conditions
        assert "in_shading_position" not in str(branch["conditions"])

    def test_shading_first_branch_records_the_window_and_follows_invariant_7(self):
        branch = _find_branch_by_alias(BP["actions"], SHADING_FIRST_ALIAS)
        update = branch["sequence"][0]["variables"]["update_values"]
        assert update["win"] == "tlt"
        assert update["man"] == "{{ 0 if will_drive else helper_json.man | default(0) | int }}"
        # Invariant 8: a contact-handler branch must not touch the pending keys
        assert "pnd" not in update and "ts" not in update

    def test_shading_first_branch_ends_in_apply_transition(self):
        """Invariant 2 - also enforced structurally by test_apply_transition_architecture."""
        branch = _find_branch_by_alias(BP["actions"], SHADING_FIRST_ALIAS)
        assert any("apply_transition" in str(step) or "delay" in str(step)
                   for step in branch["sequence"][1:])


class TestShadingFollowUpBranches:
    """Tilt stage and alternate depth must keep tracking while the window is tilted -
    otherwise the shading would freeze at the depth it started with."""

    @pytest.mark.parametrize("alias", [SHADING_TILT_ALIAS, SHADING_ALT_ALIAS])
    def test_tilted_window_only_blocks_without_the_option(self, alias):
        branch = _find_branch_by_alias(BP["actions"], alias)
        assert branch is not None
        assert f"{{{{ {TILTED_GATE} }}}}" in branch["conditions"]

    @pytest.mark.parametrize("alias", [SHADING_TILT_ALIAS, SHADING_ALT_ALIAS])
    def test_open_window_always_blocks(self, alias):
        """The gate must stay false for a fully open window, option or not."""
        branch = _find_branch_by_alias(BP["actions"], alias)
        gate = next(c for c in branch["conditions"] if "window_opened_now" in str(c))
        for option in (False, True):
            assert _render(gate, {}, window_opened_now=True, window_tilted_now=False,
                           shading_over_ventilation=option) == "False"
