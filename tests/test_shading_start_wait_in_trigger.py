"""
Issue #696 follow-up: the brightness shading-START trigger holds the start
waiting time itself via `for:` (mirror of the sensor-based end triggers in
test_shading_end_wait_in_trigger.py).

Only `t_shading_start_pending_2` changes: the brightness has to stay above the
start threshold for the whole waiting time without interruption, and the arm
branch then sets the due time to "now" so the execution (with its live
re-check of all start conditions) follows immediately instead of waiting a
second time. The pre-window deferral to the window start stays. Every other
start trigger keeps the pending wait (retry-loop design, Bug Pattern AA).

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

ARM_ALIAS = "Shading detected. Save next execution time and pending status"
BRIGHTNESS = "t_shading_start_pending_2"
OTHER_START_TRIGGERS = [f"t_shading_start_pending_{n}" for n in (1, 3, 4, 5, 6, 7, 8)]
NOW = 1_800_000_000


def _load_blueprint_yaml() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


@pytest.fixture(scope="module")
def blueprint() -> dict:
    return _load_blueprint_yaml()


def _trigger(blueprint: dict, trigger_id: str) -> dict:
    for trig in blueprint["triggers"]:
        if trig.get("id") == trigger_id:
            return trig
    raise AssertionError(f"trigger {trigger_id!r} not found")


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


def _arm_variables(blueprint: dict) -> dict:
    branch = _find_branch_by_alias(blueprint, ARM_ALIAS)
    assert branch is not None, f"branch not found: {ARM_ALIAS!r}"
    for step in branch["sequence"]:
        if isinstance(step, dict) and "variables" in step:
            return step["variables"]
    raise AssertionError("variables step not found in the arm branch")


def _env() -> jinja2.Environment:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.globals["now"] = lambda: NOW
    env.globals["as_timestamp"] = lambda value: value
    env.globals["today_at"] = lambda value: value
    env.filters["max"] = max
    return env


def _render_arm(blueprint, trigger_id, wait=300, **flags):
    """Render shading_start_wait and shading_start_due like the arm branch does."""
    variables = _arm_variables(blueprint)
    env = _env()
    context = {
        "trigger": {"id": trigger_id},
        "shading_waitingtime_start": wait,
        "is_time_control_disabled": False,
        "is_shading_allowed_window": True,
        "is_time_field_enabled": False,
        "is_calendar_enabled": False,
        "calendar_open_start": None,
        "time_up_early_today": NOW + 3600,
        **flags,
    }
    start_wait = int(env.from_string(variables["shading_start_wait"]).render(**context).strip())
    due = int(env.from_string(variables["shading_start_due"]).render(
        **context, shading_start_wait=start_wait).strip())
    return start_wait, due


class TestBrightnessStartTriggerHoldsTheWaitingTime:
    def test_brightness_trigger_carries_the_start_waiting_time(self, blueprint):
        trig = _trigger(blueprint, BRIGHTNESS)
        # `!input` is loaded as the input name; the value must be the start waiting time.
        assert trig.get("for") == {"seconds": "shading_waitingtime_start"}, (
            f"{BRIGHTNESS} must wait `for: shading_waitingtime_start` (#696 follow-up)"
        )

    @pytest.mark.parametrize("trigger_id", OTHER_START_TRIGGERS)
    def test_other_start_triggers_keep_the_pending_wait(self, blueprint, trigger_id):
        # Retry-loop design (Bug Pattern AA): only brightness flickers.
        assert "for" not in _trigger(blueprint, trigger_id)


class TestArmBranchDoesNotWaitTwice:
    def test_brightness_trigger_executes_immediately_inside_the_window(self, blueprint):
        start_wait, due = _render_arm(blueprint, BRIGHTNESS)
        assert start_wait == 0
        assert due == NOW

    @pytest.mark.parametrize("trigger_id", OTHER_START_TRIGGERS)
    def test_other_triggers_wait_in_the_pending(self, blueprint, trigger_id):
        start_wait, due = _render_arm(blueprint, trigger_id)
        assert start_wait == 300
        assert due == NOW + 300

    def test_brightness_trigger_still_defers_to_the_window_start(self, blueprint):
        # Bug Patterns L/S: arming before the window keeps the max() with the
        # window start, the for: only removes the second wait.
        window_start = NOW + 3600
        _, due = _render_arm(
            blueprint, BRIGHTNESS,
            is_shading_allowed_window=False, is_time_field_enabled=True,
            time_up_early_today=window_start,
        )
        assert due == window_start + 1

    def test_user_wait_of_zero_behaves_like_before(self, blueprint):
        start_wait, due = _render_arm(blueprint, "t_shading_start_pending_1", wait=0)
        assert start_wait == 0 and due == NOW

    def test_log_line_names_the_trigger_held_wait_only_for_brightness(self, blueprint):
        template = _arm_variables(blueprint)["log_extra"]
        assert "shading_start_wait" in template
        assert "already held by the trigger" in template
        assert "t_shading_start_pending_2" in template
