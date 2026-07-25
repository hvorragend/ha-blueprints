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
stamped by `helper_update` only when `drive_plan.run` was true (the same
decision that gates `man: 0`, Invariant 7). The settle window keys off `d`
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


def _render_helper_update(drive_plan=None, update_values=None, current=None) -> dict:
    env = _make_env()
    variables = {
        "helper_json": current if current is not None else dict(CURRENT_HELPER),
        "update_values": update_values if update_values is not None else {},
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
        result = _render_helper_update(drive_plan={"run": True})
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
        assert "(drive_plan | default({})).run | default(false)" in tpl, (
            "d must be derived from drive_plan.run with the Invariant-14 guards"
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
