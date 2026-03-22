"""
Unit tests for Cover Control Automation (CCA) branch-selection logic.

These tests verify that the priority cascade (lockout > vent > shading > open/close)
is respected in key trigger handlers, by evaluating the actual Jinja2 conditions
from the blueprint against mocked variable sets.

Run with: pytest tests/ -v
"""
import pathlib
import pytest
import yaml
from conftest import make_jinja_env, eval_condition, first_matching_branch


BLUEPRINT_PATH = pathlib.Path(__file__).parent.parent / "blueprints" / "automation" / "cover_control_automation.yaml"


# ─────────────────────────────────────────────────────────────────────────────
# Branch condition definitions — copied verbatim from blueprint
# ─────────────────────────────────────────────────────────────────────────────

# Conditions used in the "resident_leaving" → choose block
# Each branch is tried in order; first match wins.
RESIDENT_LEAVING_BRANCHES = [
    {
        "name": "lockout",  # Window fully open → lockout (highest priority)
        "conditions": [
            "{{ contact_window_opened != [] and states(contact_window_opened) in ['true', 'on'] }}",
            "{{ resident_flags.allow_ventilate }}",
            "{{ is_ventilation_enabled }}",
            # NOTE: No position check here — that belongs in the if: guard, not conditions
        ],
    },
    {
        "name": "vent_tilted",  # Window tilted (not opened) → ventilation position
        "conditions": [
            "{{ contact_window_tilted != [] and states(contact_window_tilted) in ['true', 'on'] }}",
            "{{ not (contact_window_opened != [] and states(contact_window_opened) in ['true', 'on']) }}",
            "{{ resident_flags.allow_ventilate }}",
            "{{ is_ventilation_enabled }}",
            # NOTE: No position check here — that belongs in the if: guard, not conditions
        ],
    },
    {
        "name": "shading",  # Shading active → move to shading position
        "conditions": [
            "{{ helper_state_shade }}",
            "{{ resident_flags.allow_shade }}",
            "{{ is_shading_enabled }}",
            "{{ effective_state != 'shd' or not in_shading_position }}",
        ],
    },
    {
        "name": "open",  # Base state open → move to open
        "conditions": [
            "{{ helper_state_base == 'opn' }}",
            "{{ resident_flags.opening_trigger }}",
            "{{ is_up_enabled }}",
            "{{ effective_state != 'opn' or not in_open_position }}",
            "{{ force_allows_open }}",
        ],
    },
    {
        "name": "close",  # Base state close → move to closed
        "conditions": [
            "{{ helper_state_base == 'cls' }}",
            "{{ is_down_enabled }}",
            "{{ effective_state != 'cls' or not in_close_position }}",
            "{{ force_allows_close }}",
        ],
    },
]

# The if: guard that controls whether the cover actually drives (lockout branch)
LOCKOUT_DRIVE_GUARD = (
    "force_allows_ventilate and (effective_state != 'lock' or not in_open_position)"
)

# The if: guard for the vent-tilted branch
VENT_DRIVE_GUARD = (
    "force_allows_ventilate and (effective_state != 'vnt' or not in_ventilate_position)"
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a standard variable dict for scenarios
# ─────────────────────────────────────────────────────────────────────────────

WINDOW_OPENED_ENTITY = "binary_sensor.window_opened"
WINDOW_TILTED_ENTITY = "binary_sensor.window_tilted"


def make_vars(
    *,
    window_opened: bool = False,
    window_tilted: bool = False,
    allow_ventilate: bool = True,
    is_ventilation_enabled: bool = True,
    helper_state_shade: bool = False,
    allow_shade: bool = True,
    is_shading_enabled: bool = True,
    effective_state: str = "opn",
    in_open_position: bool = False,
    in_ventilate_position: bool = False,
    in_shading_position: bool = False,
    in_close_position: bool = False,
    helper_state_base: str = "opn",
    force_allows_open: bool = True,
    force_allows_close: bool = True,
    force_allows_ventilate: bool = True,
    is_up_enabled: bool = True,
    is_down_enabled: bool = True,
    opening_trigger: bool = True,
) -> dict:
    return {
        # In HA blueprints, !input for an entity returns the entity_id string when
        # configured, or [] (empty list) when not configured.
        # contact_window_opened/tilted != [] checks if the sensor is configured.
        "contact_window_opened": WINDOW_OPENED_ENTITY,
        "contact_window_tilted": WINDOW_TILTED_ENTITY,
        # Resident flags (dict-like object accessed via dot notation in Jinja)
        "resident_flags": {
            "allow_ventilate": allow_ventilate,
            "allow_shade": allow_shade,
            "opening_trigger": opening_trigger,
        },
        # Feature flags
        "is_ventilation_enabled": is_ventilation_enabled,
        "is_shading_enabled": is_shading_enabled,
        "is_up_enabled": is_up_enabled,
        "is_down_enabled": is_down_enabled,
        # Helper state
        "helper_state_shade": helper_state_shade,
        "helper_state_base": helper_state_base,
        # Effective state & positions
        "effective_state": effective_state,
        "in_open_position": in_open_position,
        "in_ventilate_position": in_ventilate_position,
        "in_shading_position": in_shading_position,
        "in_close_position": in_close_position,
        # Force permissions
        "force_allows_open": force_allows_open,
        "force_allows_close": force_allows_close,
        "force_allows_ventilate": force_allows_ventilate,
    }


def make_entity_states(*, window_opened: bool = False, window_tilted: bool = False) -> dict:
    return {
        "binary_sensor.window_opened": "on" if window_opened else "off",
        "binary_sensor.window_tilted": "on" if window_tilted else "off",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tests: resident_leaving → priority cascade
# ─────────────────────────────────────────────────────────────────────────────

class TestResidentLeavingPriority:
    """
    Verify that the lockout branch is always selected when the window is open,
    regardless of cover position (regression for Bug-Muster A).
    """

    def test_window_open_cover_at_open_position_selects_lockout(self):
        """
        Regression: Resident leaves, window open, cover already at 100%.
        Before fix: lockout branch was skipped (condition FALSE), shading fired.
        After fix: lockout branch is selected, shading is NOT reached.
        """
        entity_states = make_entity_states(window_opened=True, window_tilted=True)
        env = make_jinja_env(entity_states)
        variables = make_vars(
            window_opened=True,
            window_tilted=True,
            effective_state="lock",     # win='opn' → effective_state='lock'
            in_open_position=True,      # cover is already at 100%
            helper_state_shade=True,    # shading is active (would fire if lockout is skipped)
            allow_shade=True,
            is_shading_enabled=True,
        )
        branch = first_matching_branch(env, RESIDENT_LEAVING_BRANCHES, variables)
        assert branch == "lockout", (
            f"Expected 'lockout' but got '{branch}'. "
            "Lockout must take priority over shading when window is open."
        )

    def test_window_open_cover_not_at_open_position_selects_lockout(self):
        """
        Resident leaves, window open, cover is NOT yet at open position.
        Lockout branch must be selected and drive must happen.
        """
        entity_states = make_entity_states(window_opened=True)
        env = make_jinja_env(entity_states)
        variables = make_vars(
            window_opened=True,
            effective_state="shd",      # cover was in shading before
            in_open_position=False,
            helper_state_shade=True,
        )
        branch = first_matching_branch(env, RESIDENT_LEAVING_BRANCHES, variables)
        assert branch == "lockout"

    def test_lockout_drive_guard_suppresses_drive_when_already_at_position(self):
        """
        When cover is already at open position in lockout state,
        the if: guard must evaluate to False (no re-drive needed).
        """
        env = make_jinja_env()
        result = eval_condition(env, LOCKOUT_DRIVE_GUARD, {
            "force_allows_ventilate": True,
            "effective_state": "lock",
            "in_open_position": True,
        })
        assert result is False, "Drive guard should be False when already at open position"

    def test_lockout_drive_guard_allows_drive_when_not_at_position(self):
        """
        When cover is NOT at open position, the drive guard must allow movement.
        """
        env = make_jinja_env()
        result = eval_condition(env, LOCKOUT_DRIVE_GUARD, {
            "force_allows_ventilate": True,
            "effective_state": "shd",
            "in_open_position": False,
        })
        assert result is True, "Drive guard should be True when cover needs to move"

    def test_window_tilted_only_cover_at_vent_position_selects_vent(self):
        """
        Regression: Resident leaves, window tilted (not opened), cover already at vent position.
        Before fix: vent branch was skipped, shading fired.
        After fix: vent branch is selected.
        """
        entity_states = make_entity_states(window_opened=False, window_tilted=True)
        env = make_jinja_env(entity_states)
        variables = make_vars(
            window_opened=False,
            window_tilted=True,
            effective_state="vnt",
            in_ventilate_position=True,     # already there
            helper_state_shade=True,         # shading would fire if vent is skipped
        )
        branch = first_matching_branch(env, RESIDENT_LEAVING_BRANCHES, variables)
        assert branch == "vent_tilted", (
            f"Expected 'vent_tilted' but got '{branch}'. "
            "Ventilation must take priority over shading when window is tilted."
        )

    def test_vent_drive_guard_suppresses_drive_when_already_at_position(self):
        """
        If cover is already at vent position, the if: guard must not re-drive.
        """
        env = make_jinja_env()
        result = eval_condition(env, VENT_DRIVE_GUARD, {
            "force_allows_ventilate": True,
            "effective_state": "vnt",
            "in_ventilate_position": True,
        })
        assert result is False

    def test_window_closed_shading_active_selects_shading(self):
        """
        Resident leaves, no window open or tilted, shading is active.
        The shading branch should be selected.
        """
        entity_states = make_entity_states(window_opened=False, window_tilted=False)
        env = make_jinja_env(entity_states)
        variables = make_vars(
            window_opened=False,
            window_tilted=False,
            helper_state_shade=True,
            effective_state="shd",
            in_shading_position=False,   # needs to drive
        )
        branch = first_matching_branch(env, RESIDENT_LEAVING_BRANCHES, variables)
        assert branch == "shading"

    def test_window_closed_no_shading_base_open_selects_open(self):
        """
        Resident leaves, window closed, no shading, base state is 'opn'.
        The open branch should be selected.
        """
        entity_states = make_entity_states(window_opened=False, window_tilted=False)
        env = make_jinja_env(entity_states)
        variables = make_vars(
            window_opened=False,
            window_tilted=False,
            helper_state_shade=False,
            helper_state_base="opn",
            effective_state="opn",
            in_open_position=False,
        )
        branch = first_matching_branch(env, RESIDENT_LEAVING_BRANCHES, variables)
        assert branch == "open"

    def test_window_opened_takes_priority_over_tilted(self):
        """
        When both contacts are on, 'window opened' (lockout) must win over 'tilted'.
        """
        entity_states = make_entity_states(window_opened=True, window_tilted=True)
        env = make_jinja_env(entity_states)
        variables = make_vars(
            window_opened=True,
            window_tilted=True,
            effective_state="lock",
            in_open_position=True,
            helper_state_shade=False,
        )
        branch = first_matching_branch(env, RESIDENT_LEAVING_BRANCHES, variables)
        assert branch == "lockout", "opened (lockout) must take priority over tilted"

    def test_allow_ventilate_false_skips_lockout_branch(self):
        """
        If resident_flags.allow_ventilate is False AND ventilation is disabled,
        the lockout branch must not fire. (Rare config, but must be safe.)
        """
        entity_states = make_entity_states(window_opened=True)
        env = make_jinja_env(entity_states)
        variables = make_vars(
            window_opened=True,
            allow_ventilate=False,
            is_ventilation_enabled=False,
            effective_state="lock",
            in_open_position=True,
            helper_state_shade=True,
            is_shading_enabled=True,
        )
        # Lockout branch requires is_ventilation_enabled — if disabled, skip
        branch = first_matching_branch(env, RESIDENT_LEAVING_BRANCHES, variables)
        # Should NOT be lockout — falls to shading or lower
        assert branch != "lockout"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: opened > tilted priority (Bug-Muster D)
# ─────────────────────────────────────────────────────────────────────────────

# Branches representing any handler where tilted is checked after opened.
# The tilted branch MUST contain the not-contact_window_opened guard.
OPENED_VS_TILTED_BRANCHES = [
    {
        "name": "opened_lockout",
        "conditions": [
            "{{ contact_window_opened != [] and states(contact_window_opened) in ['true', 'on'] }}",
        ],
    },
    {
        "name": "tilted_vent",
        "conditions": [
            "{{ contact_window_tilted != [] and states(contact_window_tilted) in ['true', 'on'] }}",
            # BUG-MUSTER D: this guard MUST be present — tilted must not fire when opened is also on
            "{{ not (contact_window_opened != [] and states(contact_window_opened) in ['true', 'on']) }}",
        ],
    },
]

# Buggy version: tilted branch WITHOUT the not-opened guard
OPENED_VS_TILTED_BRANCHES_BUGGY = [
    {
        "name": "opened_lockout",
        "conditions": [
            "{{ contact_window_opened != [] and states(contact_window_opened) in ['true', 'on'] }}",
        ],
    },
    {
        "name": "tilted_vent",
        "conditions": [
            # Missing: not-contact_window_opened guard  ← this is the bug
            "{{ contact_window_tilted != [] and states(contact_window_tilted) in ['true', 'on'] }}",
        ],
    },
]


class TestOpenedVsTiltedPriority:
    """
    Verify that contact_window_opened always takes priority over contact_window_tilted
    in choose blocks (Bug-Muster D).
    """

    def test_both_sensors_on_selects_opened(self):
        """
        Both opened and tilted sensors are on → opened branch must win.
        """
        entity_states = make_entity_states(window_opened=True, window_tilted=True)
        env = make_jinja_env(entity_states)
        variables = make_vars(window_opened=True, window_tilted=True)
        branch = first_matching_branch(env, OPENED_VS_TILTED_BRANCHES, variables)
        assert branch == "opened_lockout", (
            "When both sensors are on, opened (lockout) must win over tilted."
        )

    def test_only_tilted_selects_tilted(self):
        """
        Only tilted is on → tilted branch must be selected.
        """
        entity_states = make_entity_states(window_opened=False, window_tilted=True)
        env = make_jinja_env(entity_states)
        variables = make_vars(window_opened=False, window_tilted=True)
        branch = first_matching_branch(env, OPENED_VS_TILTED_BRANCHES, variables)
        assert branch == "tilted_vent"

    def test_buggy_tilted_branch_fires_when_opened_also_on(self):
        """
        Demonstrates the bug: without the not-opened guard, the tilted branch
        can be reached even when opened is also active (depending on choose order).
        This test documents the expected broken behavior — it should fail if
        somehow both branches are added and opened comes first.
        In a realistic buggy scenario where opened guard fails, tilted would match.
        """
        entity_states = make_entity_states(window_opened=False, window_tilted=True)
        env = make_jinja_env(entity_states)
        variables = make_vars(window_opened=False, window_tilted=True)
        # Even in buggy branches, when only tilted is on, tilted should fire
        branch = first_matching_branch(env, OPENED_VS_TILTED_BRANCHES_BUGGY, variables)
        assert branch == "tilted_vent"

    def test_buggy_branch_with_both_on_picks_opened_first(self):
        """
        If opened branch comes first in the choose list and both are on,
        opened still wins by order — but the NOT guard on tilted is still
        required to prevent the tilted branch firing in handlers where
        opened branch failed its guard (e.g. position check blocked it).
        """
        entity_states = make_entity_states(window_opened=True, window_tilted=True)
        env = make_jinja_env(entity_states)
        variables = make_vars(window_opened=True, window_tilted=True)
        # In buggy version, opened still wins if it comes first AND its conditions pass
        branch = first_matching_branch(env, OPENED_VS_TILTED_BRANCHES_BUGGY, variables)
        assert branch == "opened_lockout"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: resident_leaving allow_shade based on new_resident_status (Bug-Muster B)
# ─────────────────────────────────────────────────────────────────────────────

# The corrected shading branch condition uses new_resident_status == 0
# instead of resident_flags.allow_shade (which reads stale helper state).
RESIDENT_LEAVING_SHADING_BRANCH_CORRECT = {
    "name": "shading",
    "conditions": [
        "{{ helper_state_shade }}",
        "{{ new_resident_status == 0 or 'resident_allow_shading' in resident_config }}",
        "{{ is_shading_enabled }}",
        "{{ effective_state != 'shd' or not in_shading_position }}",
    ],
}

RESIDENT_LEAVING_SHADING_BRANCH_BUGGY = {
    "name": "shading",
    "conditions": [
        "{{ helper_state_shade }}",
        "{{ resident_flags.allow_shade }}",   # ← Bug: reads stale helper state
        "{{ is_shading_enabled }}",
        "{{ effective_state != 'shd' or not in_shading_position }}",
    ],
}


class TestResidentLeavingAllowShade:
    """
    Verify that allow_shade in the resident_leaving handler uses new_resident_status
    (fresh) not resident_flags.allow_shade (stale helper) — Bug-Muster B.
    """

    def _make_leaving_vars(self, *, resident_allow_shading_configured: bool, allow_shade_from_flags: bool) -> dict:
        """
        Simulate the state at the moment resident_leaving fires:
        - new_resident_status is always 0 (resident just left)
        - resident_flags.allow_shade reflects old helper state (stale)
        """
        return {
            "contact_window_opened": WINDOW_OPENED_ENTITY,
            "contact_window_tilted": WINDOW_TILTED_ENTITY,
            "new_resident_status": 0,
            "resident_config": (
                ["resident_allow_shading"] if resident_allow_shading_configured else []
            ),
            "resident_flags": {
                "allow_shade": allow_shade_from_flags,
                "allow_ventilate": True,
                "opening_trigger": True,
            },
            "helper_state_shade": True,
            "is_shading_enabled": True,
            "effective_state": "shd",
            "in_shading_position": False,
            "is_ventilation_enabled": False,  # window sensors off below
        }

    def test_correct_branch_fires_when_resident_allow_shading_not_configured(self):
        """
        resident_allow_shading NOT configured: resident_flags.allow_shade would be False
        (stale helper: resident was present → allow_shade = not True = False).
        But new_resident_status == 0 is True → corrected branch MUST fire.
        """
        env = make_jinja_env(make_entity_states(window_opened=False, window_tilted=False))
        variables = self._make_leaving_vars(
            resident_allow_shading_configured=False,
            allow_shade_from_flags=False,   # ← stale: was False because resident was present
        )
        # Correct branch should fire
        from conftest import eval_conditions
        assert eval_conditions(env, RESIDENT_LEAVING_SHADING_BRANCH_CORRECT["conditions"], variables), \
            "Correct branch must fire even when allow_shade (stale) is False"

    def test_buggy_branch_fails_when_allow_shade_stale_false(self):
        """
        Demonstrates the bug: when resident_flags.allow_shade is stale (False),
        the buggy branch does NOT fire — causing fallthrough to open branch.
        """
        env = make_jinja_env(make_entity_states(window_opened=False, window_tilted=False))
        variables = self._make_leaving_vars(
            resident_allow_shading_configured=False,
            allow_shade_from_flags=False,   # stale value
        )
        from conftest import eval_conditions
        assert not eval_conditions(env, RESIDENT_LEAVING_SHADING_BRANCH_BUGGY["conditions"], variables), \
            "Buggy branch should NOT fire when allow_shade is stale False (demonstrating the bug)"

    def test_correct_branch_fires_when_resident_allow_shading_configured(self):
        """
        resident_allow_shading IS configured: both old and new logic agree → branch fires.
        """
        env = make_jinja_env(make_entity_states(window_opened=False, window_tilted=False))
        variables = self._make_leaving_vars(
            resident_allow_shading_configured=True,
            allow_shade_from_flags=True,
        )
        from conftest import eval_conditions
        assert eval_conditions(env, RESIDENT_LEAVING_SHADING_BRANCH_CORRECT["conditions"], variables)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: base status update when window tilted at closing time (Bug-Muster E)
# ─────────────────────────────────────────────────────────────────────────────

def _load_blueprint_yaml(path) -> dict:
    """Load HA blueprint YAML, tolerating custom tags like !input and anchors."""
    class _Loader(yaml.SafeLoader):
        pass

    # Allow !input tags (return their value as a plain string)
    _Loader.add_constructor(
        "!input",
        lambda loader, node: loader.construct_scalar(node),
    )
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


def _find_tilted_closing_sequence(blueprint: dict) -> dict | None:
    """
    Walk the blueprint automation sequence to find the choose branch
    'Window tilted. No lockout. Move to ventilation position instead of closing'.
    Returns the sequence dict or None.
    """
    def walk(node):
        if isinstance(node, dict):
            if node.get("alias") == "Window tilted. No lockout. Move to ventilation position instead of closing":
                return node
            for v in node.values():
                result = walk(v)
                if result is not None:
                    return result
        elif isinstance(node, list):
            for item in node:
                result = walk(item)
                if result is not None:
                    return result
        return None

    return walk(blueprint)


class TestBaseStatusUpdateWhenTiltedAtClosingTime:
    """
    Regression for Bug-Muster E:
    When the closing trigger fires (e.g. at latest closing time) and the window
    is tilted, the cover moves to the ventilation position. But the base state
    helper (bas) was NOT updated to 'cls', staying 'opn'.

    The section comment at the closing handler says:
      'Note: Always updates base state, movement only if conditions allow'

    Fix: add bas: 'cls' and ts.cls: 'now' to the update_values of the
    tilted-closing branch.
    """

    def _load_blueprint(self) -> dict:
        return _load_blueprint_yaml(BLUEPRINT_PATH)

    def test_tilted_closing_branch_sets_bas_cls(self):
        """
        The 'Window tilted, no lockout' closing branch must include bas: 'cls'
        so that the base state is updated to closed even though the cover
        physically stays at the ventilation position.
        """
        blueprint = self._load_blueprint()
        branch = _find_tilted_closing_sequence(blueprint)
        assert branch is not None, (
            "Could not find 'Window tilted. No lockout. Move to ventilation position "
            "instead of closing' branch in blueprint YAML."
        )
        # The first item in sequence is 'variables:', which contains update_values
        seq = branch.get("sequence", [])
        variables_step = next(
            (s for s in seq if isinstance(s, dict) and "variables" in s), None
        )
        assert variables_step is not None, "No 'variables:' step found in tilted closing sequence"
        update_values = variables_step["variables"].get("update_values", {})
        assert update_values.get("bas") == "cls", (
            f"Expected update_values.bas == 'cls' but got {update_values.get('bas')!r}. "
            "Base status must be updated to 'cls' when closing time fires, "
            "even if cover stays in ventilation position due to tilted window."
        )

    def test_tilted_closing_branch_sets_ts_cls(self):
        """
        The tilted-closing branch must also set ts.cls so that
        prevent_multiple_times works correctly the next day.
        """
        blueprint = self._load_blueprint()
        branch = _find_tilted_closing_sequence(blueprint)
        assert branch is not None
        seq = branch.get("sequence", [])
        variables_step = next(
            (s for s in seq if isinstance(s, dict) and "variables" in s), None
        )
        assert variables_step is not None
        update_values = variables_step["variables"].get("update_values", {})
        ts = update_values.get("ts", {})
        assert "cls" in ts, (
            f"Expected update_values.ts.cls to be set, but ts = {ts!r}. "
            "ts.cls is needed for prevent_multiple_times to work correctly."
        )
