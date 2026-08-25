"""
Issue #671: opt-in manual schedule adoption.

With `manual_schedule_adoption` enabled for a direction, a manual movement
that the detection classifies as "opened"/"closed" *inside the matching
schedule window* (`is_opening_phase` / `is_closing_phase`) counts as the
scheduled event: the branch advances `bas` and stamps `ts.opn`/`ts.cls`
next to the normal override record (`man: 1`, `ts.man`).

Pinned here:

  1. The input exists, defaults to empty, and offers exactly the two
     direction values; it is bound and projected into `adopt_flags`.
  2. The adoption gate: option + window + an actual base change. No
     environment condition is consulted (the manual move is the authority
     inside the window — the point of #671).
  3. The reducer write: adoption adds exactly `bas` + its timestamp;
     without adoption the write is byte-identical to the plain override
     record. Pending/shading/window/force/resident are never touched
     (Invariant 15's documented exception is `bas` only).
  4. The handler still never drives: no `drive_plan` in the manual branch.

All templates are extracted verbatim from the blueprint.
"""
import ast
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

MANUAL_BRANCH_ALIAS = "Checking for manual position changes"


def _load_blueprint() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


BP = _load_blueprint()


def _find_branch_by_alias(node, alias):
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


def _manual_branch() -> dict:
    branch = _find_branch_by_alias(BP, MANUAL_BRANCH_ALIAS)
    assert branch is not None
    return branch


def _classification_branch(alias: str) -> dict:
    choose = next(step for step in _manual_branch()["sequence"] if "choose" in step)
    branch = next(c for c in choose["choose"] if c.get("alias") == alias)
    return branch["sequence"][0]["variables"]


ENV = jinja2.Environment(undefined=jinja2.StrictUndefined)


def _render_bool(template: str, **ctx) -> bool:
    result = ENV.from_string(template).render(**ctx).strip()
    assert result in ("True", "False"), f"not a boolean render: {result!r}"
    return result == "True"


def _render_dict(template: str, **ctx) -> dict:
    return ast.literal_eval(ENV.from_string(template).render(**ctx).strip())


# ─────────────────────────────────────────────────────────────────────────────
# 1. Input wiring
# ─────────────────────────────────────────────────────────────────────────────


class TestInputWiring:
    def test_input_exists_with_empty_default_and_both_directions(self):
        inputs = BP["blueprint"]["input"]["override_section"]["input"]
        assert "manual_schedule_adoption" in inputs
        definition = inputs["manual_schedule_adoption"]
        assert definition["default"] == []
        values = [o["value"] for o in definition["selector"]["select"]["options"]]
        assert values == ["manual_adopt_opening", "manual_adopt_closing"]

    def test_input_is_bound_and_projected_into_adopt_flags(self):
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        assert "manual_schedule_adoption: !input manual_schedule_adoption" in text
        flags = BP["variables"]["adopt_flags"]
        assert _render_bool(flags["opening"], manual_schedule_adoption=["manual_adopt_opening"])
        assert not _render_bool(flags["opening"], manual_schedule_adoption=[])
        assert _render_bool(flags["closing"], manual_schedule_adoption=["manual_adopt_closing"])
        assert not _render_bool(
            flags["closing"], manual_schedule_adoption=["manual_adopt_opening"]
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. The adoption gate
# ─────────────────────────────────────────────────────────────────────────────


class TestAdoptionGate:
    @pytest.mark.parametrize(
        "alias,flag_key,phase_key,base_other,base_same",
        [
            ("Manual: opened", "opening", "is_opening_phase", "cls", "opn"),
            ("Manual: closed", "closing", "is_closing_phase", "opn", "cls"),
        ],
    )
    def test_gate_requires_option_window_and_base_change(
        self, alias, flag_key, phase_key, base_other, base_same
    ):
        gate = _classification_branch(alias)["adopt_schedule"]

        def render(option: bool, in_phase: bool, base: str) -> bool:
            return _render_bool(
                gate,
                adopt_flags={"opening": False, "closing": False, flag_key: option},
                **{
                    phase_key: in_phase,
                    "helper_state_base": base,
                },
            )

        assert render(True, True, base_other), "all three conditions met -> adopt"
        assert not render(False, True, base_other), "option off -> no adoption"
        assert not render(True, False, base_other), "outside the window -> no adoption"
        assert not render(True, True, base_same), (
            "base already at the target -> no redundant write / ts re-stamp"
        )

    @pytest.mark.parametrize("alias", ["Manual: opened", "Manual: closed"])
    def test_gate_does_not_consult_environment_or_once_guards(self, alias):
        # #671: the manual move is the authority inside the window - a day
        # where brightness/sun never crossed must still adopt.
        gate = _classification_branch(alias)["adopt_schedule"]
        for token in (
            "environment_allows_opening",
            "environment_allows_closing",
            "base_gates",
            "prevent_flags",
        ):
            assert token not in gate, f"{token} must not gate the adoption"

    def test_the_windows_are_the_unified_phase_variables(self):
        # Time-field AND calendar mode both work through is_*_phase; a private
        # re-derivation of the window would silently drop calendar setups.
        opened = _classification_branch("Manual: opened")["adopt_schedule"]
        closed = _classification_branch("Manual: closed")["adopt_schedule"]
        assert "is_opening_phase" in opened and "is_closing_phase" not in opened
        assert "is_closing_phase" in closed and "is_opening_phase" not in closed


# ─────────────────────────────────────────────────────────────────────────────
# 3. The reducer write
# ─────────────────────────────────────────────────────────────────────────────


class TestReducerWrite:
    @pytest.mark.parametrize(
        "alias,base,ts_key",
        [
            ("Manual: opened", "opn", "opn"),
            ("Manual: closed", "cls", "cls"),
        ],
    )
    def test_adoption_adds_exactly_bas_and_its_timestamp(self, alias, base, ts_key):
        update = _classification_branch(alias)["update_values"]
        adopted = _render_dict(update, adopt_schedule=True)
        assert adopted == {
            "man": 1,
            "bas": base,
            "ts": {"man": "now", ts_key: "now"},
        }

    @pytest.mark.parametrize("alias", ["Manual: opened", "Manual: closed"])
    def test_without_adoption_the_write_is_the_plain_override_record(self, alias):
        update = _classification_branch(alias)["update_values"]
        plain = _render_dict(update, adopt_schedule=False)
        assert plain == {"man": 1, "ts": {"man": "now"}}

    @pytest.mark.parametrize("alias", ["Manual: opened", "Manual: closed"])
    def test_pending_and_background_state_stay_untouched(self, alias):
        # Invariant 8/15: manual detection must not clear pending timers or
        # rewrite shading/window/force/resident - adoption included.
        update = _classification_branch(alias)["update_values"]
        for adopt in (True, False):
            rendered = _render_dict(update, adopt_schedule=adopt)
            assert {"shd", "pnd", "win", "frc", "res"}.isdisjoint(rendered)
            assert {"due", "arm", "shd"}.isdisjoint(rendered.get("ts", {}))

    def test_the_manual_branch_still_never_drives(self):
        # The handler has no drive_plan anywhere: apply_transition's default
        # (run: false) keeps this a pure state write.
        branch = _manual_branch()

        def walk(node):
            if isinstance(node, dict):
                assert "drive_plan" not in node
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(branch)

    def test_manual_position_triggers_load_the_calendar_when_adoption_is_on(self):
        # Bug Pattern T family: is_opening_phase/is_closing_phase read the
        # calendar windows, so a calendar-mode adoption needs the load on
        # t_manual_position runs (t_manual_tilt never reaches the opened/
        # closed classification).
        def find_calendar_load(node):
            if isinstance(node, dict):
                if (
                    "if" in node
                    and "calendar.get_events" in str(node.get("then", ""))
                ):
                    return node
                for value in node.values():
                    found = find_calendar_load(value)
                    if found is not None:
                        return found
            elif isinstance(node, list):
                for item in node:
                    found = find_calendar_load(item)
                    if found is not None:
                        return found
            return None

        step = find_calendar_load(BP)
        assert step is not None, "calendar load step not found"
        conditions = str(step["if"])
        assert "t_manual_position" in conditions
        assert "adopt_flags.opening or adopt_flags.closing" in conditions
        assert "t_manual_tilt" not in conditions

    def test_log_user_names_the_adoption(self):
        tail = next(
            step
            for step in _manual_branch()["sequence"]
            if isinstance(step, dict) and "variables" in step and "log_user" in step["variables"]
        )
        template = tail["variables"]["log_user"]
        plain = ENV.from_string(template).render()
        assert plain == "the cover was moved by hand, the automation stands back"
        adopted = ENV.from_string(template).render(adopt_label="opening")
        assert adopted == "the cover was moved by hand and counts as the scheduled opening"
