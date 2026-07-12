"""
Tests for the optional Alternate Sun Shading Position feature (Issue #580).

The feature adds a second shading depth (`shading_position_alt`) plus a gating
entity (`shading_position_alt_entity`). While the entity is `on`, the cover
shades to the alternate position; otherwise (or when either input is unset) the
normal `shading_position` is used. The active depth is derived live from the
gating entity via the central `effective_shading_position` variable — no extra
status is persisted in the helper (matches the #558 "helper holds logical state,
not last physical target" decision).

Key properties verified here (real logic extracted from the blueprint, not a
copy):
  - Backward compatibility: with both inputs unset, effective == shading_position.
  - effective_shading_position lives in the FULL `variables:` block, not in
    `trigger_variables:` — it calls states(), which is forbidden in the limited
    trigger context (Invariant 10).
  - All shading drive sites and the position detection use the effective value.
  - The mid-shading re-drive trigger `t_shading_position_alt` provably passes the
    global trigger gate while shading is active (shd == 1).
  - The re-drive branch does NOT touch shd / ts.shd / pnd / ts.due / ts.arm, so
    "shade only once per day" is unaffected (hard constraint from #580).

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

INVALID_STATES = ["", "unavailable", "unknown", "none", "None"]


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


def _env(entity_states: dict | None = None) -> jinja2.Environment:
    """Jinja env with the HA globals/filters/tests the templates rely on."""
    entity_states = entity_states or {}
    env = jinja2.Environment(undefined=jinja2.Undefined)
    env.globals["states"] = lambda e: entity_states.get(e, "unknown")
    env.filters["regex_search"] = (
        lambda value, pattern: re.search(pattern, str(value)) is not None
    )
    env.tests["match"] = (
        lambda value, pattern: re.match(pattern, str(value)) is not None
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


def _find_trigger_by_id(blueprint: dict, trigger_id: str):
    for trg in blueprint.get("triggers", []):
        if isinstance(trg, dict) and trg.get("id") == trigger_id:
            return trg
    return None


def _global_condition_template(blueprint: dict) -> str:
    for cond in blueprint.get("conditions", []):
        if isinstance(cond, dict) and "value_template" in cond:
            return cond["value_template"]
    raise AssertionError("global template condition not found")


def _branch_update_values(branch: dict) -> dict:
    for step in branch.get("sequence", []):
        if isinstance(step, dict) and "variables" in step:
            return step["variables"].get("update_values", {})
    return {}


# ════════════════════════════════════════════════════════════════════════════
# Inputs
# ════════════════════════════════════════════════════════════════════════════
class TestInputs:
    def test_both_inputs_defined(self):
        text = _blueprint_text()
        assert "shading_position_alt:" in text
        assert "shading_position_alt_entity:" in text

    def test_alt_position_is_optional_number_selector(self):
        bp = _load_blueprint_yaml()
        inp = _find_input(bp, "shading_position_alt")
        assert inp["default"] == []
        assert inp["selector"]["number"]["min"] == 0.0
        assert inp["selector"]["number"]["max"] == 100.0

    def test_alt_entity_is_optional_and_domain_restricted(self):
        bp = _load_blueprint_yaml()
        inp = _find_input(bp, "shading_position_alt_entity")
        assert inp["default"] == []
        domains = inp["selector"]["entity"]["domain"]
        assert set(domains) == {"binary_sensor", "input_boolean"}


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


# ════════════════════════════════════════════════════════════════════════════
# effective_shading_position — the central mechanism
# ════════════════════════════════════════════════════════════════════════════
class TestEffectiveShadingPosition:
    @pytest.fixture(scope="class")
    def tmpl(self):
        return _load_blueprint_yaml()["variables"]["effective_shading_position"]

    def _render(self, tmpl, *, alt, entity, entity_state, normal=25):
        states = {entity: entity_state} if entity != [] else {}
        out = (
            _env(states)
            .from_string(tmpl)
            .render(
                shading_position_alt=alt,
                shading_position_alt_entity=entity,
                shading_position=normal,
            )
            .strip()
        )
        return int(out)

    def test_disabled_falls_back_to_normal(self, tmpl):
        # Both unset — byte-for-byte the old behavior.
        assert self._render(tmpl, alt=[], entity=[], entity_state="off") == 25

    def test_alt_unset_entity_set_uses_normal(self, tmpl):
        assert (
            self._render(tmpl, alt=[], entity="input_boolean.x", entity_state="on")
            == 25
        )

    def test_entity_unset_alt_set_uses_normal(self, tmpl):
        assert self._render(tmpl, alt=60, entity=[], entity_state="on") == 25

    def test_entity_on_uses_alternate(self, tmpl):
        assert (
            self._render(tmpl, alt=60, entity="input_boolean.x", entity_state="on")
            == 60
        )

    def test_entity_off_uses_normal(self, tmpl):
        assert (
            self._render(tmpl, alt=60, entity="input_boolean.x", entity_state="off")
            == 25
        )

    def test_lives_in_variables_not_trigger_variables(self):
        """states() is forbidden in trigger_variables (Invariant 10)."""
        bp = _load_blueprint_yaml()
        assert "effective_shading_position" in bp["variables"]
        assert "effective_shading_position" not in bp["trigger_variables"]

    def test_defined_before_its_consumers(self):
        keys = list(_load_blueprint_yaml()["variables"].keys())
        assert keys.index("effective_shading_position") < keys.index(
            "position_comparisons"
        )
        assert keys.index("effective_shading_position") < keys.index(
            "in_shading_position"
        )


# ════════════════════════════════════════════════════════════════════════════
# Consumers use the effective value, not the raw shading_position
# ════════════════════════════════════════════════════════════════════════════
class TestConsumersUseEffective:
    def test_in_shading_position_uses_effective(self):
        tmpl = _load_blueprint_yaml()["variables"]["in_shading_position"]
        # The tolerance band is computed against the effective (not the raw) depth.
        assert "effective_shading_position - position_tolerance" in tmpl
        assert "effective_shading_position + position_tolerance" in tmpl

    def test_all_shading_position_comparisons_use_effective(self):
        pc = _load_blueprint_yaml()["variables"]["position_comparisons"]
        # Every comparison that involves the shading depth must reflect the
        # effective (normal/alternate) position, per the maintainer's #580 note.
        shading_keys = [k for k, v in pc.items() if "shading_position" in v]
        assert shading_keys, "expected shading-related position comparisons"
        for key in shading_keys:
            assert "effective_shading_position" in pc[key], key
            # No bare (non-effective) shading_position must remain.
            assert not re.search(r"(?<!effective_)shading_position", pc[key]), key

    def test_all_nine_drive_sites_plus_redrive_use_effective(self):
        text = _blueprint_text()
        # 9 original drive sites + the new re-drive branch = 10.
        assert (
            text.count('target_position: "{{ effective_shading_position | int }}"')
            == 10
        )
        # No drive site still hard-wires the raw input.
        assert "target_position: !input shading_position" not in text

    def test_start_shading_guard_compares_against_effective(self):
        text = _blueprint_text()
        assert "current_position == effective_shading_position" in text
        assert "current_position == shading_position " not in text

    def test_ventilation_floor_gate_uses_effective(self):
        """Bug Pattern AE floor must bind on the *active* depth (#580 follow-up).

        The maintainer's #580 comment lists shading_below_ventilate among the
        position_comparisons that must reflect the effective position; otherwise
        the ventilation floor (window tilted) breaks when the alternate depth
        sits on the opposite side of the ventilate position.
        """
        pc = _load_blueprint_yaml()["variables"]["position_comparisons"]
        tmpl = pc["shading_below_ventilate"]
        assert "effective_shading_position" in tmpl

        def below(effective, ventilate, is_awning=False):
            return (
                _env()
                .from_string(tmpl)
                .render(
                    effective_shading_position=effective,
                    ventilate_position=ventilate,
                    is_awning=is_awning,
                )
                .strip()
                == "True"
            )

        # Blind (0 % = closed): "below" means a numerically smaller position.
        assert below(30, 50) is True  # alt depth below vent → floor binds
        assert below(60, 50) is False  # alt depth above vent → floor must NOT bind
        # Awning (0 % = retracted): inverted.
        assert below(60, 50, is_awning=True) is True
        assert below(30, 50, is_awning=True) is False

    def test_shading_above_close_gate_uses_effective(self):
        """Close-time "lowering blocked if shaded" gate reflects the active depth."""
        pc = _load_blueprint_yaml()["variables"]["position_comparisons"]
        tmpl = pc["shading_above_close"]
        assert "effective_shading_position" in tmpl

        def above(effective, close, is_awning=False):
            return (
                _env()
                .from_string(tmpl)
                .render(
                    effective_shading_position=effective,
                    close_position=close,
                    is_awning=is_awning,
                )
                .strip()
                == "True"
            )

        # Blind: shading "above" close means a numerically larger position.
        assert above(20, 10) is True  # alt depth above close
        assert above(5, 10) is False  # alt depth below close


# ════════════════════════════════════════════════════════════════════════════
# Mid-shading re-drive trigger
# ════════════════════════════════════════════════════════════════════════════
class TestReDriveTrigger:
    def test_trigger_defined_as_state_with_not_to_guard(self):
        trg = _find_trigger_by_id(_load_blueprint_yaml(), "t_shading_position_alt")
        assert trg is not None
        assert trg["trigger"] == "state"
        assert set(trg["not_to"]) == {"unavailable", "unknown"}

    def test_trigger_enabled_gate(self):
        trg = _find_trigger_by_id(_load_blueprint_yaml(), "t_shading_position_alt")
        gate = trg["enabled"]
        assert "is_shading_enabled" in gate
        assert "shading_position_alt_entity != []" in gate
        assert "cover_status_helper != []" in gate

    @pytest.mark.parametrize(
        "helper, expected",
        [
            # Shading active — the re-drive MUST be allowed through.
            ('{"shd":1,"pnd":"non","ts":{"shd":1779701945}}', True),
            # Shading inactive — no re-drive needed, but the gate does not
            # single this trigger out either (falls into the else->true branch).
            ('{"shd":0,"pnd":"non","ts":{"shd":0}}', True),
        ],
    )
    def test_passes_global_gate(self, helper, expected):
        bp = _load_blueprint_yaml()
        tmpl = _global_condition_template(bp)
        result = (
            _env({"input_text.cca": helper})
            .from_string(tmpl)
            .render(
                trigger={"id": "t_shading_position_alt"},
                cover_status_helper="input_text.cca",
                invalid_states=INVALID_STATES,
            )
            .strip()
            .lower()
        )
        assert (result == "true") is expected

    def test_gate_still_suppresses_start_pending_while_shaded(self):
        """Sanity: the harness really evaluates the gate (contrast case)."""
        bp = _load_blueprint_yaml()
        tmpl = _global_condition_template(bp)
        shaded = '{"shd":1,"pnd":"non","ts":{"shd":1779701945}}'
        result = (
            _env({"input_text.cca": shaded})
            .from_string(tmpl)
            .render(
                trigger={"id": "t_shading_start_pending_1"},
                cover_status_helper="input_text.cca",
                invalid_states=INVALID_STATES,
            )
            .strip()
            .lower()
        )
        # shd==1 and no end-pending → start-pending is suppressed.
        assert result == "false"


# ════════════════════════════════════════════════════════════════════════════
# Re-drive branch — must not look like a shading start
# ════════════════════════════════════════════════════════════════════════════
class TestReDriveBranch:
    ALIAS = "Check for alternate shading position"

    @pytest.fixture(scope="class")
    def branch(self):
        b = _find_branch_by_alias(_load_blueprint_yaml()["actions"], self.ALIAS)
        assert b is not None, "re-drive branch not found"
        return b

    def test_gated_on_its_own_trigger(self, branch):
        conds = str(branch["conditions"])
        assert "t_shading_position_alt" in conds

    def test_gated_on_active_shading_only(self, branch):
        conds = str(branch["conditions"])
        assert "helper_state_is_shaded" in conds
        assert "not helper_state_pending_start" in conds

    def test_gated_on_force_resident_and_override(self, branch):
        conds = str(branch["conditions"])
        assert "force_allows_shade" in conds
        assert "resident_flags.allow_shade" in conds
        assert "helper_state_manual and override_flags.shading" in conds

    def test_lockout_window_checks_present(self, branch):
        conds = str(branch["conditions"])
        assert "contact_window_opened" in conds
        assert "contact_window_tilted" in conds

    def test_drives_position_via_effective(self, branch):
        seq = str(branch["sequence"])
        assert "effective_shading_position" in seq

    def test_does_not_touch_shading_start_state(self, branch):
        """Hard constraint #580.2: a depth change is NOT a new shading start."""
        uv = _branch_update_values(branch)
        for forbidden in ("shd", "pnd", "ts"):
            assert forbidden not in uv, (
                f"re-drive must not set '{forbidden}' — would corrupt the "
                f"shade-once-per-day guard / pending state"
            )
        # It may only (optionally) reset the manual flag when it actually drives.
        assert set(uv.keys()) <= {"man"}
