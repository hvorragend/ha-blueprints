"""
Tests for the "Tilt First, Then Position (Somfy J4 IO)" tilt wait mode
(Issues #355 / #612).

These motors reject tilt commands while fully open, force their tilt target
to 100/0 on open_cover/close_cover, and restore the last tilt target after
every positioning run. The mode therefore drives in three steps:

  1. Preliminary alignment (inside &drive_with_actions, before the cover
     move): a cover at the fully-open endpoint is briefly started downwards
     (so tilt commands are accepted again), otherwise the slats are
     pre-tilted to the travel direction (0 down / 100 up).
  2. &cover_move_action avoids the open_cover/close_cover shortcuts unless
     the tilt target matches their implicit tilt (100/0).
  3. &tilt_move_action sends the final tilt after the movement and waits for
     the cover to become idle first (like wait_idle mode).

The condition templates are extracted verbatim from the blueprint and
rendered, so these tests exercise the real logic, not a copy.
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


def _load_blueprint_yaml() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor(
        "!input", lambda loader, node: loader.construct_scalar(node)
    )
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


def _anchors() -> dict:
    return _load_blueprint_yaml()["actions"][0]["variables"]


def _render_bool(template: str, variables: dict) -> bool:
    env = jinja2.Environment(undefined=jinja2.Undefined)
    rendered = env.from_string(template).render(**variables).strip()
    assert rendered in ("True", "False"), rendered
    return rendered == "True"


def _align_step(drive_with_actions: dict) -> dict:
    for step in drive_with_actions["sequence"]:
        if isinstance(step, dict) and "alignment" in str(step.get("alias", "")):
            return step
    raise AssertionError("preliminary tilt alignment step missing")


def _align_branches(align_step: dict) -> list[dict]:
    repeat_seq = align_step["then"][0]["repeat"]["sequence"]
    inner = repeat_seq[0]["then"]
    choose_step = next(s for s in inner if isinstance(s, dict) and "choose" in s)
    return choose_step["choose"]


def _cover_move_branches(cover_move_action: dict) -> list[dict]:
    for step in cover_move_action["sequence"]:
        if isinstance(step, dict) and "repeat" in step:
            return step["repeat"]["sequence"][0]["choose"]
    raise AssertionError("cover move choose block missing")


def _first_matching(branches: list[dict], variables: dict) -> str | None:
    for branch in branches:
        if _render_bool(branch["conditions"], variables):
            return branch["alias"]
    return None


class TestDriveOrder:
    """Alignment runs first, then the cover move, then the final tilt."""

    def test_alignment_before_cover_move_before_tilt_move(self):
        anchors = _anchors()
        seq = anchors["drive_with_actions"]["sequence"]
        align_idx = next(
            i for i, s in enumerate(seq)
            if isinstance(s, dict) and "alignment" in str(s.get("alias", ""))
        )
        cover_idx = next(
            i for i, s in enumerate(seq) if s is anchors["cover_move_action"]
        )
        tilt_idx = next(
            i for i, s in enumerate(seq) if s is anchors["tilt_move_action"]
        )
        assert align_idx < cover_idx < tilt_idx

    def test_alignment_is_gated_on_the_mode(self):
        align = _align_step(_anchors()["drive_with_actions"])
        assert "is_tilt_before_position_mode" in str(align["if"][0])
        assert "is_cover_tilt_enabled_and_possible" in str(align["if"][0])

    def test_alignment_re_reads_pause_and_hand_over_live(self):
        align = _align_step(_anchors()["drive_with_actions"])
        gate = str(align["if"][1])
        assert "states(force_pause)" in gate
        assert "instance_active_on_states" in gate

    def test_alignment_skipped_when_position_will_not_change(self):
        align = _align_step(_anchors()["drive_with_actions"])
        tolerance_gate = str(align["if"][2])
        assert not _render_bool(
            tolerance_gate,
            {"target_position": 40, "current_position": 40, "position_tolerance": 0},
        )
        assert _render_bool(
            tolerance_gate,
            {"target_position": 20, "current_position": 40, "position_tolerance": 0},
        )


class TestPreliminaryAlignment:
    """Fully open -> brief close; otherwise pre-tilt to the travel direction."""

    def _pick(self, align_position: int, target_position: int) -> str | None:
        branches = _align_branches(_align_step(_anchors()["drive_with_actions"]))
        return _first_matching(
            branches,
            {"align_position": align_position, "target_position": target_position},
        )

    def test_fully_open_cover_is_briefly_started_downwards(self):
        assert self._pick(100, 30) == "Tilt align: leave the fully-open endpoint"

    def test_fully_open_wins_even_for_a_full_close(self):
        assert self._pick(100, 0) == "Tilt align: leave the fully-open endpoint"

    def test_moving_down_pre_tilts_closed(self):
        assert self._pick(60, 20) == "Tilt align: close slats before moving down"

    def test_moving_up_pre_tilts_open(self):
        assert self._pick(20, 80) == "Tilt align: open slats before moving up"

    def test_branch_actions_match_their_alias(self):
        branches = _align_branches(_align_step(_anchors()["drive_with_actions"]))
        by_alias = {b["alias"]: str(b["sequence"]) for b in branches}
        assert "cover.close_cover" in by_alias["Tilt align: leave the fully-open endpoint"]
        assert "'tilt_position': 0}" in by_alias["Tilt align: close slats before moving down"]
        assert "'tilt_position': 100}" in by_alias["Tilt align: open slats before moving up"]


class TestCoverMoveShortcutRestriction:
    """open_cover/close_cover overwrite the motor's tilt target with 100/0 —
    in tilt-before-position mode they are only allowed when the tilt target
    matches (or no tilt target / no tilt support exists)."""

    def _pick(self, *, mode: bool, tilt_possible: bool = True,
              target: int, target_tilt: int = 101) -> str | None:
        branches = _cover_move_branches(_anchors()["cover_move_action"])
        return _first_matching(
            branches,
            {
                "is_tilt_before_position_mode": mode,
                "is_cover_tilt_enabled_and_possible": tilt_possible,
                "target_position": target,
                "target_tilt_position": target_tilt,
            },
        )

    def test_default_mode_keeps_the_shortcuts(self):
        assert self._pick(mode=False, target=0, target_tilt=50) == "Cover move: full close"
        assert self._pick(mode=False, target=100, target_tilt=50) == "Cover move: full open"
        assert self._pick(mode=False, target=40) == "Cover move: position command (0-100)"

    def test_mismatching_tilt_target_forces_a_position_command(self):
        assert self._pick(mode=True, target=0, target_tilt=50) == "Cover move: position command (0-100)"
        assert self._pick(mode=True, target=100, target_tilt=50) == "Cover move: position command (0-100)"

    def test_matching_or_absent_tilt_target_keeps_the_shortcuts(self):
        assert self._pick(mode=True, target=0, target_tilt=0) == "Cover move: full close"
        assert self._pick(mode=True, target=100, target_tilt=100) == "Cover move: full open"
        assert self._pick(mode=True, target=0) == "Cover move: full close"
        assert self._pick(mode=True, target=100) == "Cover move: full open"

    def test_without_tilt_support_the_shortcuts_stay(self):
        assert self._pick(mode=True, tilt_possible=False, target=0, target_tilt=50) == "Cover move: full close"
        assert self._pick(mode=True, tilt_possible=False, target=100, target_tilt=50) == "Cover move: full open"

    def test_no_target_matches_no_branch(self):
        assert self._pick(mode=True, target=101) is None
        assert self._pick(mode=False, target=101) is None


class TestFinalTiltWaitsForIdle:
    """The final tilt runs after the position command in this mode, so it
    must wait for the cover to stop — same branch as wait_idle mode."""

    def _wait_branches(self) -> list[dict]:
        anchor = _anchors()["tilt_move_action"]
        repeat_seq = anchor["sequence"][-1]["repeat"]["sequence"]
        inner = repeat_seq[0]["then"]
        choose_step = next(
            s for s in inner
            if isinstance(s, dict) and "choose" in s and "Tilt wait" in str(s)
        )
        return choose_step["choose"]

    @pytest.mark.parametrize(
        ("idle_mode", "before_position_mode", "expect_wait"),
        [(True, False, True), (False, True, True), (False, False, False)],
    )
    def test_wait_branch_selection(self, idle_mode, before_position_mode, expect_wait):
        branch = next(
            b for b in self._wait_branches()
            if b["alias"] == "Tilt wait: until movement stops"
        )
        matched = _render_bool(
            branch["conditions"],
            {
                "is_tilt_wait_idle_mode": idle_mode,
                "is_tilt_before_position_mode": before_position_mode,
            },
        )
        assert matched is expect_wait

    def test_no_skip_branch_remains(self):
        aliases = [b["alias"] for b in self._wait_branches()]
        assert aliases == ["Tilt wait: until movement stops"]


class TestPrerenderGuards:
    """Invariant 14: the alignment block lives inside an anchor body that is
    pre-rendered on every run — every runtime-context reference must be
    guarded so the anchor-definition step cannot raise."""

    def test_alignment_templates_survive_prerender_without_runtime_context(self):
        align = _align_step(_anchors()["drive_with_actions"])

        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        env.globals["states"] = lambda e: "unknown"
        env.globals["state_attr"] = lambda e, a: None

        globals_only = {
            "is_tilt_before_position_mode": False,
            "is_cover_tilt_enabled_and_possible": False,
            "prevent_flags": {"default_cover_actions": False},
            "force_pause": [],
            "instance_active": [],
            "instance_active_on_states": ["on", "true"],
            "current_position": 101,
            "position_tolerance": 0,
            "blind_entities": [],
        }

        def render_all(node):
            if isinstance(node, str) and "{{" in node:
                env.from_string(node).render(**globals_only)
            elif isinstance(node, dict):
                for value in node.values():
                    render_all(value)
            elif isinstance(node, list):
                for item in node:
                    render_all(item)

        render_all(align)
