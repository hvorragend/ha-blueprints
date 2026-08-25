"""
Bug Pattern AX: manual moves on covers that report intermediate positions
while travelling must not be swallowed by the per-step drift dead-band.

`t_manual_position` carries `for: 60`; on an attribute trigger every
intermediate position report re-arms the timer with a fresh from/to pair, so
at fire time `trigger.from_state` is the PENULTIMATE report of the travel.
The Bug Pattern Q dead-band therefore measures only the final reporting step
(e.g. 97 -> 100 of a full manual open), which on granular covers is within
`position_tolerance` - the whole hand movement classified as drift and the
run fell through to "No operational branch matched" with no helper write.

Fix under test: each cover-attribute source alternatively accepts the event
when `trigger.from_state.state in ['opening', 'closing']` - a from_state
captured mid-travel proves a real motor movement, which outside the drive
settle window (keyed on `d`, Bug Pattern AP) is never CCA's own drive and
never idle drift.

The condition tree is extracted verbatim from the blueprint and evaluated
with mocked trigger objects.
"""
import pathlib

import pytest
import yaml

from conftest import eval_condition, make_jinja_env


BLUEPRINT_PATH = (
    pathlib.Path(__file__).parent.parent
    / "blueprints"
    / "automation"
    / "cover_control_automation.yaml"
)

INVALID_STATES = ["", "unavailable", "unknown", "none", "None", "null", "query failed", []]

MANUAL_BRANCH_ALIAS = "Checking for manual position changes"


def _load_blueprint() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


def _walk(node, predicate):
    if predicate(node):
        return node
    if isinstance(node, dict):
        for value in node.values():
            found = _walk(value, predicate)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _walk(item, predicate)
            if found is not None:
                return found
    return None


BP = _load_blueprint()

MANUAL_BRANCH = _walk(
    BP,
    lambda n: isinstance(n, dict)
    and n.get("alias") == MANUAL_BRANCH_ALIAS
    and "conditions" in n,
)
assert MANUAL_BRANCH is not None


def _source_group(marker: str) -> dict:
    """The and-group of the source-selection OR that mentions `marker`."""
    source_or = next(
        c for c in MANUAL_BRANCH["conditions"] if isinstance(c, dict) and "or" in c
    )
    for group in source_or["or"]:
        assert isinstance(group, dict) and "and" in group
        if any(marker in str(item) for item in group["and"]):
            return group
    raise AssertionError(f"no source group mentions {marker!r}")


def _make_env():
    env = make_jinja_env()
    env.filters["abs"] = abs
    env.globals["is_number"] = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    return env


def _eval_tree(env, cond, variables) -> bool:
    if isinstance(cond, str):
        return eval_condition(env, cond, variables)
    if isinstance(cond, dict):
        if "or" in cond:
            return any(_eval_tree(env, c, variables) for c in cond["or"])
        if "and" in cond:
            return all(_eval_tree(env, c, variables) for c in cond["and"])
    raise AssertionError(f"unsupported condition node: {cond!r}")


def _vars(attr: str, source: str, from_pos, to_pos, from_state: str, to_state: str,
          tolerance: int = 3) -> dict:
    return {
        "trigger": {
            "id": "t_manual_position",
            "attribute": attr,
            "from_state": {"state": from_state, "attributes": {attr: from_pos}},
            "to_state": {"state": to_state, "attributes": {attr: to_pos}},
        },
        "position_source": source,
        "position_tolerance": tolerance,
        "invalid_states": INVALID_STATES,
    }


@pytest.mark.parametrize(
    ("attr", "source"),
    [("current_position", "current_position_attr"), ("position", "position_attr")],
)
class TestMovementStateDisjunct:
    def test_granular_travel_final_step_detected(self, attr, source):
        """97 -> 100 (delta 3 <= tolerance) with a mid-travel from_state IS manual."""
        env = _make_env()
        group = _source_group(f"'{source}'")
        assert _eval_tree(env, group, _vars(attr, source, 97, 100, "opening", "open"))

    def test_granular_close_final_step_detected(self, attr, source):
        env = _make_env()
        group = _source_group(f"'{source}'")
        assert _eval_tree(env, group, _vars(attr, source, 2, 0, "closing", "closed"))

    def test_idle_drift_still_ignored(self, attr, source):
        """Bug Pattern Q preserved: 58 -> 59 with the cover idle is drift."""
        env = _make_env()
        group = _source_group(f"'{source}'")
        assert not _eval_tree(env, group, _vars(attr, source, 58, 59, "open", "open"))

    def test_single_report_jump_detected_regardless_of_state(self, attr, source):
        """Covers reporting only the final position: 0 -> 100 from an idle state."""
        env = _make_env()
        group = _source_group(f"'{source}'")
        assert _eval_tree(env, group, _vars(attr, source, 0, 100, "closed", "open"))

    def test_small_step_from_idle_open_state_ignored(self, attr, source):
        """A final refinement arriving after the state settled stays undetected
        (documented residual of Bug Pattern AX) - pinned so a change here is a
        conscious decision, not an accident."""
        env = _make_env()
        group = _source_group(f"'{source}'")
        assert not _eval_tree(env, group, _vars(attr, source, 99, 100, "open", "open"))


class TestStaticWiring:
    def test_both_attribute_sources_accept_mid_travel_from_state(self):
        text = BLUEPRINT_PATH.read_text()
        assert (
            text.count("trigger.from_state.state in ['opening', 'closing']") == 2
        ), "both cover-attribute sources need the movement-state disjunct"

    def test_custom_sensor_source_keeps_deadband_only(self):
        """Documented residual: a custom position sensor has no motion state;
        burst heuristics false-positive on recomputing template sensors."""
        group = _source_group("'custom_sensor'")
        assert not any(
            "opening" in str(item) for item in group["and"]
        ), "custom_sensor source must not grow a motion-state disjunct blindly"

    def test_deadband_expression_unchanged(self):
        """Q's dead-band stays the first disjunct for both attribute sources."""
        text = BLUEPRINT_PATH.read_text()
        for attr in ("current_position", "position"):
            expr = (
                f"((trigger.to_state.attributes.{attr} | float(0)) "
                f"- (trigger.from_state.attributes.{attr} | float(0))) | abs "
                f"> position_tolerance"
            )
            assert expr in text
