"""
Tests for tilt-aware status detection (Issue #558).

Two stages are covered:

  Stage 1 — `tilt_position_tolerance`:
    The position checkers (in_open/close/shading/ventilate_position) compare the
    current tilt against the target tilt within an absolute tolerance band instead
    of requiring an exact match. The manual tilt-change detection uses the same
    dead-band so small motor/integration jitter is no longer treated as a manual
    intervention.

  Stage 2 — persisted last-applied shading tilt (`tp`, helper schema v7):
    Shading tilt is computed dynamically from the sun elevation, so an exact
    comparison made in_shading_position go stale whenever the sun moved to a new
    tilt stage. The applied tilt is now persisted in the helper field `tp` and
    in_shading_position compares against it (falling back to the dynamic value when
    tp == -1). helper_update forces tp back to -1 whenever shd transitions to 0.

The in_shading_position template is extracted verbatim from the blueprint and
rendered, so these tests exercise the real logic, not a copy.
"""
import json
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

HELPER_ENTITY = "input_text.cca_status"
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


def _make_env(helper_value: str | None) -> jinja2.Environment:
    states_map = {}
    if helper_value is not None:
        states_map[HELPER_ENTITY] = helper_value

    def states(entity_id):
        return states_map.get(entity_id, "unknown")

    def from_json(value, default=None):
        try:
            return json.loads(value)
        except Exception:
            return {} if default is None else default

    env = jinja2.Environment(undefined=jinja2.Undefined)
    env.globals["states"] = states
    env.filters["from_json"] = from_json
    return env


def _render(template_str: str, env: jinja2.Environment, **variables) -> str:
    return env.from_string(template_str).render(**variables).strip()


def _render_bool(template_str: str, env: jinja2.Environment, **variables) -> bool:
    return _render(template_str, env, **variables) == "True"


# ── helper to build a v7 helper JSON ────────────────────────────────────────
def _helper_json(*, shd=1, tp=-1, win="cls") -> str:
    return json.dumps(
        {
            "bas": "opn", "shd": shd, "pnd": "non", "win": win, "frc": "non",
            "res": 0, "man": 0,
            "ts": {"opn": 0, "cls": 0, "shd": 0, "due": 0, "arm": 0, "man": 0},
            "tp": tp, "v": 7, "t": 0,
        }
    )


def _in_shading_position_template() -> str:
    bp = _load_blueprint_yaml()
    return bp["variables"]["in_shading_position"]


# common variable set for rendering in_shading_position
def _vars(**overrides) -> dict:
    base = dict(
        shading_position=0,
        position_tolerance=0,
        current_position=0,
        is_shading_enabled=True,
        is_cover_tilt_enabled_and_possible=True,
        current_tilt_position=30,
        shading_tilt_position=30,
        tilt_position_tolerance=0,
        cover_status_helper=HELPER_ENTITY,
        invalid_states=INVALID_STATES,
    )
    base.update(overrides)
    return base


# ════════════════════════════════════════════════════════════════════════════
# Stage 1 — tilt_position_tolerance
# ════════════════════════════════════════════════════════════════════════════
class TestTiltToleranceInput:
    def test_input_defined(self):
        text = _blueprint_text()
        assert "tilt_position_tolerance:" in text
        assert "tilt_position_tolerance: !input tilt_position_tolerance" in text

    def test_checkers_use_tolerance_band_not_exact_match(self):
        text = _blueprint_text()
        # The strict `== <x>_tilt_position` comparison must be gone from the checkers.
        assert "current_tilt_position == open_tilt_position" not in text
        assert "current_tilt_position == close_tilt_position" not in text
        assert "current_tilt_position == ventilate_tilt_position" not in text
        assert "current_tilt_position == shading_tilt_position | int" not in text
        # ...replaced by an absolute dead-band against tilt_position_tolerance.
        assert text.count("| abs <= tilt_position_tolerance") >= 4

    def test_manual_tilt_detection_uses_deadband(self):
        text = _blueprint_text()
        assert (
            "current_tilt_position | float(0)) - (trigger.from_state.attributes."
            "current_tilt_position | float(0)) | abs > tilt_position_tolerance"
            in text.replace("\n", " ").replace("  ", " ")
            or "| abs > tilt_position_tolerance" in text
        )
        # Old exact-inequality detection must be gone.
        assert (
            "current_tilt_position != trigger.to_state.attributes.current_tilt_position"
            not in text
        )


class TestInOpenTiltBand:
    """The open-position tilt comparison uses the same band; rendered directly."""

    EXPR = (
        "{{ (current_tilt_position - (open_tilt_position | int)) | abs "
        "<= tilt_position_tolerance }}"
    )

    def test_exact_match_in_position(self):
        env = _make_env(None)
        assert _render_bool(
            self.EXPR, env, current_tilt_position=50, open_tilt_position=50,
            tilt_position_tolerance=0,
        )

    def test_small_drift_within_tolerance(self):
        env = _make_env(None)
        assert _render_bool(
            self.EXPR, env, current_tilt_position=52, open_tilt_position=50,
            tilt_position_tolerance=5,
        )

    def test_drift_beyond_tolerance(self):
        env = _make_env(None)
        assert not _render_bool(
            self.EXPR, env, current_tilt_position=58, open_tilt_position=50,
            tilt_position_tolerance=5,
        )

    def test_zero_tolerance_rejects_any_drift(self):
        env = _make_env(None)
        assert not _render_bool(
            self.EXPR, env, current_tilt_position=51, open_tilt_position=50,
            tilt_position_tolerance=0,
        )


# ════════════════════════════════════════════════════════════════════════════
# Stage 1 — in_shading_position discriminates the issue's overlapping states
# ════════════════════════════════════════════════════════════════════════════
class TestOverlappingPositionsDistinguishedByTilt:
    """Issue #558 example: closed(0,0), shading(0,30), ventilate(0,75)."""

    def test_shading_tilt_matches_is_in_shading(self):
        env = _make_env(_helper_json(shd=1, tp=30))
        tmpl = _in_shading_position_template()
        assert _render_bool(tmpl, env, **_vars(current_tilt_position=30))

    def test_closed_tilt_is_not_in_shading(self):
        # Same position 0, but tilt 0 (closed) — must NOT read as shading.
        env = _make_env(_helper_json(shd=1, tp=30))
        tmpl = _in_shading_position_template()
        assert not _render_bool(tmpl, env, **_vars(current_tilt_position=0))

    def test_ventilate_tilt_is_not_in_shading(self):
        # Same position 0, but tilt 75 (ventilate) — must NOT read as shading.
        env = _make_env(_helper_json(shd=1, tp=30))
        tmpl = _in_shading_position_template()
        assert not _render_bool(tmpl, env, **_vars(current_tilt_position=75))

    def test_tilt_within_tolerance_still_shading(self):
        env = _make_env(_helper_json(shd=1, tp=30))
        tmpl = _in_shading_position_template()
        assert _render_bool(
            tmpl, env, **_vars(current_tilt_position=32, tilt_position_tolerance=3)
        )


# ════════════════════════════════════════════════════════════════════════════
# Stage 2 — in_shading_position compares against persisted tp (not dynamic)
# ════════════════════════════════════════════════════════════════════════════
class TestInShadingPositionUsesPersistedTilt:
    def test_persisted_tp_overrides_changed_dynamic_value(self):
        """
        Sun moved → shading_tilt_position recomputed to 50, but the cover is still
        physically at the previously applied tilt 30 (tp=30). The checker must
        stay True (compare against tp), not go stale against the new dynamic 50.
        """
        env = _make_env(_helper_json(shd=1, tp=30))
        tmpl = _in_shading_position_template()
        assert _render_bool(
            tmpl, env,
            **_vars(current_tilt_position=30, shading_tilt_position=50),
        )

    def test_exact_comparison_would_have_failed(self):
        """Control: comparing the same scenario against the dynamic value is False."""
        env = _make_env(_helper_json(shd=1, tp=-1))  # tp unset → fall back to dynamic
        tmpl = _in_shading_position_template()
        assert not _render_bool(
            tmpl, env,
            **_vars(current_tilt_position=30, shading_tilt_position=50),
        )

    def test_tp_unset_falls_back_to_dynamic(self):
        env = _make_env(_helper_json(shd=1, tp=-1))
        tmpl = _in_shading_position_template()
        assert _render_bool(
            tmpl, env,
            **_vars(current_tilt_position=50, shading_tilt_position=50),
        )

    def test_no_helper_configured_falls_back_to_dynamic(self):
        env = _make_env(None)  # states() → 'unknown'
        tmpl = _in_shading_position_template()
        assert _render_bool(
            tmpl, env,
            **_vars(current_tilt_position=20, shading_tilt_position=20),
        )

    def test_tilt_disabled_ignores_tilt(self):
        env = _make_env(_helper_json(shd=1, tp=30))
        tmpl = _in_shading_position_template()
        # Tilt not possible → only position matters.
        assert _render_bool(
            tmpl, env,
            **_vars(
                is_cover_tilt_enabled_and_possible=False,
                current_tilt_position=99,
            ),
        )


# ════════════════════════════════════════════════════════════════════════════
# Stage 2 — helper_update centrally resets tp when shading clears
# ════════════════════════════════════════════════════════════════════════════
class TestHelperUpdateTpReset:
    EXPR = (
        "{{ -1 if new_shd == 0 else "
        "(updates.tp | default(current.tp | default(-1)) | int) }}"
    )

    def test_shd_zero_forces_minus_one(self):
        env = _make_env(None)
        out = _render(
            self.EXPR, env, new_shd=0, updates={"tp": 30}, current={"tp": 30}
        )
        assert out == "-1"

    def test_shd_one_takes_update(self):
        env = _make_env(None)
        out = _render(
            self.EXPR, env, new_shd=1, updates={"tp": 40}, current={"tp": 10}
        )
        assert out == "40"

    def test_shd_one_preserves_current_when_no_update(self):
        env = _make_env(None)
        out = _render(
            self.EXPR, env, new_shd=1, updates={}, current={"tp": 25}
        )
        assert out == "25"

    def test_default_minus_one_when_absent(self):
        env = _make_env(None)
        out = _render(self.EXPR, env, new_shd=1, updates={}, current={})
        assert out == "-1"


# ════════════════════════════════════════════════════════════════════════════
# Stage 2 — schema wiring
# ════════════════════════════════════════════════════════════════════════════
class TestSchemaV7Wiring:
    def test_schema_bumped_to_v7_everywhere(self):
        text = _blueprint_text()
        assert "'v': 6" not in text, "stale v6 schema marker remains"
        assert text.count("'v': 7") >= 4  # v5-migrate, compact, default, helper_update, empty-init

    def test_helper_update_writes_tp(self):
        text = _blueprint_text()
        assert "'tp': new_tp | int" in text
        assert "set new_tp =" in text

    def test_compact_parse_reads_tp(self):
        text = _blueprint_text()
        assert "helper_raw.tp | default(-1) | int" in text

    def test_migration_check_targets_v7(self):
        text = _blueprint_text()
        assert "helper_raw.v | default(0) != 7" in text

    def test_compact_parse_accepts_v6_and_v7(self):
        text = _blueprint_text()
        assert "helper_raw.v in [6, 7]" in text


class TestShadingDrivesPersistTp:
    """Every auto-shading drive branch records the applied tilt in tp."""

    ALIASES = [
        "Shading detected. Move to shading position",
        "Start Shading",
        "Check for shading tilt",
        "Window closed - Return to shading",
        "Resident leaving: target SHADED",
    ]

    @pytest.mark.parametrize("alias", ALIASES)
    def test_branch_sets_tp(self, alias):
        bp = _load_blueprint_yaml()

        def walk(node):
            if isinstance(node, dict):
                if node.get("alias") == alias:
                    return node
                for v in node.values():
                    r = walk(v)
                    if r is not None:
                        return r
            elif isinstance(node, list):
                for item in node:
                    r = walk(item)
                    if r is not None:
                        return r
            return None

        branch = walk(bp)
        assert branch is not None, f"branch {alias!r} not found"
        update_values = None
        for step in branch.get("sequence", []):
            if isinstance(step, dict) and "variables" in step:
                update_values = step["variables"].get("update_values")
                if update_values is not None:
                    break
        assert update_values is not None, f"no update_values in {alias!r}"
        assert "tp" in update_values, f"branch {alias!r} does not persist tp"
        assert "shading_tilt_position" in str(update_values["tp"])
