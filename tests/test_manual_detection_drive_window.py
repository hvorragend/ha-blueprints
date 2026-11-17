"""
Issue #614: manual cover moves must not be swallowed by suppression windows
that key off non-driving activity.

The manual-detection branch ("Checking for manual position changes") used two
overshooting suppressions:

  1. A settle window computed from `helper_json.t` — stamped on EVERY helper
     write, including pure state syncs (window/resident updates, shading
     pending arming) that move nothing. Each write opened a
     `drive_time + 60` (default 150 s) blind window in which a genuine manual
     move was silently discarded and never re-fired.
  2. `this.attributes.current == 0` — dropped manual events while ANY run of
     the automation was executing (queued long waits: drive delays up to
     10 min, contact settle delay, midnight-reset sleep).

The fix introduces a dedicated last-drive timestamp `d` in the helper JSON,
stamped by `helper_update` only after `apply_transition` dispatches a real
position/relevant-tilt change (the same signal that gates `man: 0`, Invariant
7). The settle window keys off `d`
(via `helper_ts_drive`), and the `current == 0` check is removed: with
`mode: queued` a manual event always executes AFTER the concurrent run's
helper write, so a run that drove suppresses via the window and a run that
did not drive must not suppress at all.

All templates are extracted verbatim from the blueprint.
"""
import ast
import datetime
import json
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

INVALID_STATES = ["", "unavailable", "unknown", "none", "None", "null", "query failed", []]

NOW = datetime.datetime(2026, 7, 19, 12, 0, 0)
NOW_TS = int(NOW.timestamp())

TS = 1752875000  # any 10-digit unix timestamp


def _load_blueprint() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


BP = _load_blueprint()


def _walk(node, predicate):
    """Depth-first search for the first node matching predicate."""
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


def _find_branch_by_alias(alias: str) -> dict:
    branch = _walk(
        BP,
        lambda n: isinstance(n, dict)
        and n.get("alias") == alias
        and "conditions" in n,
    )
    assert branch is not None, f"branch not found: {alias!r}"
    return branch


def _helper_update_value_template() -> str:
    """The input_text.set_value value template of the helper_update anchor."""
    step = _walk(
        BP,
        lambda n: isinstance(n, dict)
        and n.get("action") == "input_text.set_value"
        and "run_drove" in str(n.get("data", {}).get("value", "")),
    )
    assert step is not None, "helper_update set_value template with run_drove not found"
    return step["data"]["value"]


def _helper_json_template() -> str:
    return BP["variables"]["helper_json"]


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
    # HA's to_json uses orjson → compact separators
    env.filters["to_json"] = lambda v: json.dumps(v, separators=(",", ":"))
    env.filters["from_json"] = lambda v, default=None: json.loads(v)
    env.filters["regex_match"] = lambda v, p, ignorecase=False: re.match(p, str(v)) is not None
    return env


CURRENT_HELPER = {
    "bas": "opn", "shd": 0, "pnd": "non", "win": "cls", "frc": "non",
    "res": 0, "man": 0,
    "ts": {"opn": TS, "cls": TS, "shd": TS, "due": 0, "arm": 0, "man": TS},
    "v": 6, "t": TS, "d": TS,
}


def _render_helper_update(drive_plan=None, update_values=None, current=None, live=None,
                          drive_dispatched=False) -> dict:
    """live: raw helper JSON string served by states() at write time (Bug
    Pattern AQ live re-read). Defaults to the serialized `current` snapshot so
    the snapshot and the live state agree, as they do outside queued races."""
    snapshot = current if current is not None else dict(CURRENT_HELPER)
    entity = "input_text.cca_status"
    env = _make_env({entity: live if live is not None else json.dumps(snapshot)})
    variables = {
        "helper_json": snapshot,
        "update_values": update_values if update_values is not None else {},
        "cover_status_helper": entity,
        "invalid_states": INVALID_STATES,
        "drive_dispatched": drive_dispatched,
    }
    if drive_plan is not None:
        variables["drive_plan"] = drive_plan
    rendered = env.from_string(_helper_update_value_template()).render(**variables)
    return json.loads(rendered.strip())


# ─────────────────────────────────────────────────────────────────────────────
# helper_update: `d` is stamped only by runs that drove the cover
# ─────────────────────────────────────────────────────────────────────────────


class TestDriveTimestampStamping:
    def test_driving_run_stamps_d(self):
        result = _render_helper_update(drive_plan={"run": True}, drive_dispatched=True)
        assert result["d"] == NOW_TS
        assert result["t"] == NOW_TS

    def test_non_driving_run_preserves_d(self):
        """A pure state sync (pending arming, win/res update) must not open
        the manual-detection settle window."""
        result = _render_helper_update(drive_plan={"run": False}, update_values={"win": "tlt"})
        assert result["d"] == TS, "hygiene write must not touch the drive timestamp"
        assert result["t"] == NOW_TS, "every write still stamps t"

    def test_run_without_drive_plan_preserves_d(self):
        """Classification-only handlers (manual, reset) and the migration
        persist define no drive_plan at all."""
        result = _render_helper_update(update_values={"man": 1, "ts": {"man": "now"}})
        assert result["d"] == TS

    def test_helper_without_d_defaults_to_zero(self):
        """First write after the upgrade: the stored helper has no d yet."""
        current = {k: v for k, v in CURRENT_HELPER.items() if k != "d"}
        result = _render_helper_update(drive_plan={"run": False}, current=current)
        assert result["d"] == 0

    def test_d_stamp_matches_the_man_reset_decision(self):
        """The suppression window and the man:0 reset must key off the same
        drive decision (drive_plan.run == will_drive, Invariant 7)."""
        tpl = _helper_update_value_template()
        assert "drive_dispatched | default(false)" in tpl, (
            "d must be derived from the post-delay dispatch decision"
        )


# ─────────────────────────────────────────────────────────────────────────────
# helper_json parser: `d` round-trips, missing `d` defaults to 0
# ─────────────────────────────────────────────────────────────────────────────


HELPER_ENTITY = "input_text.cca_status"


def _parse_helper(raw: str) -> dict:
    env = _make_env({HELPER_ENTITY: raw})
    rendered = env.from_string(_helper_json_template()).render(
        cover_status_helper=HELPER_ENTITY,
        invalid_states=INVALID_STATES,
    )
    return ast.literal_eval(rendered.strip())


class TestHelperJsonParsesDriveTimestamp:
    V6_WITH_D = (
        '{"bas":"opn","shd":0,"pnd":"non","win":"cls","frc":"non","res":0,"man":0,'
        '"ts":{"opn":0,"cls":0,"shd":0,"due":0,"arm":0,"man":0},"v":6,"t":%d,"d":%d}'
        % (TS, TS)
    )
    V6_WITHOUT_D = (
        '{"bas":"opn","shd":0,"pnd":"non","win":"cls","frc":"non","res":0,"man":0,'
        '"ts":{"opn":0,"cls":0,"shd":0,"due":0,"arm":0,"man":0},"v":6,"t":%d}' % TS
    )

    def test_d_round_trips(self):
        assert _parse_helper(self.V6_WITH_D)["d"] == TS

    def test_missing_d_defaults_to_zero(self):
        """Pre-#614 helper: d absent must read as 'no recent drive', so a
        manual move right after the upgrade is not suppressed."""
        assert _parse_helper(self.V6_WITHOUT_D)["d"] == 0

    def test_fresh_default_has_d_zero(self):
        assert _parse_helper("unknown")["d"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Manual-detection branch conditions: drive-scoped window, no current==0
# ─────────────────────────────────────────────────────────────────────────────


MANUAL_BRANCH_ALIAS = "Checking for manual position changes"


class TestManualDetectionConditions:
    @pytest.fixture(scope="class")
    def conditions(self):
        return [str(c) for c in _find_branch_by_alias(MANUAL_BRANCH_ALIAS)["conditions"]]

    def test_settle_window_keys_off_drive_timestamp(self, conditions):
        settle = [c for c in conditions if "drive_time" in c]
        assert len(settle) == 1, "expected exactly one settle-window condition"
        assert "helper_ts_drive" in settle[0], (
            "the settle window must count from the last DRIVING write (#614), "
            "not from every helper write"
        )
        assert "helper_json.t" not in settle[0]

    def test_no_condition_counts_from_every_write(self, conditions):
        assert not any("helper_json.t" in c or "helper_ts_write" in c for c in conditions), (
            "a settle window keyed off helper_json.t suppresses manual moves "
            "after pure state syncs (#614 window 1)"
        )

    def test_no_running_automation_suppression(self, conditions):
        assert not any(re.search(r"this\.attributes\.current\b", c) for c in conditions), (
            "current == 0 drops manual events while any queued run executes "
            "(#614 window 2); with mode:queued the manual run executes after "
            "the concurrent run's helper write, so the drive-scoped settle "
            "window already covers the own-drive case"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helper length: the config check must cover the grown JSON
# ─────────────────────────────────────────────────────────────────────────────


class TestHelperLengthBudget:
    def _max_helper_json(self) -> str:
        """Worst-case compact JSON: every field at its longest value."""
        current = {
            "bas": "opn", "shd": 1, "pnd": "non", "win": "opn", "frc": "non",
            "res": 1, "man": 1,
            "ts": {"opn": TS, "cls": TS, "shd": TS, "due": TS, "arm": TS, "man": TS},
            "v": 6, "t": TS, "d": TS,
        }
        env = _make_env()
        rendered = env.from_string(_helper_update_value_template()).render(
            helper_json=current, update_values={}, drive_plan={"run": True},
        )
        return rendered.strip()

    def _configured_minimum(self) -> int:
        cond = _walk(
            BP,
            lambda n: isinstance(n, str) and "check_status_helper_length | int <" in n,
        )
        assert cond is not None, "helper length check not found"
        return int(re.search(r"check_status_helper_length \| int < (\d+)", cond).group(1))

    def test_minimum_length_covers_worst_case_json(self):
        max_len = len(self._max_helper_json())
        minimum = self._configured_minimum()
        assert max_len <= minimum, (
            f"worst-case helper JSON is {max_len} chars but the config check "
            f"only requires {minimum} - writes would fail silently"
        )

    def test_recommended_length_still_sufficient(self):
        assert len(self._max_helper_json()) <= 254


# ─────────────────────────────────────────────────────────────────────────────
# Bug Pattern BE: inside the drive settle window a counter-move or a stop of
# CCA's own movement still counts as manual
# ─────────────────────────────────────────────────────────────────────────────


def _drive_contradicted_template() -> str:
    step = _walk(
        BP,
        lambda n: isinstance(n, dict) and "drive_contradicted" in n and "state_targets" in n,
    )
    assert step is not None, "drive_contradicted must sit next to state_targets"
    return step["drive_contradicted"]


def _is_number(value) -> bool:
    """HA's is_number: numeric strings count, bool/None/nan/inf do not."""
    if isinstance(value, bool) or value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and number not in (float("inf"), float("-inf"))


def _as_timestamp(value, default=None):
    if isinstance(value, datetime.datetime):
        return value.timestamp()
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


BLIND = "cover.test"
DRIVE_TS = NOW_TS - 100  # CCA dispatched 100 s ago: inside the default 150 s window
STATE_TARGETS = {
    "lock": {"target": 100}, "opn": {"target": 100}, "vnt": {"target": 20},
    "shd": {"target": 30}, "cls": {"target": 0},
}


def _report(state: str, pos, at: int, source: str = "current_position_attr") -> dict:
    stamp = datetime.datetime.fromtimestamp(at)
    if source == "custom_sensor":
        return {"state": str(pos), "attributes": {}, "last_updated": stamp}
    attr = "position" if source == "position_attr" else "current_position"
    return {"state": state, "attributes": {attr: pos}, "last_updated": stamp}


def _scenario(from_state, from_pos, to_state, to_pos, *, live="open", target_state="cls",
              tolerance=0, report_at=DRIVE_TS + 40, drive_ts=DRIVE_TS, write_ts=None,
              source="current_position_attr", trigger_id="t_manual_position",
              now_ts=NOW_TS) -> dict:
    attr = "position" if source == "position_attr" else "current_position"
    return {
        "trigger": {
            "id": trigger_id,
            "attribute": attr,
            "from_state": _report(from_state, from_pos, report_at - 5, source),
            "to_state": _report(to_state, to_pos, report_at, source),
        },
        "live": live,
        "now_ts": now_ts,
        "blind": BLIND,
        "position_source": source,
        "position_tolerance": tolerance,
        "tilt_position_tolerance": 0,
        "state_targets": STATE_TARGETS,
        "effective_state": target_state,
        "helper_ts_drive": drive_ts,
        "helper_ts_write": drive_ts if write_ts is None else write_ts,
        "drive_time": 90,
        "in_reset_override_position": False,
        "helper_state_manual": False,
        "invalid_states": INVALID_STATES,
    }


def _env(scenario: dict) -> jinja2.Environment:
    env = jinja2.Environment(undefined=jinja2.Undefined)
    env.globals["states"] = lambda entity_id: scenario["live"] if entity_id == BLIND else "unknown"
    env.globals["now"] = lambda: datetime.datetime.fromtimestamp(scenario["now_ts"])
    env.globals["as_timestamp"] = _as_timestamp
    env.globals["is_number"] = _is_number
    env.filters["abs"] = abs
    return env


def _contradicted(scenario: dict) -> bool:
    rendered = _env(scenario).from_string(_drive_contradicted_template()).render(**scenario)
    return rendered.strip() == "True"


def _branch_passes(scenario: dict) -> bool:
    """All conditions of the real manual-detection branch, with the real
    drive_contradicted rendered first (as HA does for action variables)."""
    variables = dict(scenario, drive_contradicted=_contradicted(scenario))
    env = _env(scenario)

    def evaluate(cond) -> bool:
        if isinstance(cond, dict):
            if "or" in cond:
                return any(evaluate(c) for c in cond["or"])
            if "and" in cond:
                return all(evaluate(c) for c in cond["and"])
            raise AssertionError(f"unsupported condition node: {cond!r}")
        text = cond.strip()
        if text.startswith("{{") and text.endswith("}}"):
            text = text[2:-2]
        return env.from_string("{{ " + text + " }}").render(**variables).strip() == "True"

    return all(evaluate(c) for c in _find_branch_by_alias(MANUAL_BRANCH_ALIAS)["conditions"])


class TestCounterMoveInsideDriveWindow:
    # The two field reports (KNX, CCA closing to 0)

    def test_raised_by_hand_after_ccas_close_is_manual(self):
        """Closed by CCA, 17 s later raised by wall button: open 1 -> opening 2
        -> open 98; the final report is 2 -> 98."""
        assert _branch_passes(_scenario("opening", 2, "open", 98))

    def test_stopped_then_raised_by_hand_is_manual(self):
        """CCA's close stopped at 10 %, raised 12 s later: opening 10 -> open 100."""
        assert _branch_passes(_scenario("opening", 10, "open", 100))

    # Stop short of the target

    def test_stop_short_of_the_close_target_is_manual(self):
        assert _branch_passes(_scenario("closing", 20, "open", 10))

    def test_stop_with_state_flipping_after_the_last_report_is_manual(self):
        """KNX: position report still 'closing', state flips to 'open' later."""
        assert _branch_passes(_scenario("closing", 20, "closing", 10, live="open"))

    def test_stop_while_opening_is_manual(self):
        assert _branch_passes(_scenario("opening", 40, "open", 55, target_state="opn"))

    def test_counter_move_while_opening_is_manual(self):
        assert _branch_passes(_scenario("closing", 60, "closed", 0, target_state="opn"))

    def test_continuing_past_the_shading_target_is_manual(self):
        """Single-report cover: CCA drives to 30, the user keeps it going to 0."""
        assert _branch_passes(_scenario("closing", 100, "closed", 0, target_state="shd"))

    # CCA's own movement is never manual

    @pytest.mark.parametrize(
        ("from_state", "from_pos", "to_state", "to_pos", "live", "target_state"),
        [
            ("closing", 60, "closing", 40, "closing", "cls"),  # progress, still travelling
            ("closing", 3, "closed", 0, "closed", "cls"),      # arrival
            ("closing", 100, "closed", 0, "closed", "cls"),    # single-report arrival
            ("closed", 0, "open", 1, "open", "cls"),           # end-position jitter
            ("closed", 0, "open", 2, "open", "cls"),           # jitter at the 2 % floor
            ("closing", 4, "open", 2, "open", "cls"),          # rests 2 % off the end
            ("opening", 40, "opening", 60, "opening", "opn"),  # progress, opening
            ("opening", 97, "open", 100, "open", "opn"),       # arrival, opening
            ("open", 100, "open", 99, "open", "opn"),          # jitter at the top
            ("closing", 31, "open", 30, "open", "shd"),        # arrival mid-range
            ("closing", 31, "open", 29, "open", "shd"),        # 1 % overshoot
        ],
    )
    def test_own_movement_is_not_manual(self, from_state, from_pos, to_state, to_pos,
                                        live, target_state):
        assert not _branch_passes(
            _scenario(from_state, from_pos, to_state, to_pos, live=live, target_state=target_state)
        )

    def test_position_tolerance_widens_the_margin(self):
        assert not _branch_passes(_scenario("closing", 20, "open", 4, tolerance=5))
        assert _branch_passes(_scenario("closing", 20, "open", 10, tolerance=5))

    # Guards that keep the old suppression

    def test_report_before_the_dispatch_write_stays_suppressed(self):
        """#614 ordering: a manual event that fired before CCA's dispatch but
        executes after it was physically overridden by that movement."""
        assert not _branch_passes(_scenario("opening", 2, "open", 98, report_at=DRIVE_TS - 10))

    def test_state_write_since_the_drive_keeps_the_suppression(self):
        """A non-driving write after the drive may have moved the projected
        target - CCA's own arrival must not look like a stop short of it."""
        assert not _branch_passes(
            _scenario("closing", 40, "open", 30, target_state="cls", write_ts=DRIVE_TS + 20)
        )

    def test_unknown_target_keeps_the_suppression(self):
        assert not _branch_passes(_scenario("opening", 2, "open", 98, target_state="non"))

    def test_tilt_changes_keep_the_plain_window(self):
        scenario = _scenario("opening", 2, "open", 98, trigger_id="t_manual_tilt")
        scenario["trigger"]["from_state"]["attributes"]["current_tilt_position"] = 0
        scenario["trigger"]["to_state"]["attributes"]["current_tilt_position"] = 100
        assert not _branch_passes(scenario)

    def test_position_attr_source(self):
        assert _branch_passes(_scenario("opening", 10, "open", 100, source="position_attr"))
        assert not _branch_passes(
            _scenario("closing", 3, "closed", 0, live="closed", source="position_attr")
        )

    def test_custom_sensor_counter_move_only(self):
        assert _branch_passes(_scenario(None, 2, None, 98, source="custom_sensor"))
        assert not _branch_passes(_scenario(None, 20, None, 10, source="custom_sensor"))

    # Outside the window nothing changes

    def test_outside_the_window_detection_is_unchanged(self):
        late = NOW_TS - DRIVE_TS + 200
        assert _branch_passes(_scenario("open", 50, "open", 60, live="open", now_ts=NOW_TS + late))
        assert _branch_passes(
            _scenario("closing", 3, "closed", 0, live="closed", now_ts=DRIVE_TS + 151)
        ), "outside the window even an arrival-shaped change counts, as before"

    def test_variable_is_false_for_non_state_triggers(self):
        scenario = _scenario("opening", 2, "open", 98)
        scenario["trigger"] = {"id": "t_open_1"}
        assert not _contradicted(scenario)
