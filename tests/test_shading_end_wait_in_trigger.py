"""
Issue #696: the shading-end waiting time must hold WITHOUT interruption.

Before the fix the sensor-based end conditions were only sampled — at the
first drop (arming the end pending) and when the pending expired (plus every
retry). Brightness recovering to anywhere between the end and the start value
never canceled the wait (#554 only fires on a start-condition edge), so on
changeable days the shading ended as soon as one sample landed on a cloud.

The six sensor-based end triggers now carry `for: shading_waitingtime_end`
(the `t_open_4` pattern): HA cancels the timer when the template falls back to
false and restarts it on the next edge, so the trigger fires only after the
condition held for the whole waiting time. The arm branch then sets the due
time to "now" for those triggers, so the execution (with its live re-check of
all end conditions) follows immediately instead of waiting a second time. The
sun-position triggers (5/7) keep their pending wait, including the
"immediately when out of range" option.

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

ARM_ALIAS = "Shading end detected. Save next execution time and pending status"
SENSOR_TRIGGERS = [f"t_shading_end_pending_{n}" for n in (1, 2, 3, 4, 6, 8)]
SUN_TRIGGERS = ["t_shading_end_pending_5", "t_shading_end_pending_7"]


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


class TestSensorEndTriggersHoldTheWaitingTime:
    @pytest.mark.parametrize("trigger_id", SENSOR_TRIGGERS)
    def test_sensor_trigger_carries_the_end_waiting_time(self, blueprint, trigger_id):
        trig = _trigger(blueprint, trigger_id)
        # `!input` is loaded as the input name; the value must be the end waiting time.
        assert trig.get("for") == {"seconds": "shading_waitingtime_end"}, (
            f"{trigger_id} must wait `for: shading_waitingtime_end` (#696)"
        )

    @pytest.mark.parametrize("trigger_id", SUN_TRIGGERS)
    def test_sun_position_triggers_keep_the_pending_wait(self, blueprint, trigger_id):
        # The sun never re-enters a range it just left; the wait (and the
        # "immediately when out of range" 20 s) stays in the arm branch.
        assert "for" not in _trigger(blueprint, trigger_id)

    def test_start_triggers_are_untouched(self, blueprint):
        for trig in blueprint["triggers"]:
            if str(trig.get("id", "")).startswith("t_shading_start_pending"):
                assert "for" not in trig, f"{trig['id']} must not carry a for:"


class TestArmBranchDoesNotWaitTwice:
    def _wait(self, blueprint, trigger_id, immediate=False, wait=300) -> int:
        template = _arm_variables(blueprint)["local_waitingtime_end"]
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        env.filters["bool"] = lambda value, default=None: str(value).lower() in ("true", "1", "on")
        rendered = env.from_string(template).render(
            trigger={"id": trigger_id},
            is_shading_end_immediate_by_sun_position=immediate,
            shading_waitingtime_end=wait,
        )
        return int(rendered.strip())

    @pytest.mark.parametrize("trigger_id", SENSOR_TRIGGERS)
    def test_sensor_trigger_executes_immediately(self, blueprint, trigger_id):
        # The trigger already held the waiting time; a second wait in the
        # pending would double it.
        assert self._wait(blueprint, trigger_id) == 0
        assert self._wait(blueprint, trigger_id, immediate=True) == 0

    @pytest.mark.parametrize("trigger_id", SUN_TRIGGERS)
    def test_sun_trigger_waits_in_the_pending(self, blueprint, trigger_id):
        assert self._wait(blueprint, trigger_id) == 300
        assert self._wait(blueprint, trigger_id, wait=0) == 0

    @pytest.mark.parametrize("trigger_id", SUN_TRIGGERS)
    def test_immediate_by_sun_position_still_shortens_the_sun_wait(self, blueprint, trigger_id):
        assert self._wait(blueprint, trigger_id, immediate=True) == 20

    def test_due_is_derived_from_the_local_wait(self, blueprint):
        uv = _arm_variables(blueprint)["update_values"]
        assert uv["pnd"] == "end"
        assert "local_waitingtime_end" in str(uv["ts"]["due"])
        assert uv["ts"]["arm"] == "now"


class TestExecutionTriggerFiresOnTheArmWrite:
    def test_execution_template_is_true_once_due_is_now(self, blueprint):
        """With due = now the execution trigger must turn true on the very helper
        write that arms the pending (the template reads the helper, so the
        write re-renders it)."""
        template = _trigger(blueprint, "t_shading_end_execution")["value_template"]
        assert "states(cover_status_helper)" in template
        now_ts = 1_800_000_000
        helper = (
            '{"bas":"opn","shd":1,"pnd":"end","win":"cls","frc":"non","res":1,"man":0,'
            '"ts":{"opn":0,"cls":0,"shd":%d,"due":%d,"arm":%d,"man":0},"v":6,"t":0}'
            % (now_ts, now_ts, now_ts)
        )
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        env.globals["states"] = lambda entity_id: helper
        env.globals["now"] = lambda: now_ts
        env.globals["as_timestamp"] = lambda value: value
        env.filters["from_json"] = __import__("json").loads
        env.filters["regex_match"] = lambda value, pattern: bool(re.match(pattern, str(value)))
        rendered = env.from_string(template).render(
            cover_status_helper="input_text.cca_helper",
            invalid_states=["", "unavailable", "unknown", "none", "None"],
        ).strip()
        assert rendered == "True"
