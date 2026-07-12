"""
Regression tests for documented "Known Bug Patterns" in .claude/CLAUDE.md
that previously had neither a numbered Invariant nor a dedicated test.

Covered here:
  - Pattern K (#467): regex must not match the nested ts.shd timestamp
  - Pattern L:        shading-start ts.due = max(now+wait, window_start+1)
  - Pattern M (#483): sun-position end split into azimuth-only / elevation-only
  - Pattern N (#484): contact handler must not reset pnd/ts.due/ts.arm,
                      and "was ventilating before" must not gate on in_open_position
  - Pattern V:        shade-once-per-day guard is calendar-based (no helper_ts_man
                      short-circuit)

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


def _blueprint_text() -> str:
    return BLUEPRINT_PATH.read_text(encoding="utf-8")


def _load_blueprint_yaml() -> dict:
    """Load HA blueprint YAML, tolerating custom tags like !input and anchors."""

    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor(
        "!input",
        lambda loader, node: loader.construct_scalar(node),
    )
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


def _find_variable_definition(blueprint: dict, name: str):
    """Depth-first search for a variables-step key with the given name."""

    def walk(node):
        if isinstance(node, dict):
            variables = node.get("variables")
            if isinstance(variables, dict) and name in variables:
                return variables[name]
            for v in node.values():
                found = walk(v)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item)
                if found is not None:
                    return found
        return None

    return walk(blueprint)


def _find_branch_by_alias(blueprint: dict, alias: str) -> dict | None:
    """Depth-first search for a choose-branch dict with the given alias."""

    def walk(node):
        if isinstance(node, dict):
            if node.get("alias") == alias:
                return node
            for v in node.values():
                found = walk(v)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item)
                if found is not None:
                    return found
        return None

    return walk(blueprint)


def _find_trigger_by_id(blueprint: dict, trigger_id: str) -> dict | None:
    for trig in blueprint.get("triggers", []) or blueprint.get("trigger", []) or []:
        if trig.get("id") == trigger_id:
            return trig
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Pattern K (#467): regex must not match the nested ts.shd timestamp
# ─────────────────────────────────────────────────────────────────────────────

# The fixed regex from the blueprint (all 6 occurrences use this exact form).
SHD_ACTIVE_REGEX = r'"shd"\s*:\s*1\s*[,}]'

# Realistic helper JSON snippets.
HELPER_SHADING_ACTIVE = (
    '{"bas":"opn","shd":1,"pnd":"non","win":"cls","frc":"non","res":1,"man":0,'
    '"ts":{"opn":0,"cls":0,"shd":1779701945,"due":0,"arm":0,"man":0},"v":6,"t":0}'
)
HELPER_SHADING_INACTIVE = (
    '{"bas":"opn","shd":0,"pnd":"non","win":"cls","frc":"non","res":1,"man":0,'
    '"ts":{"opn":0,"cls":0,"shd":1779701945,"due":0,"arm":0,"man":0},"v":6,"t":0}'
)


def _regex_search(value, pattern):
    """Mirror Home Assistant's `value | regex_search(pattern)` filter."""
    return bool(re.search(pattern, str(value)))


class TestPatternKShdRegex:
    """#467: `"shd":1` detection must not be fooled by a `ts.shd` timestamp."""

    def test_matches_top_level_shd_active(self):
        assert _regex_search(HELPER_SHADING_ACTIVE, SHD_ACTIVE_REGEX) is True

    def test_does_not_match_when_shd_inactive(self):
        # shd is 0; only the nested ts.shd starts with 1 — must NOT match.
        assert _regex_search(HELPER_SHADING_INACTIVE, SHD_ACTIVE_REGEX) is False

    def test_old_buggy_regex_false_positives_on_timestamp(self):
        # Documents *why* the fix was needed: the pre-#467 regex matched ts.shd.
        buggy = r'"shd"\s*:\s*1'
        assert _regex_search(HELPER_SHADING_INACTIVE, buggy) is True
        assert _regex_search(HELPER_SHADING_INACTIVE, SHD_ACTIVE_REGEX) is False

    def test_matches_with_closing_brace_after_one(self):
        # Defensive: top-level shd as the last key before '}'.
        assert _regex_search('{"x":0,"shd":1}', SHD_ACTIVE_REGEX) is True

    def test_blueprint_uses_guarded_regex_everywhere(self):
        text = _blueprint_text()
        # Every shd-active check must carry the [,}] guard.
        guarded = len(re.findall(re.escape(r'"shd"\s*:\s*1\s*[,}]'), text))
        assert guarded == 6, f"expected 6 guarded shd regexes, found {guarded}"
        # No bare `"shd"\s*:\s*1` without the trailing `\s*[,}]` guard.
        bare = re.findall(r'"shd"\\s\*:\\s\*1(?!\\s\*\[,\}\])', text)
        assert bare == [], f"unguarded shd regex(es) found: {bare}"


# ─────────────────────────────────────────────────────────────────────────────
# Pattern L: shading-start ts.due = max(now+wait, window_start+1)
# ─────────────────────────────────────────────────────────────────────────────

# Verbatim copy of the `shading_start_due` template (blueprint ~line 5333).
SHADING_START_DUE_TEMPLATE = (
    "{% set wait_due = (as_timestamp(now()) + shading_waitingtime_start | int) | int %}"
    "{% if is_time_control_disabled or is_shading_allowed_window %}"
    "{{ wait_due }}"
    "{% elif is_time_field_enabled %}"
    "{{ [wait_due, as_timestamp(today_at(time_up_early_today)) | int + 1] | max }}"
    "{% elif is_calendar_enabled and calendar_open_start is not none %}"
    "{{ [wait_due, calendar_open_start | int + 1] | max }}"
    "{% else %}"
    "{{ wait_due }}"
    "{% endif %}"
)

_NOW_TS = 1000  # as_timestamp(now())


def _render_due(**variables) -> int:
    """Render the ts.due template with mocked HA time functions."""
    _NOW_SENTINEL = object()
    window_start_ts = variables.pop("window_start_ts", 0)

    def as_timestamp(value):
        return _NOW_TS if value is _NOW_SENTINEL else int(value)

    env = jinja2.Environment()
    env.globals["now"] = lambda: _NOW_SENTINEL
    env.globals["as_timestamp"] = as_timestamp
    env.globals["today_at"] = lambda _s: window_start_ts
    defaults = {
        "shading_waitingtime_start": 600,
        "is_time_control_disabled": False,
        "is_shading_allowed_window": False,
        "is_time_field_enabled": False,
        "is_calendar_enabled": False,
        "calendar_open_start": None,
        "time_up_early_today": "07:00:00",
    }
    defaults.update(variables)
    out = env.from_string(SHADING_START_DUE_TEMPLATE).render(**defaults)
    return int(out.strip())


class TestPatternLDueDeferredToWindow:
    """Pending must not arm a ts.due that fires before the time window opens."""

    def test_window_open_due_is_now_plus_wait(self):
        # is_shading_allowed_window → execute as soon as the wait elapses.
        assert _render_due(is_shading_allowed_window=True) == _NOW_TS + 600

    def test_time_control_disabled_due_is_now_plus_wait(self):
        assert _render_due(is_time_control_disabled=True) == _NOW_TS + 600

    def test_arming_before_window_defers_to_window_start(self):
        # window opens far in the future → due == window_start + 1, not now+wait.
        due = _render_due(
            is_time_field_enabled=True,
            window_start_ts=5000,
        )
        assert due == 5001

    def test_window_start_already_past_keeps_now_plus_wait(self):
        # window already open earlier today → max() keeps now+wait.
        due = _render_due(
            is_time_field_enabled=True,
            window_start_ts=500,
        )
        assert due == _NOW_TS + 600

    def test_calendar_mode_defers_to_calendar_open_start(self):
        due = _render_due(
            is_calendar_enabled=True,
            calendar_open_start=9000,
        )
        assert due == 9001

    def test_blueprint_template_uses_max_against_window_start(self):
        text = _blueprint_text()
        assert "today_at(time_up_early_today)) | int + 1] | max" in text
        assert "calendar_open_start | int + 1] | max" in text


# ─────────────────────────────────────────────────────────────────────────────
# Pattern M (#483): sun-position end split into azimuth-only / elevation-only
# ─────────────────────────────────────────────────────────────────────────────

class TestPatternMSunPositionEndSplit:
    """Independent FALSE→TRUE transitions for azimuth and elevation end."""

    @pytest.fixture(scope="class")
    def blueprint(self):
        return _load_blueprint_yaml()

    def test_pending_5_is_azimuth_only(self, blueprint):
        trig = _find_trigger_by_id(blueprint, "t_shading_end_pending_5")
        assert trig is not None, "t_shading_end_pending_5 missing"
        tmpl = trig["value_template"]
        assert "azimuth" in tmpl
        assert "elevation" not in tmpl, "azimuth trigger must not mix in elevation"

    def test_pending_7_is_elevation_only(self, blueprint):
        trig = _find_trigger_by_id(blueprint, "t_shading_end_pending_7")
        assert trig is not None, "t_shading_end_pending_7 missing (#483 split)"
        tmpl = trig["value_template"]
        assert "elevation" in tmpl
        assert "azimuth" not in tmpl, "elevation trigger must not mix in azimuth"

    def test_pending_condition_regex_covers_1_to_7(self):
        text = _blueprint_text()
        assert "t_shading_end_pending_[1-7]" in text
        assert "t_shading_end_pending_[1-6]" not in text, "regex must extend to [1-7]"

    def test_immediate_by_sun_position_checks_both_triggers(self):
        text = _blueprint_text()
        assert (
            "trigger.id in ['t_shading_end_pending_5', 't_shading_end_pending_7']"
            in text
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pattern N (#484): contact handler must not destroy active shading pending
# ─────────────────────────────────────────────────────────────────────────────

# Branches whose fix (#484) removed pnd/ts.due/ts.arm from update_values.
# "Window tilted - Partial ventilation" was missed by the original #484 fix and
# is included here so a tilt during a shading pending no longer destroys it.
N_FIXED_BRANCH_ALIASES = [
    "Window opened - Full ventilation (lockout)",
    "Window tilted - Partial ventilation",
    "Window closed - Return to background state",
]

# "Window closed" return branch that must not gate "was ventilating" on position.
N_RETURN_BRANCH_ALIASES = [
    "Window closed - Return to background state",
]


def _branch_update_values(branch: dict) -> dict:
    """Extract the update_values dict from a branch's first variables step."""
    for step in branch.get("sequence", []):
        if isinstance(step, dict) and "variables" in step:
            uv = step["variables"].get("update_values")
            if uv is not None:
                return uv
    return {}


class TestPatternNContactPreservesPending:
    """#484 Fix A: contact handler omits pnd/ts.due/ts.arm so they persist."""

    @pytest.fixture(scope="class")
    def blueprint(self):
        return _load_blueprint_yaml()

    @pytest.mark.parametrize("alias", N_FIXED_BRANCH_ALIASES)
    def test_branch_does_not_reset_pending_keys(self, blueprint, alias):
        branch = _find_branch_by_alias(blueprint, alias)
        assert branch is not None, f"branch not found: {alias!r}"
        # update_values is either a YAML dict or (for target-chain leaves) a
        # Jinja template building the dict — neither may mention the pending
        # keys, so helper_update preserves them.
        flat = str(_branch_update_values(branch))
        assert "pnd" not in flat, f"{alias}: must not reset pnd (#484)"
        assert "due" not in flat, f"{alias}: must not reset ts.due (#484)"
        assert "arm" not in flat, f"{alias}: must not reset ts.arm (#484)"

    @pytest.mark.parametrize("alias", N_RETURN_BRANCH_ALIASES)
    def test_was_ventilating_not_gated_on_open_position(self, blueprint, alias):
        # #484 Fix B: the shared "was ventilating before" gate must not include
        # in_open_position, otherwise it spuriously matches when win == 'cls'
        # the whole time. The gate lives in the was_ventilating variable that
        # all three return branches reference.
        branch = _find_branch_by_alias(blueprint, alias)
        assert branch is not None, f"branch not found: {alias!r}"
        flat = " ".join(str(c) for c in branch["conditions"])
        assert "was_ventilating" in flat, f"{alias}: expected was_ventilating gate"
        definition = str(_find_variable_definition(blueprint, "was_ventilating"))
        assert "in_ventilate_position" in definition, "expected vent-position clause"
        assert "in_open_position" not in definition, (
            "'was ventilating' must not gate on in_open_position (#484 Fix B)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Issue #495: late opening trigger must not overwrite ts.opn / redundantly drive
#
# Fixed in 9ba59b0, silently reverted by 3116a92 (no test guarded it), re-applied.
# The "Already in open position" branch must always be SELECTED when the cover is
# open (no or-gate in conditions); the ts.opn refresh decision lives inside the
# sequence as if/then/else.  This is the regression test that was missing.
# ─────────────────────────────────────────────────────────────────────────────

P_BRANCH_ALIAS = "Already in open position - only update base state"


def _update_values_from_steps(steps: list) -> dict:
    for step in steps or []:
        if isinstance(step, dict) and "variables" in step:
            uv = step["variables"].get("update_values")
            if uv is not None:
                return uv
    return {}


class TestIssue495AlreadyOpenPreservesTsOpn:
    """The already-open branch refreshes ts.opn only on a real transition/new day."""

    @pytest.fixture(scope="class")
    def branch(self):
        return _find_branch_by_alias(_load_blueprint_yaml(), P_BRANCH_ALIAS)

    def test_branch_exists(self, branch):
        assert branch is not None, f"branch not found: {P_BRANCH_ALIAS!r}"

    def test_conditions_have_no_or_gate(self, branch):
        # The branch must always be selected when the cover is open — the refresh
        # decision must NOT live in the conditions (that caused the #495 fall-through).
        for cond in branch["conditions"]:
            assert not (isinstance(cond, dict) and "or" in cond), (
                "conditions must not contain an or-gate (#495 regression)"
            )
            assert "helper_state_base != 'opn'" not in str(cond), (
                "base-transition check must be inside the sequence, not conditions (#495)"
            )

    def test_refresh_decision_is_if_then_else_in_sequence(self, branch):
        first = branch["sequence"][0]
        assert isinstance(first, dict) and "if" in first, (
            "sequence must start with an if/then/else refresh decision (#495)"
        )
        assert "helper_state_base != 'opn'" in first["if"]
        assert "now().day" in first["if"]

        then_uv = _update_values_from_steps(first.get("then", []))
        else_uv = _update_values_from_steps(first.get("else", []))

        # then (real transition / new day) → refresh ts.opn
        assert then_uv.get("ts", {}).get("opn") == "now", "then must refresh ts.opn"
        # else (already open, same day) → preserve ts.opn by omitting the key
        assert "ts" not in else_uv, "else must preserve ts.opn (omit it) (#495)"
        assert else_uv.get("bas") == "opn"


# ─────────────────────────────────────────────────────────────────────────────
# Issue #530: shading starts while the cover sits BELOW the shading position
#
# When the shading conditions are met before the opening time, the cover is
# still fully closed (position 0) at execution time. The shading-position cap is
# above the closed position (e.g. shading_position=3, close_position=0), so the
# old `current_above_shading` position guard was always False and the
# "Start Shading" branch was skipped — leaving the cover stuck closed with
# pnd='beg' forever. The branch must also drive when the cover is below the
# shading position while the base state wants it open (effective_state == 'opn').
# ─────────────────────────────────────────────────────────────────────────────

START_SHADING_ALIAS = "Start Shading"


class TestIssue530RaiseToShadingFromBelow:
    """The Start Shading branch must raise a closed cover to the shading cap."""

    @pytest.fixture(scope="class")
    def branch(self):
        return _find_branch_by_alias(_load_blueprint_yaml(), START_SHADING_ALIAS)

    def test_branch_exists(self, branch):
        assert branch is not None, f"branch not found: {START_SHADING_ALIAS!r}"

    def test_position_check_has_below_shading_alternative(self, branch):
        # The position-check OR must include an alternative that fires when the
        # cover is below the shading position and the base state wants it open.
        or_clauses = [
            c["or"] for c in branch["conditions"] if isinstance(c, dict) and "or" in c
        ]
        assert or_clauses, "Start Shading must have an or-based position check"
        flat = " ".join(str(clause) for clause in or_clauses)
        assert "current_below_shading" in flat, (
            "Start Shading must drive when cover is below the shading position (#530)"
        )
        assert "effective_state == 'opn'" in flat, (
            "below-shading drive must be gated on base wanting open (#530)"
        )

    def test_branch_still_sets_shd_and_clears_pending(self, branch):
        # Whatever direction the cover moves, the helper must record shd=1 and
        # clear the pending so the cover never gets stuck in 'beg'.
        uv = _branch_update_values(branch)
        assert uv.get("shd") == 1, "Start Shading must set shd=1"
        assert uv.get("pnd") == "non", "Start Shading must clear pnd"


# ─────────────────────────────────────────────────────────────────────────────
# Pattern V: "shade only once per day" must block on a calendar-day basis,
# not be short-circuited by the always-true `helper_ts_man <= helper_ts_shade`
# clause.
# ─────────────────────────────────────────────────────────────────────────────


class TestPatternVShadeOncePerDay:
    """The shading once-per-day guard must actually block a second shading."""

    @pytest.fixture(scope="class")
    def branch(self):
        return _find_branch_by_alias(_load_blueprint_yaml(), "Check for shading start")

    def _once_per_day_clauses(self, branch):
        # The guard itself lives in the shared shading_once_guard_ok variable;
        # the branch's once-per-day OR references it plus the bypass clauses.
        for cond in branch["conditions"]:
            if isinstance(cond, dict) and "or" in cond:
                flat = " ".join(str(c) for c in cond["or"])
                if "shading_once_guard_ok" in flat:
                    return cond["or"], flat
        raise AssertionError("once-per-day OR not found in shading-start branch")

    def _guard_definition(self):
        definition = _find_variable_definition(
            _load_blueprint_yaml(), "shading_once_guard_ok"
        )
        assert definition is not None, "shading_once_guard_ok variable must exist"
        return str(definition)

    def test_branch_exists(self, branch):
        assert branch is not None, "Check for shading start branch must exist"

    def test_no_manual_short_circuit_clause(self, branch):
        # The `helper_ts_man <= helper_ts_shade` clause defaulted to True for
        # users who never touch the cover, disabling the guard entirely.
        self._once_per_day_clauses(branch)
        assert "helper_ts_man" not in self._guard_definition(), (
            "shading once-per-day guard must not use helper_ts_man "
            "(always-true short-circuit, Bug Pattern V)"
        )

    def test_guard_is_calendar_day_based(self, branch):
        # Full-date comparison guards against month-rollover and a fresh
        # ts.shd == 0 (which '%-d' rendered as day 1).
        self._once_per_day_clauses(branch)
        assert "%Y-%m-%d" in self._guard_definition(), (
            "shading once-per-day guard must compare full calendar dates"
        )

    def test_execution_bypass_preserved(self, branch):
        # An already-armed pending must still be able to execute.
        _, flat = self._once_per_day_clauses(branch)
        assert "t_shading_start_execution" in flat, (
            "execution trigger must bypass the once-per-day guard"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pattern W (#538): the closing handler's "window tilted → ventilation" branch
# must not re-drive the cover when it is already in the ventilation position.
# ─────────────────────────────────────────────────────────────────────────────


TILTED_CLOSE_ALIAS = (
    "Window tilted. No lockout. Move to ventilation position instead of closing"
)


class TestPatternWTiltedClosingIdempotent:
    """#538: re-driving ventilation on every closing trigger must be guarded."""

    @pytest.fixture(scope="class")
    def branch(self):
        return _find_branch_by_alias(_load_blueprint_yaml(), TILTED_CLOSE_ALIAS)

    def test_branch_exists(self, branch):
        assert branch is not None, f"branch not found: {TILTED_CLOSE_ALIAS!r}"

    def test_drive_is_position_guarded(self, branch):
        # The drive gate (will_drive = state_gates.vnt) must include the
        # in-ventilation position check so a cover that is already venting is
        # not re-driven on every closing trigger (e.g. the repeating sun-based
        # t_close_5).
        variables = branch["sequence"][0]["variables"]
        will_drive = str(variables.get("will_drive", ""))
        assert "state_gates.vnt" in will_drive, (
            "tilted-closing drive must use the shared vnt gate (#538)"
        )
        gates = _find_variable_definition(_load_blueprint_yaml(), "state_gates")
        vnt_gate = str(gates["vnt"])
        assert "force_allows_ventilate and (effective_state != 'vnt'" in vnt_gate, (
            "state_gates.vnt must be guarded by the in-ventilation check (#538)"
        )
        assert "not in_ventilate_position" in vnt_gate, (
            "state_gates.vnt must check in_ventilate_position (#538)"
        )
        plan = variables.get("drive_plan", {})
        assert "will_drive" in str(plan.get("run", "")), (
            "drive_plan.run must be gated by will_drive (#538)"
        )

    def test_man_reset_only_when_driving(self, branch):
        # man: 0 must carry the same guard (via will_drive) so it is not
        # cleared without a drive (Invariant 7).
        uv = _branch_update_values(branch)
        man = str(uv.get("man", ""))
        assert "will_drive" in man, (
            "man:0 must be gated on actually driving the cover (Invariant 7, #538)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pattern Y (#546): the manual-detection suppression at the reset position must
# carry the same precondition as the reset it mutes (helper_state_manual).
# ─────────────────────────────────────────────────────────────────────────────


MANUAL_BRANCH_ALIAS = "Checking for manual position changes"


class TestPatternYResetPositionSuppressionGuard:
    """#546: don't swallow a manual move to the reset position when man == 0."""

    @pytest.fixture(scope="class")
    def branch(self):
        return _find_branch_by_alias(_load_blueprint_yaml(), MANUAL_BRANCH_ALIAS)

    def _reset_suppression_condition(self, branch):
        for cond in branch["conditions"]:
            s = str(cond)
            if "in_reset_override_position" in s:
                return s
        raise AssertionError(
            "reset-position suppression condition not found in manual branch"
        )

    def test_branch_exists(self, branch):
        assert branch is not None, f"branch not found: {MANUAL_BRANCH_ALIAS!r}"

    def test_suppression_is_gated_on_manual_override(self, branch):
        # The suppression must only fire while an override is active, mirroring
        # the t_reset_position trigger precondition (man == 1).
        cond = self._reset_suppression_condition(branch)
        assert "helper_state_manual" in cond, (
            "reset-position suppression must be gated on helper_state_manual "
            "so a manual move while man == 0 is not silently dropped (#546)"
        )

    def test_suppression_still_targets_manual_position_trigger(self, branch):
        # The guard must remain scoped to the manual position trigger.
        cond = self._reset_suppression_condition(branch)
        assert "t_manual_position" in cond and "in_reset_override_position" in cond

    def test_reset_position_trigger_requires_active_override(self):
        # Documents the asymmetry the fix removes: the reset only fires on
        # man == 1, so the detection suppression must too.
        blueprint = _load_blueprint_yaml()
        trig = _find_trigger_by_id(blueprint, "t_reset_position")
        assert trig is not None, "t_reset_position trigger must exist"
        vt = str(trig.get("value_template", ""))
        assert "helper.man" in vt and "== 1" in vt, (
            "t_reset_position must require an active manual override (man == 1)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Issue #554: a re-triggered shading start during an active end-pending must
# cancel the pending end ONLY when the end conditions are no longer met, and the
# branch must remain reachable even after shading already ran today
# (prevent_shading_multiple_times must not block the cancel).
# ─────────────────────────────────────────────────────────────────────────────


CANCEL_END_PENDING_ALIAS = "Shading re-detected. Cancel pending shading end"


class TestIssue554CancelPendingShadingEnd:
    """#554: cancel the end-pending when end conditions are no longer met."""

    @pytest.fixture(scope="class")
    def cancel_branch(self):
        return _find_branch_by_alias(_load_blueprint_yaml(), CANCEL_END_PENDING_ALIAS)

    @pytest.fixture(scope="class")
    def start_branch(self):
        return _find_branch_by_alias(_load_blueprint_yaml(), "Check for shading start")

    def test_branch_exists(self, cancel_branch):
        assert cancel_branch is not None, f"branch not found: {CANCEL_END_PENDING_ALIAS!r}"

    def test_cancel_rechecks_end_conditions(self, cancel_branch):
        # Without the re-check, an unrelated start-pending trigger (e.g.
        # forecast-temp) cancels a legitimate end-pending whose real end
        # condition (azimuth/elevation) is still met. Since that end trigger
        # won't re-fire (no FALSE->TRUE transition), the cover gets stuck shaded.
        flat = " ".join(str(c) for c in cancel_branch["conditions"])
        assert "not shading_end_conditions_met" in flat, (
            "cancel branch must only fire when the end conditions are no longer "
            "met, otherwise an unrelated start trigger leaves the cover stuck "
            "shaded (#554)"
        )

    def test_cancel_requires_active_end_pending(self, cancel_branch):
        flat = " ".join(str(c) for c in cancel_branch["conditions"])
        assert "helper_state_pending_end" in flat
        assert "t_shading_start_pending" in flat

    def test_cancel_clears_pending_keys(self, cancel_branch):
        uv = _branch_update_values(cancel_branch)
        assert uv.get("pnd") == "non", "cancel must clear pnd to 'non'"
        ts = uv.get("ts", {}) or {}
        assert ts.get("due") == 0 and ts.get("arm") == 0, (
            "cancel must clear ts.due and ts.arm (terminal pending state)"
        )

    def test_cancel_does_not_drive_or_clear_manual(self, cancel_branch):
        # No cover movement happens here, so man must not be reset (Invariant 7)
        # and shd must stay shaded (omitted -> preserved as 1).
        uv = _branch_update_values(cancel_branch)
        assert "man" not in uv, "cancel must not clear man without driving (Invariant 7)"
        assert uv.get("shd", 1) == 1, "cancel must keep shading active"

    def test_once_per_day_guard_allows_end_pending_entry(self, start_branch):
        # prevent_shading_multiple_times must not block the cancel: shading has
        # already run today, so the once-per-day OR is otherwise false and the
        # whole branch (incl. the cancel) would be skipped.
        for cond in start_branch["conditions"]:
            if isinstance(cond, dict) and "or" in cond:
                flat = " ".join(str(c) for c in cond["or"])
                if "shading_once_guard_ok" in flat:
                    assert "helper_state_pending_end" in flat, (
                        "once-per-day guard must allow entry while an end-pending "
                        "is active so the cancel branch stays reachable (#554)"
                    )
                    return
        raise AssertionError("once-per-day OR not found in shading-start branch")

    def test_window_state_guard_allows_end_pending_entry(self, start_branch):
        # An end-pending can be armed while the window is open/tilted (the end
        # handler has no window gate). The branch-entry OR ("Check the helper
        # status or the target status") must then still admit the run so the
        # cancel branch stays reachable.
        for cond in start_branch["conditions"]:
            if isinstance(cond, dict) and "or" in cond:
                flat = " ".join(str(c) for c in cond["or"])
                if "helper_state_is_shaded" in flat:
                    assert "helper_state_pending_end" in flat, (
                        "window-state entry OR must allow entry while an "
                        "end-pending is active (#554)"
                    )
                    return
        raise AssertionError("window-state entry OR not found in shading-start branch")


# ─────────────────────────────────────────────────────────────────────────────
# Bug Pattern AA (#554 follow-up): the GLOBAL trigger gate suppressed all
# t_shading_start_pending_[1-6] triggers while shd == 1 — but during an
# end-pending shd is always still 1, so the #554 cancel branch was dead code.
# The gate must let start-pending triggers through when pnd == 'end'.
# ─────────────────────────────────────────────────────────────────────────────

PND_END_REGEX = r'"pnd"\s*:\s*"end"'

HELPER_END_PENDING = (
    '{"bas":"opn","shd":1,"pnd":"end","win":"cls","frc":"non","res":1,"man":0,'
    '"ts":{"opn":0,"cls":0,"shd":1779701945,"due":1779705000,"arm":1779701945,"man":0},"v":6,"t":0}'
)


def _global_trigger_gate_template() -> str:
    blueprint = _load_blueprint_yaml()
    conditions = blueprint.get("conditions") or blueprint.get("condition") or []
    for cond in conditions:
        if isinstance(cond, dict) and cond.get("condition") == "template":
            vt = str(cond.get("value_template", ""))
            if "t_shading_start_pending" in vt:
                return vt
    raise AssertionError("global trigger gate template condition not found")


def _render_gate(trigger_id: str, helper_json: str) -> bool:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.tests["match"] = lambda value, pattern: bool(re.match(pattern, str(value)))
    env.filters["regex_search"] = _regex_search
    env.globals["states"] = lambda entity_id: helper_json
    rendered = env.from_string(_global_trigger_gate_template()).render(
        trigger={"id": trigger_id},
        cover_status_helper="input_text.cca_helper",
        invalid_states=["", "unavailable", "unknown", "none", "None"],
    )
    rendered = rendered.strip()
    # The else-branch renders the literal "true"; HA parses both spellings.
    assert rendered in ("True", "False", "true", "false"), f"unexpected gate output: {rendered!r}"
    return rendered in ("True", "true")


class TestPatternAAGlobalGateEndPending:
    """#554 follow-up: gate must not swallow start triggers during end-pending."""

    def test_pnd_end_regex_matches_only_end_pending(self):
        assert _regex_search(HELPER_END_PENDING, PND_END_REGEX) is True
        assert _regex_search(HELPER_SHADING_ACTIVE, PND_END_REGEX) is False
        assert _regex_search(HELPER_SHADING_INACTIVE, PND_END_REGEX) is False

    def test_start_pending_passes_while_end_pending_armed(self):
        # The core #554 scenario: shd == 1 AND pnd == 'end' → the start trigger
        # must reach the actions so the cancel branch can run.
        for trigger_id in ("t_shading_start_pending_1", "t_shading_start_pending_2",
                           "t_shading_start_pending_6"):
            assert _render_gate(trigger_id, HELPER_END_PENDING) is True

    def test_start_pending_still_blocked_while_shaded_without_pending(self):
        # Noise suppression preserved: shading active, no end-pending → blocked.
        assert _render_gate("t_shading_start_pending_2", HELPER_SHADING_ACTIVE) is False

    def test_start_pending_passes_while_not_shaded(self):
        assert _render_gate("t_shading_start_pending_2", HELPER_SHADING_INACTIVE) is True

    def test_end_pending_trigger_requires_active_shading(self):
        # Deliberate asymmetry: end triggers still require shd == 1 (the start
        # side is a documented retry loop; see Bug Pattern AA in CLAUDE.md).
        assert _render_gate("t_shading_end_pending_3", HELPER_END_PENDING) is True
        assert _render_gate("t_shading_end_pending_3", HELPER_SHADING_INACTIVE) is False

    def test_unrelated_triggers_pass(self):
        assert _render_gate("t_shading_start_execution", HELPER_END_PENDING) is True
        assert _render_gate("t_open_1", HELPER_SHADING_ACTIVE) is True


# ---------------------------------------------------------------------------
# #550: a Threshold helper (or any noisy source) bound to a contact/resident
# input re-fires the state trigger on every *attribute* change. Setting any of
# from/to/not_from/not_to on the trigger flips HA out of match_all, so it only
# fires on real on/off transitions. The fix uses not_to at the trigger so the
# automation never even starts a run (no leftover trace) for attribute changes.
# ---------------------------------------------------------------------------
class TestIssue550AttributeOnlyTriggersFiltered:
    """#550: ignore attribute-only re-triggers on contact/resident sensors."""

    FILTERED_IDS = (
        "t_contact_tilted_changed",
        "t_contact_opened_changed",
        "t_resident_update",
    )
    MANUAL_IDS = ("t_manual_position", "t_manual_tilt")

    def test_contact_resident_triggers_have_not_to(self):
        # not_to (any of from/to/not_from/not_to) disables match_all, so the
        # trigger no longer fires on attribute-only changes.
        blueprint = _load_blueprint_yaml()
        for tid in self.FILTERED_IDS:
            trig = _find_trigger_by_id(blueprint, tid)
            assert trig is not None, f"trigger {tid} must exist"
            keys = set(trig)
            assert keys & {"not_to", "not_from", "to", "from"}, (
                f"{tid} must set one of from/to/not_from/not_to to ignore "
                f"attribute-only changes (#550)"
            )

    def test_not_to_keeps_real_transitions(self):
        # not_to must only exclude dropout sentinels, never on/off/true/false,
        # otherwise real window/presence transitions would be dropped too.
        blueprint = _load_blueprint_yaml()
        for tid in self.FILTERED_IDS:
            trig = _find_trigger_by_id(blueprint, tid)
            not_to = trig.get("not_to") or []
            assert "unavailable" in not_to
            for real in ("on", "off", "true", "false"):
                assert real not in not_to, (
                    f"{tid} not_to must not exclude the real state {real!r} (#550)"
                )

    def test_manual_triggers_not_filtered(self):
        # Manual position/tilt detection legitimately relies on attribute
        # changes and must NOT get a not_to/to guard.
        blueprint = _load_blueprint_yaml()
        for tid in self.MANUAL_IDS:
            trig = _find_trigger_by_id(blueprint, tid)
            assert trig is not None, f"trigger {tid} must exist"
            assert not (set(trig) & {"not_to", "not_from", "to", "from"}), (
                f"{tid} must keep reacting to attribute changes (#550)"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Bug Pattern AB (#565): a cover sitting at the shading position with shd == 0
# must still open normally at opening time. The old "not in_shading_position"
# guard deferred to Shading End unconditionally — but the global trigger gate
# blocks all shading-end triggers unless the helper shows shd == 1, so with
# shd == 0 the handoff was dead code and the cover never opened.
# ─────────────────────────────────────────────────────────────────────────────


NORMAL_OPENING_ALIAS = "Normal opening of the cover"


class TestIssue565OpenAtShadingPositionWithoutActiveShading:
    """#565: normal opening must only defer to Shading End while shd == 1."""

    @pytest.fixture(scope="class")
    def branch(self):
        return _find_branch_by_alias(_load_blueprint_yaml(), NORMAL_OPENING_ALIAS)

    def _condition(self, branch) -> str:
        conds = [str(c) for c in branch["conditions"]]
        assert len(conds) == 1, "normal-opening branch is expected to have one condition"
        return conds[0]

    def _eval(self, branch, *, in_shading_position: bool, helper_state_shade: bool) -> bool:
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        rendered = env.from_string(self._condition(branch)).render(
            in_shading_position=in_shading_position,
            helper_state_shade=helper_state_shade,
        )
        return rendered.strip() == "True"

    def test_branch_exists(self, branch):
        assert branch is not None, f"branch not found: {NORMAL_OPENING_ALIAS!r}"

    def test_opens_when_at_shading_position_but_shading_inactive(self, branch):
        # shd == 0: the shading-end triggers are gated off globally, so the
        # deferral can never complete — the branch must fire and open (#565).
        assert self._eval(branch, in_shading_position=True, helper_state_shade=False)

    def test_still_defers_when_shading_active(self, branch):
        # shd == 1 and in shading position: Shading End owns the movement.
        assert not self._eval(branch, in_shading_position=True, helper_state_shade=True)

    def test_opens_when_not_at_shading_position(self, branch):
        assert self._eval(branch, in_shading_position=False, helper_state_shade=True)
        assert self._eval(branch, in_shading_position=False, helper_state_shade=False)


# ─────────────────────────────────────────────────────────────────────────────
# Pattern AC (#566): force-disable recovery must ignore the window contacts
# when the ventilation automation is disabled — every direct sensor read in the
# recovery branches must be scoped to is_ventilation_enabled.
# ─────────────────────────────────────────────────────────────────────────────


RECOVERY_VENT_ALIAS = "Force disabled recovery: return to VENTILATION (window tilted)"
RECOVERY_LOCKOUT_ALIAS = "Force disabled recovery: return to OPEN (window open — lockout)"
RECOVERY_CLOSE_ALIAS = "Force disabled recovery: return to CLOSE (base=cls)"
RECOVERY_SHADING_ALIAS = "Force disabled recovery: return to SHADING"
RECOVERY_OPEN_ALIAS = "Force disabled recovery: return to OPEN (base=opn)"


class TestPatternACForceRecoveryVentilationGate:
    """#566: recovery drove to ventilation although ventilation was disabled."""

    @pytest.fixture(scope="class")
    def blueprint(self):
        return _load_blueprint_yaml()

    def _chain_arm(self, blueprint, target: str) -> str:
        # The recovery targets live in the recovery_target chain; extract the
        # condition text of the arm that yields the given target.
        chain = str(_find_variable_definition(blueprint, "recovery_target"))
        assert f"%}}{target}" in chain, f"recovery_target has no {target!r} arm"
        return chain.split(f"%}}{target}")[0].rsplit("{%", 1)[1]

    def test_vent_branch_exists(self, blueprint):
        assert _find_branch_by_alias(blueprint, RECOVERY_VENT_ALIAS) is not None, (
            f"branch not found: {RECOVERY_VENT_ALIAS!r}"
        )

    @pytest.mark.parametrize("target", ["vnt", "lock"])
    def test_drive_targets_require_ventilation_enabled(self, blueprint, target):
        # The ventilation-target arms read the contact sensors directly and
        # therefore bypass the trigger-level gate — they need their own gate.
        arm = self._chain_arm(blueprint, target)
        assert "is_ventilation_enabled" in arm, (
            f"recovery_target {target!r} arm must gate on is_ventilation_enabled (#566)"
        )

    @pytest.mark.parametrize("target", ["cls", "shd", "opn"])
    def test_window_exclusions_scoped_to_ventilation_enabled(self, blueprint, target):
        # A stuck open/tilted contact must not block these targets when the
        # ventilation automation is disabled — every negative window-contact
        # check must be scoped to is_ventilation_enabled.
        arm = self._chain_arm(blueprint, target)
        window_flag = "window_any_now" if target in ("cls", "shd") else "window_opened_now"
        assert f"not (is_ventilation_enabled and {window_flag})" in arm, (
            f"recovery_target {target!r} arm must scope its window exclusion to "
            f"is_ventilation_enabled (#566)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pattern AE: shading start must hold the ventilation floor when the window is
# only tilted (VENT prio 4 > SHADING prio 6). Tilt-first-then-shade must stop at
# the ventilation position, not drop to the shading position below it.
# ─────────────────────────────────────────────────────────────────────────────


VENT_FLOOR_ALIAS = "Shading start - hold ventilation floor (window tilted)"


def _sequence_variables(branch: dict) -> dict:
    for step in branch.get("sequence", []):
        if isinstance(step, dict) and "variables" in step:
            return step["variables"]
    return {}


class TestPatternAEShadingStartVentilationFloor:
    """Tilt-first-then-shade must hold the ventilation floor, not shade below it."""

    @pytest.fixture(scope="class")
    def branch(self):
        return _find_branch_by_alias(_load_blueprint_yaml(), VENT_FLOOR_ALIAS)

    def test_branch_exists(self, branch):
        assert branch is not None, f"branch not found: {VENT_FLOOR_ALIAS!r}"

    def test_drives_to_ventilation_position(self, branch):
        plan = _sequence_variables(branch).get("drive_plan", {})
        assert "ventilate_position" in str(plan.get("target", "")), (
            "vnt-floor branch must drive to the ventilation position, not shading"
        )
        assert plan.get("action_set") == "ventilate"

    def test_gated_on_tilted_not_opened_and_floor(self, branch):
        conds = " ".join(str(c) for c in branch["conditions"])
        assert "window_tilted_now" in conds
        # opened beats tilted (Invariant 5)
        assert "not window_opened_now" in conds
        assert "position_comparisons.shading_below_ventilate" in conds
        assert "force_allows_ventilate" in conds
        assert "resident_flags.allow_ventilate" in conds
        # shading must be allowed too, else fall through to "Save shading state for the future"
        assert "resident_flags.allow_shade" in conds

    def test_runs_before_start_shading(self):
        text = _blueprint_text()
        assert text.index(VENT_FLOOR_ALIAS) < text.index('alias: "Start Shading"'), (
            "vnt-floor branch must be evaluated before 'Start Shading'"
        )

    def test_terminal_pending_clear_and_manual_guard(self, branch):
        variables = _sequence_variables(branch)
        uv = variables.get("update_values", {})
        # terminal branch clears pending together (Invariant 8)
        assert uv.get("pnd") == "non"
        assert uv.get("ts", {}).get("due") == 0
        assert uv.get("ts", {}).get("arm") == 0
        assert uv.get("shd") == 1
        assert uv.get("win") == "tlt"
        # man only cleared when actually driving (Invariant 7): the gate lives
        # in will_drive, referenced by both man and drive_plan.run
        assert "not in_ventilate_position" in str(variables.get("will_drive", ""))
        assert "will_drive" in str(uv.get("man", ""))

    def test_position_comparison_defined(self):
        text = _blueprint_text()
        assert "shading_below_ventilate:" in text, (
            "position_comparisons must define shading_below_ventilate"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Bug Pattern AG: opening deferred/armed into shading although the lockout
# window is open — the shading execution's lockout branch only stores the
# intent and stops, it never opens the cover. Both defer paths in the opening
# handler ("Opening skipped: Shading start pending" and "Opening: Shading
# warranted, arm pending", the latter new since #555 / 2026.06.28 V3) must
# fall through to "Normal opening" when the lockout applies (window fully
# open, or tilted with lockout_tilted_shading_start), so the cover is driven
# to the open position as the cascade (LOCKOUT prio 2) demands.
# ─────────────────────────────────────────────────────────────────────────────

AG_DEFER_ALIAS = "Opening skipped: Shading start pending"
AG_ARM_ALIAS = "Opening: Shading warranted, arm pending"
AG_NORMAL_ALIAS = "Normal opening of the cover"


def _eval_ha_condition(env, cond, variables) -> bool:
    """Evaluate a blueprint condition: template string or {or:[...]}/{and:[...]} dict."""
    from conftest import eval_condition

    if isinstance(cond, str):
        return eval_condition(env, cond, variables)
    if isinstance(cond, dict):
        if "or" in cond:
            return any(_eval_ha_condition(env, c, variables) for c in cond["or"])
        if "and" in cond:
            return all(_eval_ha_condition(env, c, variables) for c in cond["and"])
    raise AssertionError(f"unsupported condition node: {cond!r}")


def _opening_choose_branches() -> list[dict]:
    """Return the choose branches of the 'Check for opening' handler, in order."""
    blueprint = _load_blueprint_yaml()
    handler = _find_branch_by_alias(blueprint, "Check for opening")
    assert handler is not None
    choose_step = handler["sequence"][0]
    return choose_step["choose"]


def _select_opening_branch(entity_states: dict, variables: dict) -> str | None:
    from conftest import make_jinja_env

    env = make_jinja_env(entity_states)
    # Derive the normalized event flags the blueprint computes once per run
    # (post-forecast variables block) from the mocked entity states.
    opened = entity_states.get("binary_sensor.window_opened") in ("on", "true")
    tilted = entity_states.get("binary_sensor.window_tilted") in ("on", "true")
    v = dict(variables)
    v.setdefault("window_opened_now", opened)
    v.setdefault("window_tilted_now", tilted)
    v.setdefault("window_any_now", opened or tilted)
    v.setdefault(
        "lockout_now",
        {
            "closing": opened,
            "shading_start": opened
            or (v.get("lockout_tilted_when_shading_starts", False) and tilted),
            "shading_end": opened,
        },
    )
    v.setdefault(
        "shading_once_guard_ok",
        not v.get("prevent_flags", {}).get("shading_multiple_times", False),
    )
    for branch in _opening_choose_branches():
        if all(
            _eval_ha_condition(env, c, v) for c in branch["conditions"]
        ):
            return branch["alias"]
    return None


def _ag_variables(**overrides) -> dict:
    base = {
        "is_ventilation_enabled": True,
        "is_shading_enabled": True,
        "is_shading_allowed_window": True,
        "shading_start_warranted": True,
        "lockout_tilted_when_shading_starts": False,
        "contact_window_opened": "binary_sensor.window_opened",
        "contact_window_tilted": "binary_sensor.window_tilted",
        "helper_state_pending_start": False,
        "helper_state_pending_end": False,
        "helper_state_is_shaded": False,
        "helper_state_shade": False,
        "effective_state": "lock",
        "in_open_position": False,
        "in_shading_position": False,
        "prevent_flags": {"shading_multiple_times": False},
    }
    base.update(overrides)
    return base


class TestPatternAGOpeningLockoutNotDeferredToShading:
    """Window open at opening time must open the cover, not defer to shading."""

    def test_window_open_with_pending_falls_through_to_normal_opening(self):
        states = {"binary_sensor.window_opened": "on", "binary_sensor.window_tilted": "off"}
        chosen = _select_opening_branch(
            states, _ag_variables(helper_state_pending_start=True)
        )
        assert chosen == AG_NORMAL_ALIAS

    def test_window_open_without_pending_falls_through_to_normal_opening(self):
        states = {"binary_sensor.window_opened": "on", "binary_sensor.window_tilted": "off"}
        chosen = _select_opening_branch(states, _ag_variables())
        assert chosen == AG_NORMAL_ALIAS

    def test_window_closed_with_pending_still_defers(self):
        states = {"binary_sensor.window_opened": "off", "binary_sensor.window_tilted": "off"}
        chosen = _select_opening_branch(
            states, _ag_variables(helper_state_pending_start=True, effective_state="opn")
        )
        assert chosen == AG_DEFER_ALIAS

    def test_window_closed_without_pending_still_arms(self):
        # #555 behavior must be preserved for a closed window
        states = {"binary_sensor.window_opened": "off", "binary_sensor.window_tilted": "off"}
        chosen = _select_opening_branch(states, _ag_variables(effective_state="opn"))
        assert chosen == AG_ARM_ALIAS

    def test_window_tilted_with_lockout_option_falls_through(self):
        states = {"binary_sensor.window_opened": "off", "binary_sensor.window_tilted": "on"}
        chosen = _select_opening_branch(
            states,
            _ag_variables(lockout_tilted_when_shading_starts=True, effective_state="opn"),
        )
        assert chosen == AG_NORMAL_ALIAS

    def test_window_tilted_without_lockout_option_still_arms(self):
        states = {"binary_sensor.window_opened": "off", "binary_sensor.window_tilted": "on"}
        chosen = _select_opening_branch(states, _ag_variables(effective_state="opn"))
        assert chosen == AG_ARM_ALIAS

    def test_ventilation_disabled_ignores_contacts(self):
        # Bug Pattern AC rule: direct contact reads must be scoped to is_ventilation_enabled
        states = {"binary_sensor.window_opened": "on", "binary_sensor.window_tilted": "off"}
        chosen = _select_opening_branch(
            states, _ag_variables(is_ventilation_enabled=False, effective_state="opn")
        )
        assert chosen == AG_ARM_ALIAS

    @pytest.mark.parametrize("alias", [AG_DEFER_ALIAS, AG_ARM_ALIAS])
    def test_gate_present_in_both_branches(self, alias):
        blueprint = _load_blueprint_yaml()
        branch = _find_branch_by_alias(blueprint, alias)
        assert branch is not None, f"branch not found: {alias!r}"
        conds = " ".join(str(c) for c in branch["conditions"])
        assert "not (is_ventilation_enabled and lockout_now.shading_start)" in conds, (
            f"{alias!r} must gate on the shading-start lockout window (Pattern AG)"
        )
        # The shared lockout flag itself must implement the full check.
        lockout_now = _find_variable_definition(blueprint, "lockout_now")
        gate = str(lockout_now["shading_start"])
        assert "window_opened_now" in gate
        assert "lockout_tilted_when_shading_starts" in gate and "window_tilted_now" in gate


# ─────────────────────────────────────────────────────────────────────────────
# Issue #544: Time Control disable must be reachable via the UI —
# the time_control_enabled checkbox in auto_options is the single
# authoritative switch; the legacy selector value is no longer evaluated.
# ─────────────────────────────────────────────────────────────────────────────


def _render_time_flag(flag, auto_options, time_control, calendar_entity=None):
    blueprint = _load_blueprint_yaml()
    template = blueprint["trigger_variables"][flag]
    out = jinja2.Environment().from_string(template).render(
        auto_options=auto_options,
        time_control=time_control,
        calendar_entity=calendar_entity if calendar_entity is not None else [],
    )
    return out.strip() == "True"


class TestIssue544TimeControlDisable:
    """#544: the auto_options checkbox is the single authoritative switch."""

    def test_selector_does_not_offer_legacy_disabled_value(self):
        blueprint = _load_blueprint_yaml()
        inputs = blueprint["blueprint"]["input"]["feature_section"]["input"]
        options = inputs["time_control"]["selector"]["select"]["options"]
        values = [o["value"] for o in options]
        assert "time_control_disabled" not in values
        assert values == ["time_control_input", "time_control_calendar"]

    def test_checkbox_is_offered_and_in_defaults(self):
        blueprint = _load_blueprint_yaml()
        inputs = blueprint["blueprint"]["input"]["feature_section"]["input"]
        auto = inputs["auto_options"]
        values = [o["value"] for o in auto["selector"]["select"]["options"]]
        assert "time_control_enabled" in values
        assert "time_control_enabled" in auto["default"]

    def test_unchecked_checkbox_disables(self):
        # The bug: this had no effect. Now it is the single disable path.
        assert _render_time_flag(
            "is_time_control_disabled", ["auto_up_enabled"], "time_control_input"
        ) is True

    def test_checked_checkbox_enables(self):
        assert _render_time_flag(
            "is_time_control_disabled",
            ["auto_up_enabled", "time_control_enabled"],
            "time_control_input",
        ) is False

    def test_legacy_disabled_value_is_ignored_but_config_stays_disabled(self):
        # Pre-consolidation config that chose 'disabled': the value itself is no
        # longer evaluated, but the missing checkbox disables — original intent kept.
        assert _render_time_flag(
            "is_time_control_disabled", ["auto_up_enabled"], "time_control_disabled"
        ) is True
        # Even with the checkbox on, the legacy value must not disable.
        assert _render_time_flag(
            "is_time_control_disabled",
            ["time_control_enabled"],
            "time_control_disabled",
        ) is False

    def test_time_fields_gated_on_checkbox(self):
        # Without the checkbox the time triggers (enabled: is_time_field_enabled)
        # must be off, or the Late trigger would fire despite "disabled".
        assert _render_time_flag(
            "is_time_field_enabled", [], "time_control_input"
        ) is False
        assert _render_time_flag(
            "is_time_field_enabled", ["time_control_enabled"], "time_control_input"
        ) is True

    def test_calendar_gated_on_checkbox(self):
        assert _render_time_flag(
            "is_calendar_enabled", [], "time_control_calendar",
            calendar_entity="calendar.covers",
        ) is False
        assert _render_time_flag(
            "is_calendar_enabled", ["time_control_enabled"], "time_control_calendar",
            calendar_entity="calendar.covers",
        ) is True
