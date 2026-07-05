"""
Tests for tilt-aware status detection (Issue #558).

`tilt_position_tolerance`:
  The position checkers (in_open/close/shading/ventilate_position) compare the
  current tilt against the target tilt within an absolute tolerance band instead
  of requiring an exact match. This lets states that share the same cover
  position be told apart by their tilt angle (e.g. closed/shading/ventilate all
  at position 0). The manual tilt-change detection uses the same dead-band so
  small motor/integration jitter is no longer treated as a manual intervention.

The in_shading_position template is extracted verbatim from the blueprint and
rendered, so these tests exercise the real logic, not a copy. in_shading_position
compares against the dynamically computed shading_tilt_position; the last applied
tilt is intentionally NOT persisted in the helper (see the design decision in
CLAUDE.md).
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


def _render_bool(template_str: str, **variables) -> bool:
    return _env().from_string(template_str).render(**variables).strip() == "True"


def _in_shading_position_template() -> str:
    return _load_blueprint_yaml()["variables"]["in_shading_position"]


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
    )
    base.update(overrides)
    return base


# ════════════════════════════════════════════════════════════════════════════
# Input + wiring
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
        assert "| abs > tilt_position_tolerance" in text
        # Old exact-inequality detection must be gone.
        assert (
            "current_tilt_position != trigger.to_state.attributes.current_tilt_position"
            not in text
        )

    def test_no_persisted_tilt_helper_field(self):
        """The last applied tilt is intentionally NOT stored in the helper."""
        text = _blueprint_text()
        assert "'tp'" not in text
        assert "helper_json.tp" not in text
        assert "'v': 7" not in text  # schema stays v6


class TestInOpenTiltBand:
    """The open-position tilt comparison uses the same band; rendered directly."""

    EXPR = (
        "{{ (current_tilt_position - (open_tilt_position | int)) | abs "
        "<= tilt_position_tolerance }}"
    )

    def test_exact_match_in_position(self):
        assert _render_bool(
            self.EXPR, current_tilt_position=50, open_tilt_position=50,
            tilt_position_tolerance=0,
        )

    def test_small_drift_within_tolerance(self):
        assert _render_bool(
            self.EXPR, current_tilt_position=52, open_tilt_position=50,
            tilt_position_tolerance=5,
        )

    def test_drift_beyond_tolerance(self):
        assert not _render_bool(
            self.EXPR, current_tilt_position=58, open_tilt_position=50,
            tilt_position_tolerance=5,
        )

    def test_zero_tolerance_rejects_any_drift(self):
        assert not _render_bool(
            self.EXPR, current_tilt_position=51, open_tilt_position=50,
            tilt_position_tolerance=0,
        )


# ════════════════════════════════════════════════════════════════════════════
# in_shading_position discriminates the issue's overlapping states
# ════════════════════════════════════════════════════════════════════════════
class TestOverlappingPositionsDistinguishedByTilt:
    """Issue #558 example: closed(0,0), shading(0,30), ventilate(0,75)."""

    def test_shading_tilt_matches_is_in_shading(self):
        tmpl = _in_shading_position_template()
        assert _render_bool(tmpl, **_vars(current_tilt_position=30))

    def test_closed_tilt_is_not_in_shading(self):
        # Same position 0, but tilt 0 (closed) — must NOT read as shading.
        tmpl = _in_shading_position_template()
        assert not _render_bool(tmpl, **_vars(current_tilt_position=0))

    def test_ventilate_tilt_is_not_in_shading(self):
        # Same position 0, but tilt 75 (ventilate) — must NOT read as shading.
        tmpl = _in_shading_position_template()
        assert not _render_bool(tmpl, **_vars(current_tilt_position=75))

    def test_tilt_within_tolerance_still_shading(self):
        tmpl = _in_shading_position_template()
        assert _render_bool(
            tmpl, **_vars(current_tilt_position=32, tilt_position_tolerance=3)
        )

    def test_tilt_disabled_ignores_tilt(self):
        tmpl = _in_shading_position_template()
        # Tilt not possible → only position matters.
        assert _render_bool(
            tmpl,
            **_vars(
                is_cover_tilt_enabled_and_possible=False,
                current_tilt_position=99,
            ),
        )

    def test_position_out_of_band_is_not_in_shading(self):
        tmpl = _in_shading_position_template()
        assert not _render_bool(
            tmpl, **_vars(current_position=80, current_tilt_position=30)
        )
