"""
Issue #641 / Bug Pattern AQ: a queued run must not write its stale
helper snapshot back over state that intervening runs already cleared.

Under `mode: queued` the automation-level `variables:` block — including
`helper_json` — is rendered at TRIGGER time, but the run may only execute
minutes later (queued behind a shading-end execution that waits out the
drive, a tilt run waiting out `tilt_delay`, a drive delay, ...). The old
`helper_update` merged `update_values` into that trigger-time snapshot, so
every field the branch did not explicitly set was written back from a stale
world: a manual/tilt run queued behind a shading-end execution resurrected
`shd: 1, pnd: 'end'` with a `ts.due` in the past, which re-fired
`t_shading_end_execution` and `t_shading_tilt_*` — an endless
end-execute → stale-write-back → end-execute loop that jiggled the cover by
a few percent every cycle.

The fix re-reads the helper LIVE at write time and merges `update_values`
into that (falling back to the `helper_json` snapshot when the live value is
invalid or pre-v6). Additionally the shading-tilt and alternate-shading-
position branches gate their drive on the live `shd` flag, so a queued tilt
run cannot tilt into the shading angle after the shading has already ended.

All templates are extracted verbatim from the blueprint.
"""
import datetime
import json
import pathlib
import re

import jinja2
import yaml


BLUEPRINT_PATH = (
    pathlib.Path(__file__).parent.parent
    / "blueprints"
    / "automation"
    / "cover_control_automation.yaml"
)

INVALID_STATES = ["", "unavailable", "unknown", "none", "None", "null", "query failed", []]

NOW = datetime.datetime(2026, 7, 27, 15, 36, 37)
NOW_TS = int(NOW.timestamp())

TS_OLD = 1785150373  # stale trigger-time snapshot timestamps
TS_NEW = 1785166525  # the intervening run's (live) write


def _load_blueprint() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


BP = _load_blueprint()


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


def _helper_update_value_template() -> str:
    step = _walk(
        BP,
        lambda n: isinstance(n, dict)
        and n.get("action") == "input_text.set_value"
        and "run_drove" in str(n.get("data", {}).get("value", "")),
    )
    assert step is not None, "helper_update set_value template with run_drove not found"
    return step["data"]["value"]


def _branch_will_drive_template(alias: str) -> str:
    branch = _walk(
        BP,
        lambda n: isinstance(n, dict) and n.get("alias") == alias and "conditions" in n,
    )
    assert branch is not None, f"branch not found: {alias!r}"
    variables = branch["sequence"][0]["variables"]
    return variables["will_drive"]


def _make_env(entity_states: dict | None = None) -> jinja2.Environment:
    entity_states = entity_states or {}

    def states(entity_id):
        if isinstance(entity_id, list):
            return "unknown"
        return entity_states.get(entity_id, "unknown")

    env = jinja2.Environment(undefined=jinja2.Undefined)
    env.globals["states"] = states
    env.globals["now"] = lambda: NOW
    env.globals["as_timestamp"] = lambda value, default=None: (
        value.timestamp() if isinstance(value, datetime.datetime) else float(value)
    )
    env.filters["to_json"] = lambda v: json.dumps(v, separators=(",", ":"))
    env.filters["from_json"] = lambda v, default=None: json.loads(v)
    env.filters["regex_match"] = lambda v, p, ignorecase=False: re.match(p, str(v)) is not None
    env.filters["regex_search"] = lambda v, p, ignorecase=False: re.search(p, str(v)) is not None
    return env


HELPER_ENTITY = "input_text.cca_status"

# The #641 trigger-time snapshot: shading-end pending armed, due in the past.
STALE_PENDING_SNAPSHOT = {
    "bas": "opn", "shd": 1, "pnd": "end", "win": "cls", "frc": "non",
    "res": 0, "man": 0,
    "ts": {"opn": TS_OLD, "cls": 0, "shd": TS_OLD, "due": TS_OLD, "arm": TS_OLD, "man": 0},
    "v": 6, "t": TS_OLD, "d": TS_OLD,
}

# What the shading-end execution wrote while this run sat in the queue.
CLEAN_LIVE_STATE = {
    "bas": "opn", "shd": 0, "pnd": "non", "win": "cls", "frc": "non",
    "res": 0, "man": 0,
    "ts": {"opn": TS_NEW, "cls": 0, "shd": TS_NEW, "due": 0, "arm": 0, "man": 0},
    "v": 6, "t": TS_NEW, "d": TS_NEW,
}


def _render_helper_update(
    update_values=None,
    drive_plan=None,
    snapshot=None,
    live=None,
    helper_input=HELPER_ENTITY,
) -> dict:
    snapshot = snapshot if snapshot is not None else dict(STALE_PENDING_SNAPSHOT)
    env = _make_env({helper_input: live} if isinstance(live, str) else {})
    variables = {
        "helper_json": snapshot,
        "update_values": update_values if update_values is not None else {},
        "cover_status_helper": helper_input,
        "invalid_states": INVALID_STATES,
    }
    if drive_plan is not None:
        variables["drive_plan"] = drive_plan
    rendered = env.from_string(_helper_update_value_template()).render(**variables)
    return json.loads(rendered.strip())


class TestHelperUpdateLiveReread:
    def test_stale_snapshot_does_not_resurrect_cleared_pending(self):
        """The #641 loop: a tilt/manual run queued behind the shading-end
        execution writes only `man` — everything else must come from the
        LIVE helper, not from its stale trigger-time snapshot."""
        result = _render_helper_update(
            update_values={"man": 0},
            drive_plan={"run": True},
            snapshot=dict(STALE_PENDING_SNAPSHOT),
            live=json.dumps(CLEAN_LIVE_STATE),
        )
        assert result["shd"] == 0, "stale snapshot resurrected shd"
        assert result["pnd"] == "non", "stale snapshot resurrected the pending phase"
        assert result["ts"]["due"] == 0
        assert result["ts"]["arm"] == 0
        assert result["ts"]["opn"] == TS_NEW, "omitted keys must be preserved from live"

    def test_explicit_updates_still_win_over_the_live_state(self):
        """The shading-end execution's own write clears the pending even when
        the live helper still shows it armed."""
        result = _render_helper_update(
            update_values={
                "bas": "opn", "shd": 0, "man": 0, "pnd": "non",
                "ts": {"opn": "now", "shd": "now", "due": 0, "arm": 0},
            },
            drive_plan={"run": True},
            snapshot=dict(STALE_PENDING_SNAPSHOT),
            live=json.dumps(STALE_PENDING_SNAPSHOT),
        )
        assert result["shd"] == 0
        assert result["pnd"] == "non"
        assert result["ts"]["due"] == 0
        assert result["ts"]["arm"] == 0
        assert result["ts"]["shd"] == NOW_TS, "real shd 1->0 change must stamp ts.shd"

    def test_ts_shd_guard_compares_against_the_live_state(self):
        """When the live state already shows shd 0, a redundant shd: 0 write
        must not re-stamp ts.shd (Invariant 8, now against live)."""
        result = _render_helper_update(
            update_values={"shd": 0, "ts": {"shd": "now"}},
            snapshot=dict(STALE_PENDING_SNAPSHOT),
            live=json.dumps(CLEAN_LIVE_STATE),
        )
        assert result["ts"]["shd"] == TS_NEW, "redundant shd write must not stamp ts.shd"

    def test_invalid_live_state_falls_back_to_the_snapshot(self):
        result = _render_helper_update(
            update_values={"man": 0},
            snapshot=dict(STALE_PENDING_SNAPSHOT),
            live="unavailable",
        )
        assert result["shd"] == 1
        assert result["pnd"] == "end"

    def test_pre_v6_live_state_falls_back_to_the_snapshot(self):
        """During the upgrade window the stored helper may still be v5; the
        snapshot (already migrated by helper_json) is the merge base then."""
        result = _render_helper_update(
            update_values={"man": 0},
            snapshot=dict(CLEAN_LIVE_STATE),
            live='{"open":{"a":1,"t":0},"v":5}',
        )
        assert result["shd"] == 0
        assert result["pnd"] == "non"
        assert result["ts"]["opn"] == TS_NEW

    def test_unconfigured_helper_falls_back_to_the_snapshot(self):
        result = _render_helper_update(
            update_values={"man": 0},
            snapshot=dict(STALE_PENDING_SNAPSHOT),
            helper_input=[],
        )
        assert result["pnd"] == "end"


class TestShadingDriveLiveGates:
    """A queued tilt/position-adjust run must not drive into the shading
    position when the live helper shows the shading has already ended."""

    def _will_drive(self, alias: str, live: str, extra=None) -> bool:
        env = _make_env({HELPER_ENTITY: live})
        variables = {
            "is_paused": False,
            "force_allows_shade": True,
            "cover_status_helper": HELPER_ENTITY,
        }
        variables.update(extra or {})
        rendered = env.from_string(_branch_will_drive_template(alias)).render(**variables)
        return rendered.strip() == "True"

    def test_tilt_branch_skips_the_drive_when_shading_ended_live(self):
        assert not self._will_drive(
            "Check for shading tilt", json.dumps(CLEAN_LIVE_STATE)
        )

    def test_tilt_branch_drives_while_shading_is_live(self):
        assert self._will_drive(
            "Check for shading tilt", json.dumps(STALE_PENDING_SNAPSHOT)
        )

    def test_tilt_branch_still_respects_the_pause(self):
        env = _make_env({HELPER_ENTITY: json.dumps(STALE_PENDING_SNAPSHOT)})
        rendered = env.from_string(
            _branch_will_drive_template("Check for shading tilt")
        ).render(
            is_paused=True,
            force_allows_shade=True,
            cover_status_helper=HELPER_ENTITY,
        )
        assert rendered.strip() == "False"

    def test_alt_position_branch_skips_the_drive_when_shading_ended_live(self):
        assert not self._will_drive(
            "Check for alternate shading position",
            json.dumps(CLEAN_LIVE_STATE),
            extra={"in_shading_position": False},
        )

    def test_alt_position_branch_drives_while_shading_is_live(self):
        assert self._will_drive(
            "Check for alternate shading position",
            json.dumps(STALE_PENDING_SNAPSHOT),
            extra={"in_shading_position": False},
        )
