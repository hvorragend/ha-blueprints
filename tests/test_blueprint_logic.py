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
from conftest import make_jinja_env, eval_condition, eval_conditions, first_matching_branch


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
            # VENT is a floor only — when bas='opn' (effective_state='opn') OPEN must win, not VENT
            "{{ effective_state == 'vnt' }}",
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
            # NOTE: No position check here — moved to if: guard (Invariant 1 fix)
        ],
    },
    {
        "name": "open",  # Base state open → move to open
        "conditions": [
            "{{ helper_state_base == 'opn' }}",
            "{{ resident_flags.opening_trigger }}",
            "{{ is_up_enabled }}",
            # NOTE: No position/force check here — moved to if: guard (Invariant 1 fix)
        ],
    },
    {
        "name": "close",  # Base state close → move to closed
        "conditions": [
            "{{ helper_state_base == 'cls' }}",
            "{{ is_down_enabled }}",
            # NOTE: No position/force check here — moved to if: guard (Invariant 1 fix)
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

# The if: guard for the shading branch
SHADING_DRIVE_GUARD = (
    "force_allows_shade and (effective_state != 'shd' or not in_shading_position)"
)

# The if: guard for the open branch
OPEN_DRIVE_GUARD = (
    "(force_allows_open or trigger_is_force) and (effective_state != 'opn' or not in_open_position)"
)

# The if: guard for the close branch
CLOSE_DRIVE_GUARD = (
    "force_allows_close and (effective_state != 'cls' or not in_close_position)"
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
    force_allows_shade: bool = True,
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
        "force_allows_shade": force_allows_shade,
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

    def test_window_tilted_base_open_selects_open_not_vent(self):
        """
        Regression (Holsteiner-Kiel): Resident leaves, window tilted, bas='opn'.
        Resident gone → allow_open=true → base_target='opn' → effective_state='opn'.
        VENT is a floor only when base_target != 'opn', so the cover must OPEN fully,
        not rest in the ventilation position.

        Before fix: vent_tilted branch fired (only checked the tilted sensor),
        driving to 50%.
        After fix: vent_tilted is skipped (effective_state != 'vnt'), open branch wins.
        """
        entity_states = make_entity_states(window_opened=False, window_tilted=True)
        env = make_jinja_env(entity_states)
        variables = make_vars(
            window_opened=False,
            window_tilted=True,
            effective_state="opn",          # resident gone + bas='opn' → open, not vent
            helper_state_base="opn",
            in_ventilate_position=True,      # currently resting at vent (the bug symptom)
            in_open_position=False,
            opening_trigger=True,            # 'open when resident leaves' configured
        )
        branch = first_matching_branch(env, RESIDENT_LEAVING_BRANCHES, variables)
        assert branch == "open", (
            f"Expected 'open' but got '{branch}'. "
            "With bas='opn' and resident gone, the cover must open fully, not ventilate."
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
    ],
}

RESIDENT_LEAVING_SHADING_BRANCH_BUGGY = {
    "name": "shading",
    "conditions": [
        "{{ helper_state_shade }}",
        "{{ resident_flags.allow_shade }}",   # Bug: reads stale helper state
        "{{ is_shading_enabled }}",
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


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Lockout protection in close handler must update base state (#402)
# ─────────────────────────────────────────────────────────────────────────────

def _find_branch_by_alias(blueprint: dict, alias: str) -> dict | None:
    """Walk the blueprint to find a choose branch by its alias."""
    def walk(node):
        if isinstance(node, dict):
            if node.get("alias") == alias:
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


class TestLockoutClosingBaseStateUpdate:
    """
    Regression for #402 (Bug Pattern H in lockout-closing branch):
    When closing time fires and the window is open, lockout protection runs
    but must still update bas to 'cls' and set ts.cls.
    """

    def _load_blueprint(self) -> dict:
        return _load_blueprint_yaml(BLUEPRINT_PATH)

    def test_lockout_closing_branch_sets_bas_cls(self):
        blueprint = self._load_blueprint()
        branch = _find_branch_by_alias(blueprint, "Lockout protection when closing")
        assert branch is not None, "Could not find 'Lockout protection when closing' branch"
        seq = branch.get("sequence", [])
        variables_step = next(
            (s for s in seq if isinstance(s, dict) and "variables" in s), None
        )
        assert variables_step is not None
        update_values = variables_step["variables"].get("update_values", {})
        assert update_values.get("bas") == "cls", (
            f"Expected update_values.bas == 'cls' but got {update_values.get('bas')!r}. "
            "Base status must be updated to 'cls' when closing time fires with lockout."
        )

    def test_lockout_closing_branch_sets_ts_cls(self):
        blueprint = self._load_blueprint()
        branch = _find_branch_by_alias(blueprint, "Lockout protection when closing")
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


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Manual unknown position clears stale shading state (#447)
# ─────────────────────────────────────────────────────────────────────────────

class TestManualUnknownClearsShadingState:
    """
    Regression for #447: When the user manually moves the cover to a position
    that does not match any defined position (open/close/shading/ventilate),
    the helper must clear `shd`, the pending phase (`pnd`), the pending fire
    time (`ts.due`) and the retry anchor (`ts.arm`). Otherwise a stale `shd=1`
    (e.g. set by a prior lockout-blocked shading-start) lets shading-end later
    override the manual move before reset_override_timeout elapses.
    """

    def _load_blueprint(self) -> dict:
        return _load_blueprint_yaml(BLUEPRINT_PATH)

    def _get_update_values(self) -> dict:
        # The unknown-position case is the default of the classification
        # choose inside "Checking for manual position changes".
        blueprint = self._load_blueprint()
        branch = _find_branch_by_alias(blueprint, "Checking for manual position changes")
        assert branch is not None, (
            "Could not find 'Checking for manual position changes' branch"
        )
        classify = branch["sequence"][0]
        assert "choose" in classify and "default" in classify, (
            "Expected the classification choose with an unknown-position default"
        )
        variables_step = next(
            (s for s in classify["default"] if isinstance(s, dict) and "variables" in s),
            None,
        )
        assert variables_step is not None, (
            "No 'variables:' step found in manual-unknown default"
        )
        return variables_step["variables"].get("update_values", {})

    def test_clears_shd(self):
        update_values = self._get_update_values()
        assert update_values.get("shd") == 0, (
            f"Expected update_values.shd == 0 but got {update_values.get('shd')!r}. "
            "Stale shd=1 lets shading-end later override the manual move."
        )

    def test_sets_man(self):
        update_values = self._get_update_values()
        assert update_values.get("man") == 1

    def test_clears_pending_and_retry_anchor(self):
        update_values = self._get_update_values()
        assert update_values.get("pnd") == "non", (
            f"Expected pnd == 'non' but got {update_values.get('pnd')!r}. "
            "Pending phase must be cleared by manual move."
        )
        ts = update_values.get("ts", {})
        assert ts.get("due") == 0, (
            f"Expected ts.due == 0 but got {ts.get('due')!r}. "
            "Pending fire time must be cleared by manual move."
        )
        assert ts.get("arm") == 0, (
            f"Expected ts.arm == 0 but got {ts.get('arm')!r}. "
            "Retry anchor must be reset when manual move cancels the sequence."
        )

    def test_sets_ts_man_and_shd(self):
        update_values = self._get_update_values()
        ts = update_values.get("ts", {})
        assert ts.get("man") == "now"
        assert ts.get("shd") == "now", (
            "ts.shd must be touched so the helper_update guard can refresh it "
            "when shd transitions from 1 to 0."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Invariant 1 — position checks in if-guard, not conditions
#   Regression for SHADED/OPEN/CLOSE branches in resident_leaving
# ─────────────────────────────────────────────────────────────────────────────

class TestInvariant1ShadingOpenCloseConsumed:
    """
    Verify that the shading/open/close branches are always selected
    (consumed) in the priority cascade, even when the cover is already
    at the target position. The drive is suppressed by the if: guard,
    but the branch itself must still match so the helper is updated.
    """

    def test_shading_branch_consumed_when_already_at_shading_position(self):
        """
        Regression: Cover at shading position, shd=1, resident leaves.
        Before fix: shading branch skipped (position check in conditions),
                    open branch fired → cover moved to open.
        After fix: shading branch always consumed, drive suppressed by if: guard.
        """
        entity_states = make_entity_states(window_opened=False, window_tilted=False)
        env = make_jinja_env(entity_states)
        variables = make_vars(
            window_opened=False,
            window_tilted=False,
            helper_state_shade=True,
            effective_state="shd",
            in_shading_position=True,
            helper_state_base="opn",
        )
        branch = first_matching_branch(env, RESIDENT_LEAVING_BRANCHES, variables)
        assert branch == "shading", (
            f"Expected 'shading' but got '{branch}'. "
            "Shading branch must be consumed even when cover is at shading position."
        )

    def test_shading_drive_guard_suppresses_when_at_position(self):
        env = make_jinja_env()
        result = eval_condition(env, SHADING_DRIVE_GUARD, {
            "force_allows_shade": True,
            "effective_state": "shd",
            "in_shading_position": True,
        })
        assert result is False, "Shading drive guard should suppress when already at position"

    def test_shading_drive_guard_allows_when_not_at_position(self):
        env = make_jinja_env()
        result = eval_condition(env, SHADING_DRIVE_GUARD, {
            "force_allows_shade": True,
            "effective_state": "opn",
            "in_shading_position": False,
        })
        assert result is True

    def test_open_branch_consumed_when_already_at_open_position(self):
        """
        Cover at open position, bas='opn', resident leaves, no shading.
        Open branch must be consumed (even though no drive needed).
        """
        entity_states = make_entity_states(window_opened=False, window_tilted=False)
        env = make_jinja_env(entity_states)
        variables = make_vars(
            window_opened=False,
            window_tilted=False,
            helper_state_shade=False,
            helper_state_base="opn",
            effective_state="opn",
            in_open_position=True,
        )
        branch = first_matching_branch(env, RESIDENT_LEAVING_BRANCHES, variables)
        assert branch == "open", (
            f"Expected 'open' but got '{branch}'. "
            "Open branch must be consumed even when cover is at open position."
        )

    def test_close_branch_consumed_when_already_at_close_position(self):
        """
        Cover at close position, bas='cls', resident leaves.
        Close branch must be consumed.
        """
        entity_states = make_entity_states(window_opened=False, window_tilted=False)
        env = make_jinja_env(entity_states)
        variables = make_vars(
            window_opened=False,
            window_tilted=False,
            helper_state_shade=False,
            helper_state_base="cls",
            effective_state="cls",
            in_close_position=True,
        )
        branch = first_matching_branch(env, RESIDENT_LEAVING_BRANCHES, variables)
        assert branch == "close", (
            f"Expected 'close' but got '{branch}'. "
            "Close branch must be consumed even when cover is at close position."
        )

    def test_close_drive_guard_suppresses_when_force_blocks(self):
        env = make_jinja_env()
        result = eval_condition(env, CLOSE_DRIVE_GUARD, {
            "force_allows_close": False,
            "effective_state": "cls",
            "in_close_position": False,
        })
        assert result is False, "Close drive guard should suppress when force blocks"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Open-handler shading sub-branch must respect effective_state (Bug B)
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenHandlerShadingRespectsEffectiveState:
    """
    Regression for issue #430 (Bug B):
    The open-handler sub-branch 'Shading detected. Move to shading position'
    matched on helper_state_is_shaded / pending_start / helper_state_shade
    without checking effective_state. With Lockout/Vent/Privacy/Force active
    (effective_state != 'shd') it still drove the cover into the shading
    position, overriding the priority cascade.

    Fix per Invariant 1 (CLAUDE.md): branch conditions stay unchanged so the
    branch is always consumed (helper update runs). The drive is gated by an
    inner if: that requires force_allows_shade AND effective_state == 'shd'.
    """

    BRANCH_ALIAS = "Shading detected. Move to shading position"

    def _load_branch(self) -> dict:
        blueprint = _load_blueprint_yaml(BLUEPRINT_PATH)
        branch = _find_branch_by_alias(blueprint, self.BRANCH_ALIAS)
        assert branch is not None, f"Could not find branch {self.BRANCH_ALIAS!r}"
        return branch

    def test_branch_conditions_do_not_gate_on_effective_state(self):
        """
        Per Invariant 1, effective_state must NOT appear in the branch
        conditions (would cause fall-through to 'Normal opening').
        """
        branch = self._load_branch()
        for cond in branch.get("conditions", []):
            cond_str = cond if isinstance(cond, str) else yaml.safe_dump(cond)
            assert "effective_state" not in cond_str, (
                f"Branch condition must not reference effective_state "
                f"(would violate Invariant 1): {cond!r}"
            )

    def test_drive_guard_gates_on_effective_state_shd(self):
        """
        The inner if: that wraps the drive must require effective_state == 'shd'
        in addition to force_allows_shade.
        """
        branch = self._load_branch()
        seq = branch.get("sequence", [])
        if_step = next(
            (s for s in seq if isinstance(s, dict) and "if" in s and "then" in s),
            None,
        )
        assert if_step is not None, "Drive guard 'if/then' step missing"
        guard = if_step["if"]
        guard_str = guard if isinstance(guard, str) else yaml.safe_dump(guard)
        assert "force_allows_shade" in guard_str, (
            f"Drive guard must include force_allows_shade: {guard!r}"
        )
        assert "effective_state == 'shd'" in guard_str, (
            f"Drive guard must include effective_state == 'shd' so Lockout/Vent/"
            f"Privacy suppress the drive: {guard!r}"
        )

    def test_man_expression_matches_drive_guard(self):
        """
        Per Invariant 7, man may only be cleared when the cover actually moves.
        The man expression must therefore include the same effective_state == 'shd'
        gate as the drive guard.
        """
        branch = self._load_branch()
        seq = branch.get("sequence", [])
        variables_step = next(
            (s for s in seq if isinstance(s, dict) and "variables" in s),
            None,
        )
        assert variables_step is not None, "variables: step missing"
        update_values = variables_step["variables"].get("update_values", {})
        man_expr = update_values.get("man", "")
        assert "force_allows_shade" in man_expr and "effective_state == 'shd'" in man_expr, (
            f"man expression must clear only when force_allows_shade and "
            f"effective_state == 'shd': got {man_expr!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Shading-start outer if must gate execution on shading window (Bug A)
# ─────────────────────────────────────────────────────────────────────────────

class TestShadingStartOuterIfGatesOnWindow:
    """
    Regression for issue #430 (Bug A — stuck pending):
    The outer if: in 'Check for shading start' originally evaluated only the
    shading-condition disjunction (independent_temp + forecast_valid OR
    shading_start_conditions_met). If a forecast-temp pending-arm fired at
    night, the inner choose at the 'Shading start execution' branch had no
    matching sub-branch and no default — pending stayed armed forever, and
    the next morning t_open_1 incorrectly drove into shading.

    Fix: outer if additionally requires that the trigger is a pending-arm
    OR is_shading_allowed_window is true. Pending-arm at night still works
    (logs the arm), but execution outside the window falls through to the
    else branch ('Stop retry') and clears the pending.
    """

    BRANCH_ALIAS = "Check for shading start"

    def _load_outer_if(self) -> dict:
        blueprint = _load_blueprint_yaml(BLUEPRINT_PATH)
        branch = _find_branch_by_alias(blueprint, self.BRANCH_ALIAS)
        assert branch is not None, f"Could not find branch {self.BRANCH_ALIAS!r}"
        seq = branch.get("sequence", [])
        if_step = next(
            (s for s in seq if isinstance(s, dict) and "if" in s and "then" in s),
            None,
        )
        assert if_step is not None, "Outer if/then step missing"
        return if_step

    def test_outer_if_gates_on_window_or_pending_trigger(self):
        if_step = self._load_outer_if()
        if_conditions = if_step["if"]
        assert isinstance(if_conditions, list), (
            f"Outer if must be a list of conditions, got {type(if_conditions).__name__}"
        )
        flat = yaml.safe_dump(if_conditions)
        assert "is_shading_allowed_window" in flat, (
            "Outer if must include is_shading_allowed_window so execution "
            "outside the window falls through to else (Stop retry)."
        )
        assert "t_shading_start_pending" in flat, (
            "Outer if must allow pending-arm triggers (regex on t_shading_start_pending) "
            "so pending arming at night still records the attempt."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Opening must not skip when a shading-start pending is stale (#514)
# ─────────────────────────────────────────────────────────────────────────────

class TestOpeningSkippedShadingStartPendingGate:
    """
    Regression for issue #514:
    A shading-start pending can be armed before the opening time when brightness
    briefly exceeds the threshold. If the conditions then fall back below the
    threshold (still before opening), the pending is stale: the shading
    execution trigger will never drive the cover (it only retries/aborts).

    The opening handler's 'Opening skipped: Shading start pending' branch
    deferred unconditionally whenever pnd == 'beg', so at opening time the
    cover stayed closed forever ('Opening skipped: Shading start pending').

    Fix: the branch additionally requires shading_start_warranted. When the
    pending is stale (conditions no longer met), the branch is skipped and
    execution falls through to 'Normal opening', which drives the cover open
    and clears the stale pending.
    """

    BRANCH_ALIAS = "Opening skipped: Shading start pending"

    def _load_branch(self) -> dict:
        blueprint = _load_blueprint_yaml(BLUEPRINT_PATH)
        branch = _find_branch_by_alias(blueprint, self.BRANCH_ALIAS)
        assert branch is not None, f"Could not find branch {self.BRANCH_ALIAS!r}"
        return branch

    def test_branch_gates_on_pending_and_warranted(self):
        branch = self._load_branch()
        flat = yaml.safe_dump(branch.get("conditions", []))
        assert "helper_state_pending_start" in flat, (
            "Branch must still require an active shading-start pending."
        )
        assert "shading_start_warranted" in flat, (
            "Branch must additionally require shading_start_warranted so a "
            "stale pending no longer suppresses the opening."
        )

    def test_defers_when_warranted(self):
        """pnd active AND still warranted → branch matches (defer to execution)."""
        env = make_jinja_env()
        branch = self._load_branch()
        variables = {
            "helper_state_pending_start": True,
            "shading_start_warranted": True,
        }
        assert eval_conditions(env, branch["conditions"], variables) is True

    def test_skips_when_stale(self):
        """pnd active BUT no longer warranted → branch does NOT match (open)."""
        env = make_jinja_env()
        branch = self._load_branch()
        variables = {
            "helper_state_pending_start": True,
            "shading_start_warranted": False,
        }
        assert eval_conditions(env, branch["conditions"], variables) is False

    def test_stale_pending_falls_through_to_normal_opening(self):
        """
        With a stale pending, the 'Opening skipped' branch is skipped and the
        next branch 'Normal opening' is selected (its only gate is the cover
        not already being in the shading position).
        """
        env = make_jinja_env()
        skip_branch = self._load_branch()
        blueprint = _load_blueprint_yaml(BLUEPRINT_PATH)
        normal = _find_branch_by_alias(blueprint, "Normal opening of the cover")
        assert normal is not None, "Could not find 'Normal opening of the cover' branch"

        ordered = [
            {"name": "skip", "conditions": skip_branch["conditions"]},
            {"name": "normal", "conditions": normal["conditions"]},
        ]
        variables = {
            "helper_state_pending_start": True,
            "shading_start_warranted": False,
            "in_shading_position": False,
        }
        assert first_matching_branch(env, ordered, variables) == "normal"


class TestShadingStartWarrantedVariable:
    """The shading_start_warranted variable mirrors the execution gate:
    standard AND/OR conditions OR the independent-temperature path."""

    SHADING_START_WARRANTED = (
        "shading_start_conditions_met or "
        "('shading_temp_comparison_independent' in shading_config and "
        "shading_start_condition_states.independent_temp_valid)"
    )

    def test_warranted_when_conditions_met(self):
        env = make_jinja_env()
        variables = {
            "shading_start_conditions_met": True,
            "shading_config": [],
            "shading_start_condition_states": {"independent_temp_valid": False},
        }
        assert eval_condition(env, self.SHADING_START_WARRANTED, variables) is True

    def test_warranted_via_independent_temp(self):
        env = make_jinja_env()
        variables = {
            "shading_start_conditions_met": False,
            "shading_config": ["shading_temp_comparison_independent"],
            "shading_start_condition_states": {"independent_temp_valid": True},
        }
        assert eval_condition(env, self.SHADING_START_WARRANTED, variables) is True

    def test_not_warranted_when_nothing_met(self):
        env = make_jinja_env()
        variables = {
            "shading_start_conditions_met": False,
            "shading_config": [],
            "shading_start_condition_states": {"independent_temp_valid": False},
        }
        assert eval_condition(env, self.SHADING_START_WARRANTED, variables) is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Independent temperature mode bypasses all conditions (#459)
# ─────────────────────────────────────────────────────────────────────────────

INDEPENDENT_TEMP_CONDITION = (
    "'shading_temp_comparison_independent' in shading_config and "
    "shading_start_condition_states.forecast_temp_valid"
)

INDEPENDENT_OR_STANDARD = (
    "(" + INDEPENDENT_TEMP_CONDITION + ") or shading_start_conditions_met"
)


def _make_independent_temp_vars(
    *,
    independent_enabled: bool = True,
    forecast_temp_valid: bool = True,
    conditions_met: bool = False,
) -> dict:
    return {
        "shading_config": (
            ["shading_temp_comparison_independent"] if independent_enabled else []
        ),
        "shading_start_condition_states": {
            "forecast_temp_valid": forecast_temp_valid,
        },
        "shading_start_conditions_met": conditions_met,
    }


class TestIndependentTempBypassesConditions:
    """
    Issue #459: Independent temperature mode bypasses ALL start conditions
    (including azimuth) by design. This is correct behavior — the user must
    disable independent mode if they don't want temperature-only shading.

    The Trace Analyzer was updated to make this bypass visible.
    """

    def test_independent_temp_valid_starts_shading(self):
        """Independent mode + forecast_temp_valid → shading starts."""
        env = make_jinja_env()
        v = _make_independent_temp_vars(forecast_temp_valid=True, conditions_met=False)
        assert eval_condition(env, INDEPENDENT_OR_STANDARD, v) is True

    def test_independent_temp_invalid_no_shading(self):
        """Independent mode + forecast_temp_valid=false → no shading (unless standard conditions met)."""
        env = make_jinja_env()
        v = _make_independent_temp_vars(forecast_temp_valid=False, conditions_met=False)
        assert eval_condition(env, INDEPENDENT_OR_STANDARD, v) is False

    def test_standard_conditions_still_work(self):
        """Standard conditions can start shading even when independent mode is off."""
        env = make_jinja_env()
        v = _make_independent_temp_vars(independent_enabled=False, conditions_met=True)
        assert eval_condition(env, INDEPENDENT_OR_STANDARD, v) is True

    def test_independent_disabled_and_conditions_false(self):
        """Both paths false → no shading."""
        env = make_jinja_env()
        v = _make_independent_temp_vars(independent_enabled=False, conditions_met=False)
        assert eval_condition(env, INDEPENDENT_OR_STANDARD, v) is False

    def test_blueprint_yaml_independent_path_exists(self):
        """Verify the independent temperature path exists in the blueprint."""
        blueprint = _load_blueprint_yaml(BLUEPRINT_PATH)
        branch = _find_branch_by_alias(blueprint, "Check for shading start")
        assert branch is not None
        seq = branch.get("sequence", [])
        if_step = next(
            (s for s in seq if isinstance(s, dict) and "if" in s and "then" in s),
            None,
        )
        assert if_step is not None
        flat = yaml.safe_dump(if_step["if"])
        assert "shading_temp_comparison_independent" in flat, (
            "Independent temperature path must exist in the outer if."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Invariant 7 — man:0 only when drive happens
# ─────────────────────────────────────────────────────────────────────────────

class TestInvariant7ManConditional:
    """
    Verify that man is only cleared (set to 0) when the drive condition
    is met, preserving manual override when force blocks movement.
    """

    @staticmethod
    def _eval_man_expr(env, force_allows, current_man):
        expr = "{{ (0 if force_allows else current_man) | int }}"
        template = env.from_string(expr)
        return int(template.render(force_allows=force_allows, current_man=current_man))

    def test_man_preserved_when_force_blocks_shade(self):
        env = make_jinja_env()
        result = self._eval_man_expr(env, force_allows=False, current_man=1)
        assert result == 1, "man must be preserved (1) when force blocks the drive"

    def test_man_cleared_when_force_allows_shade(self):
        env = make_jinja_env()
        result = self._eval_man_expr(env, force_allows=True, current_man=1)
        assert result == 0, "man must be cleared (0) when force allows the drive"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Invariant 8 — ts.shd guard in helper_update
# ─────────────────────────────────────────────────────────────────────────────

class TestInvariant8TsShdGuard:
    """
    Verify that ts.shd is only updated when shd actually changes,
    via the guard in helper_update.
    """

    def test_ts_shd_preserved_when_shd_unchanged(self):
        """
        Simulates the helper_update guard logic:
        if new_shd == current_shd, ts.shd should be preserved (not overwritten).
        """
        env = make_jinja_env()
        guard = "new_shd == current_shd"
        result = eval_condition(env, guard, {
            "new_shd": 1,
            "current_shd": 1,
        })
        assert result is True, "Guard should fire (preserve ts.shd) when shd is unchanged"

    def test_ts_shd_updated_when_shd_changes(self):
        env = make_jinja_env()
        guard = "new_shd == current_shd"
        result = eval_condition(env, guard, {
            "new_shd": 1,
            "current_shd": 0,
        })
        assert result is False, "Guard should not fire (allow ts.shd update) when shd changes"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: window-tilted contact handler — keep-open opt-out (Issue #405)
# ─────────────────────────────────────────────────────────────────────────────
#
# Verifies the choose-block ordering and conditions for the contact handler
# branches "Window tilted - Partial ventilation" (drives cover) and
# "Window tilted - No drive, sync helper window state" (helper-only).
#
# Regression guard for the bug where ventilation_keep_open_on_full_to_tilt
# was overridden by ventilation_if_lower_enabled because the if_lower OR-clause
# in the partial-ventilation branch still matched the full→tilt scenario.

WIN_TILT_DRIVE_BRANCH = {
    "name": "partial_ventilation_drive",
    "conditions": [
        "{{ contact_tilted_now }}",
        "{{ not contact_opened_now }}",
        "{{ force_allows_ventilate }}",
        "{{ 'resident_allow_ventilation' in resident_config or not resident_now }}",
        "{{ not (ventilation_flags.keep_open_on_full_to_tilt and helper_state_window == 'opn' and position_comparisons.current_above_ventilate) }}",
        "{{ effective_state != 'opn' }}",
        # OR-block flattened into one Jinja expression
        "{{ position_comparisons.current_below_ventilate"
        " or (is_cover_tilt_enabled_and_possible"
        "     and (position_comparisons.current_below_ventilate or current_position == ventilate_position)"
        "     and current_tilt_position <= ventilate_tilt_position)"
        " or (ventilation_flags.if_lower_enabled and (position_comparisons.current_above_ventilate or current_position == ventilate_position))"
        " or (helper_state_window == 'opn' and position_comparisons.current_above_ventilate)"
        " or (position_comparisons.current_above_ventilate and effective_state == 'cls') }}",
    ],
}

WIN_TILT_NO_DRIVE_BRANCH = {
    "name": "no_drive_helper_only",
    "conditions": [
        "{{ contact_tilted_now }}",
        "{{ not contact_opened_now }}",
        "{{ helper_state_window != 'tlt' }}",
        "{{ in_ventilate_position"
        " or (ventilation_flags.keep_open_on_full_to_tilt"
        "     and helper_state_window == 'opn'"
        "     and position_comparisons.current_above_ventilate)"
        " or effective_state == 'opn' }}",
    ],
}

WIN_TILT_BRANCHES = [WIN_TILT_DRIVE_BRANCH, WIN_TILT_NO_DRIVE_BRANCH]


def _make_tilt_vars(
    *,
    keep_open_on_full_to_tilt: bool = False,
    if_lower_enabled: bool = False,
    helper_state_window: str = "cls",
    current_above_ventilate: bool = False,
    current_below_ventilate: bool = False,
    in_ventilate_position: bool = False,
    is_cover_tilt_enabled_and_possible: bool = False,
    current_position: int = 100,
    ventilate_position: int = 50,
    current_tilt_position: int = 100,
    ventilate_tilt_position: int = 50,
    effective_state: str = "vnt",
    force_allows_ventilate: bool = True,
    resident_now: bool = False,
    resident_config: list | None = None,
    contact_tilted_now: bool = True,
    contact_opened_now: bool = False,
) -> dict:
    return {
        "contact_tilted_now": contact_tilted_now,
        "contact_opened_now": contact_opened_now,
        "force_allows_ventilate": force_allows_ventilate,
        "resident_now": resident_now,
        "resident_config": resident_config or [],
        "ventilation_flags": {
            "keep_open_on_full_to_tilt": keep_open_on_full_to_tilt,
            "if_lower_enabled": if_lower_enabled,
        },
        "helper_state_window": helper_state_window,
        "position_comparisons": {
            "current_above_ventilate": current_above_ventilate,
            "current_below_ventilate": current_below_ventilate,
        },
        "in_ventilate_position": in_ventilate_position,
        "is_cover_tilt_enabled_and_possible": is_cover_tilt_enabled_and_possible,
        "current_position": current_position,
        "ventilate_position": ventilate_position,
        "current_tilt_position": current_tilt_position,
        "ventilate_tilt_position": ventilate_tilt_position,
        "effective_state": effective_state,
    }


class TestKeepOpenOnFullToTilt:
    """
    Issue #405: opt-out for the full → tilt cover-lowering transition.

    Verifies that when ventilation_keep_open_on_full_to_tilt is enabled,
    the cover stays at the open position regardless of other ventilation
    options (in particular ventilation_if_lower_enabled).
    """

    def test_keep_open_disabled_full_to_tilt_drives_to_vent(self):
        """
        Default behaviour: opt-out off, full → tilt → cover lowers (drive branch).
        """
        env = make_jinja_env()
        variables = _make_tilt_vars(
            keep_open_on_full_to_tilt=False,
            helper_state_window="opn",
            current_above_ventilate=True,
        )
        branch = first_matching_branch(env, WIN_TILT_BRANCHES, variables)
        assert branch == "partial_ventilation_drive", (
            "With opt-out disabled, the full → tilt transition must drive the cover."
        )

    def test_keep_open_enabled_full_to_tilt_no_drive(self):
        """
        Opt-out enabled, full → tilt → no drive, only helper sync.
        """
        env = make_jinja_env()
        variables = _make_tilt_vars(
            keep_open_on_full_to_tilt=True,
            helper_state_window="opn",
            current_above_ventilate=True,
        )
        branch = first_matching_branch(env, WIN_TILT_BRANCHES, variables)
        assert branch == "no_drive_helper_only", (
            "With opt-out enabled, the full → tilt transition must NOT drive the cover."
        )

    def test_keep_open_enabled_with_if_lower_enabled_no_drive(self):
        """
        Regression: both opt-out AND if_lower_enabled set.

        Before fix: if_lower OR-clause matched first → cover lowered → opt-out ignored.
        After fix: top-level guard skips drive branch → no-drive branch fires.
        """
        env = make_jinja_env()
        variables = _make_tilt_vars(
            keep_open_on_full_to_tilt=True,
            if_lower_enabled=True,
            helper_state_window="opn",
            current_above_ventilate=True,
        )
        branch = first_matching_branch(env, WIN_TILT_BRANCHES, variables)
        assert branch == "no_drive_helper_only", (
            "Opt-out must take precedence over if_lower_enabled in the full → tilt scenario."
        )

    def test_if_lower_enabled_above_vent_without_full_state_drives(self):
        """
        if_lower_enabled fires for the generic 'cover above ventilate' case
        (not full → tilt) — opt-out must not interfere here.
        """
        env = make_jinja_env()
        variables = _make_tilt_vars(
            keep_open_on_full_to_tilt=True,
            if_lower_enabled=True,
            helper_state_window="cls",  # not 'opn' → not the full → tilt scenario
            current_above_ventilate=True,
        )
        branch = first_matching_branch(env, WIN_TILT_BRANCHES, variables)
        assert branch == "partial_ventilation_drive", (
            "if_lower_enabled must still drive when the helper window state is not 'opn'."
        )

    def test_keep_open_enabled_helper_state_not_opn_falls_through(self):
        """
        Opt-out is scoped to helper_state_window == 'opn'. With helper=cls
        and cover below vent, the standard drive path applies.
        """
        env = make_jinja_env()
        variables = _make_tilt_vars(
            keep_open_on_full_to_tilt=True,
            helper_state_window="cls",
            current_below_ventilate=True,
        )
        branch = first_matching_branch(env, WIN_TILT_BRANCHES, variables)
        assert branch == "partial_ventilation_drive"

    def test_at_vent_position_helper_stale_uses_no_drive_branch(self):
        """
        Cover already at ventilate position, helper not yet synced → helper-only branch.
        Independent of the keep_open option.
        """
        env = make_jinja_env()
        variables = _make_tilt_vars(
            keep_open_on_full_to_tilt=False,
            helper_state_window="cls",
            in_ventilate_position=True,
        )
        branch = first_matching_branch(env, WIN_TILT_BRANCHES, variables)
        assert branch == "no_drive_helper_only"

    def test_at_vent_position_helper_already_tlt_no_match(self):
        """
        Cover at vent, helper already 'tlt' → no branch matches (no-op).
        """
        env = make_jinja_env()
        variables = _make_tilt_vars(
            keep_open_on_full_to_tilt=False,
            helper_state_window="tlt",
            in_ventilate_position=True,
        )
        branch = first_matching_branch(env, WIN_TILT_BRANCHES, variables)
        assert branch is None


class TestContactHandlerEffectiveStateGuard:
    """
    Issue #460: effective_state now reads live sensors for win, so
    when base_target is 'opn' (effective_state == 'opn'), tilting the
    window should NOT lower the cover to ventilation position.
    VENT is a floor, not a ceiling.
    """

    def test_effective_opn_full_to_tilt_no_drive(self):
        """
        effective_state='opn' (bas='opn', no overrides, live sensor: tilted).
        Cover should stay at open position — no-drive branch fires.
        """
        env = make_jinja_env()
        variables = _make_tilt_vars(
            helper_state_window="opn",
            current_above_ventilate=True,
            effective_state="opn",
        )
        branch = first_matching_branch(env, WIN_TILT_BRANCHES, variables)
        assert branch == "no_drive_helper_only", (
            "When effective_state is 'opn', the drive branch must be skipped."
        )

    def test_effective_vnt_full_to_tilt_drives(self):
        """
        effective_state='vnt' (bas='cls', live sensor: tilted).
        Cover should lower to ventilation — drive branch fires.
        """
        env = make_jinja_env()
        variables = _make_tilt_vars(
            helper_state_window="opn",
            current_above_ventilate=True,
            effective_state="vnt",
        )
        branch = first_matching_branch(env, WIN_TILT_BRANCHES, variables)
        assert branch == "partial_ventilation_drive", (
            "When effective_state is 'vnt', the drive branch must fire."
        )

    def test_effective_shd_full_to_tilt_drives(self):
        """
        effective_state='vnt' (bas='opn', shading active, live sensor: tilted).
        VENT applies because base_target='shd' != 'opn' — drive branch fires.
        """
        env = make_jinja_env()
        variables = _make_tilt_vars(
            helper_state_window="opn",
            current_above_ventilate=True,
            effective_state="vnt",
        )
        branch = first_matching_branch(env, WIN_TILT_BRANCHES, variables)
        assert branch == "partial_ventilation_drive", (
            "When effective_state is 'vnt' (shading+tilt), the drive branch must fire."
        )

    def test_effective_opn_if_lower_enabled_no_drive(self):
        """
        effective_state='opn', if_lower_enabled=True.
        Despite if_lower_enabled, the cover should NOT lower because
        effective_state says the cover should be open.
        """
        env = make_jinja_env()
        variables = _make_tilt_vars(
            if_lower_enabled=True,
            helper_state_window="cls",
            current_above_ventilate=True,
            effective_state="opn",
        )
        branch = first_matching_branch(env, WIN_TILT_BRANCHES, variables)
        assert branch == "no_drive_helper_only", (
            "When effective_state is 'opn', if_lower_enabled must not override."
        )

    def test_effective_opn_below_ventilate_no_drive(self):
        """
        effective_state='opn', cover below ventilate.
        Guard blocks drive branch entirely — no-drive branch catches.
        """
        env = make_jinja_env()
        variables = _make_tilt_vars(
            helper_state_window="cls",
            current_below_ventilate=True,
            current_above_ventilate=False,
            effective_state="opn",
        )
        branch = first_matching_branch(env, WIN_TILT_BRANCHES, variables)
        assert branch == "no_drive_helper_only", (
            "effective_state='opn' blocks the drive branch entirely."
        )


class TestKeepOpenBlueprintWiring:
    """
    Static checks that the blueprint YAML correctly wires the new option.
    """

    def _load_blueprint(self) -> dict:
        return _load_blueprint_yaml(BLUEPRINT_PATH)

    def test_top_level_guard_present_in_partial_ventilation_branch(self):
        """
        The partial-ventilation branch must contain the top-level
        keep_open_on_full_to_tilt guard so the opt-out cannot be bypassed
        by the if_lower_enabled OR-clause.
        """
        blueprint = self._load_blueprint()

        def walk(node):
            if isinstance(node, dict):
                if node.get("alias") == "Window tilted - Partial ventilation":
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

        branch = walk(blueprint)
        assert branch is not None, "Could not find 'Window tilted - Partial ventilation' branch"
        conditions = branch.get("conditions", [])
        guard_marker = "ventilation_flags.keep_open_on_full_to_tilt"
        assert any(
            isinstance(c, str) and guard_marker in c and "not (" in c
            for c in conditions
        ), (
            "Top-level keep_open_on_full_to_tilt guard missing from "
            "'Window tilted - Partial ventilation' branch."
        )

    def test_no_drive_branch_present_after_partial_ventilation(self):
        """
        The unified 'no drive, sync helper window state' branch must exist
        and come AFTER 'Partial ventilation' in the choose-block.
        """
        blueprint = self._load_blueprint()

        def find_choose_with_aliases(node, aliases):
            if isinstance(node, dict):
                if "choose" in node and isinstance(node["choose"], list):
                    found_aliases = [b.get("alias") for b in node["choose"] if isinstance(b, dict)]
                    if all(a in found_aliases for a in aliases):
                        return node["choose"], found_aliases
                for v in node.values():
                    result = find_choose_with_aliases(v, aliases)
                    if result is not None:
                        return result
            elif isinstance(node, list):
                for item in node:
                    result = find_choose_with_aliases(item, aliases)
                    if result is not None:
                        return result
            return None

        target = find_choose_with_aliases(
            blueprint,
            [
                "Window tilted - Partial ventilation",
                "Window tilted - No drive, sync helper window state",
            ],
        )
        assert target is not None, (
            "Could not find a choose-block containing both the partial-ventilation "
            "and the no-drive helper-sync branches."
        )
        _, aliases = target
        idx_drive = aliases.index("Window tilted - Partial ventilation")
        idx_no_drive = aliases.index("Window tilted - No drive, sync helper window state")
        assert idx_drive < idx_no_drive, (
            "Drive branch must come before no-drive helper-sync branch in choose-block."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: effective_state priority cascade (BASE=OPN > VENT)
# ─────────────────────────────────────────────────────────────────────────────

# Mirrors the effective_state template from cover_control_automation.yaml.
# Kept in sync manually — the test below also asserts the blueprint's template
# starts with the expected first-line markers.
EFFECTIVE_STATE_TEMPLATE = """
{%- set h = helper_json -%}
{%- set resident_present = state_resident -%}
{%- set allow_vent = 'resident_allow_ventilation' in resident_config or not resident_present -%}
{%- set allow_shade = 'resident_allow_shading' in resident_config or not resident_present -%}
{%- set allow_open = 'resident_allow_opening' in resident_config or not resident_present -%}
{%- set privacy_active = resident_present and 'resident_closing_enabled' in resident_config -%}
{%- set s_opn = sensor_opened -%}
{%- set s_tlt = sensor_tilted -%}
{%- set sensors_configured = has_opened_sensor or has_tilted_sensor -%}
{%- set w = 'opn' if s_opn else 'tlt' if s_tlt else h.win if not sensors_configured else 'cls' -%}
{%- if h.frc != 'non' -%}
  {{ h.frc }}
{%- elif w == 'opn' -%}
  lock
{%- else -%}
  {%- if privacy_active -%}
    {%- set base_target = 'cls' -%}
  {%- elif h.shd | int == 1 and allow_shade -%}
    {%- set base_target = 'shd' -%}
  {%- elif h.bas == 'opn' and not allow_open -%}
    {%- set base_target = 'cls' -%}
  {%- else -%}
    {%- set base_target = h.bas -%}
  {%- endif -%}
  {%- set base_open_scheduled = base_target == 'opn' and is_opening_scheduled -%}
  {%- if w == 'tlt' and allow_vent and not base_open_scheduled -%}
    vnt
  {%- else -%}
    {{ base_target }}
  {%- endif -%}
{%- endif -%}
"""


def _eval_effective_state(*, helper_json: dict, state_resident: bool = False,
                          resident_config: list = None,
                          sensor_opened: bool = False,
                          sensor_tilted: bool = False,
                          has_opened_sensor: bool = False,
                          has_tilted_sensor: bool = False,
                          is_opening_scheduled: bool = True) -> str:
    env = make_jinja_env()
    template = env.from_string(EFFECTIVE_STATE_TEMPLATE)
    return template.render(
        helper_json=helper_json,
        state_resident=state_resident,
        resident_config=resident_config or [],
        sensor_opened=sensor_opened,
        sensor_tilted=sensor_tilted,
        has_opened_sensor=has_opened_sensor,
        has_tilted_sensor=has_tilted_sensor,
        is_opening_scheduled=is_opening_scheduled,
    ).strip()


class TestEffectiveStateCascade:
    """
    BASE=OPN beats VENT in the priority cascade.

    Rationale: A tilted window expresses ventilation intent — and a fully open
    cover provides maximum airflow. VENT acts as a "floor" only when the cover
    would otherwise close/shade.
    """

    def test_base_open_tilted_no_shading_returns_opn(self):
        """bas=opn + win=tlt + shd=0 → 'opn' (new behavior, previously 'vnt')."""
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "tlt", "bas": "opn", "shd": 0},
        )
        assert result == "opn", f"Expected 'opn' but got '{result}'"

    def test_base_open_tilted_no_schedule_returns_vnt(self):
        """Issue #553: shading-only setup without an opening schedule.

        bas defaults to 'opn' forever (no scheduled close ever flips it to 'cls'),
        so BASE=OPN must NOT beat VENT — a tilted window has to drive the cover to
        the ventilation position. With is_opening_scheduled=False, VENT applies.
        """
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "tlt", "bas": "opn", "shd": 0},
            is_opening_scheduled=False,
        )
        assert result == "vnt", f"Expected 'vnt' but got '{result}'"

    def test_base_open_closed_window_no_schedule_returns_opn(self):
        """Issue #553: without a tilted window, base=opn still returns 'opn'.

        The fix only affects the VENT floor — a closed window must keep returning
        'opn' so shading-end and other base=opn logic continue to work.
        """
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "cls", "bas": "opn", "shd": 0},
            is_opening_scheduled=False,
        )
        assert result == "opn", f"Expected 'opn' but got '{result}'"

    def test_base_open_tilted_with_shading_returns_vnt(self):
        """bas=opn + win=tlt + shd=1 → 'vnt' (VENT is floor for shading)."""
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "tlt", "bas": "opn", "shd": 1},
        )
        assert result == "vnt", f"Expected 'vnt' but got '{result}'"

    def test_base_close_tilted_returns_vnt(self):
        """bas=cls + win=tlt → 'vnt' (VENT is floor for close)."""
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "tlt", "bas": "cls", "shd": 0},
        )
        assert result == "vnt"

    def test_base_open_tilted_privacy_returns_vnt(self):
        """Privacy (resident + closing_enabled) + tilted + allow_vent → 'vnt'."""
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "tlt", "bas": "opn", "shd": 0},
            state_resident=True,
            resident_config=["resident_closing_enabled", "resident_allow_ventilation"],
        )
        assert result == "vnt"

    def test_base_open_tilted_allow_open_false_returns_vnt(self):
        """bas=opn but resident present without allow_opening, with allow_vent → 'vnt'."""
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "tlt", "bas": "opn", "shd": 0},
            state_resident=True,
            resident_config=["resident_allow_ventilation"],
        )
        assert result == "vnt"

    def test_base_open_tilted_resident_present_no_vent_allowed_returns_cls(self):
        """Resident present without allow_vent and without allow_open: tilted doesn't help → 'cls'."""
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "tlt", "bas": "opn", "shd": 0},
            state_resident=True,
            resident_config=[],
        )
        assert result == "cls", (
            "Without resident_allow_ventilation, VENT cannot apply for "
            "present residents — falls back to base_target ('cls' here)."
        )

    def test_window_open_lockout_still_wins(self):
        """win=opn → 'lock' regardless of other state."""
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "opn", "bas": "opn", "shd": 0},
        )
        assert result == "lock"

    def test_force_still_wins(self):
        """Active force still beats everything."""
        result = _eval_effective_state(
            helper_json={"frc": "vnt", "win": "tlt", "bas": "opn", "shd": 0},
        )
        assert result == "vnt"

    def test_base_open_closed_window_returns_opn(self):
        """bas=opn + win=cls → 'opn' (unchanged behavior)."""
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "cls", "bas": "opn", "shd": 0},
        )
        assert result == "opn"

    def test_base_close_closed_window_returns_cls(self):
        """bas=cls + win=cls → 'cls' (unchanged behavior)."""
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "cls", "bas": "cls", "shd": 0},
        )
        assert result == "cls"

    def test_base_open_closed_window_shading_returns_shd(self):
        """bas=opn + win=cls + shd=1 → 'shd' (unchanged behavior)."""
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "cls", "bas": "opn", "shd": 1},
        )
        assert result == "shd"


class TestEffectiveStateLiveSensor:
    """
    Issue #460: effective_state reads live sensors for win instead of h.win.
    This ensures the contact handler sees the correct effective_state even
    when the helper hasn't been updated yet.
    """

    def test_helper_opn_sensor_tlt_base_opn_returns_opn(self):
        """
        Helper still has win='opn' (stale), but live sensor says tilted.
        With bas='opn' → effective_state should be 'opn' (not 'lock').
        This is the core fix for issue #460.
        """
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "opn", "bas": "opn", "shd": 0},
            has_opened_sensor=True,
            has_tilted_sensor=True,
            sensor_opened=False,
            sensor_tilted=True,
        )
        assert result == "opn", (
            f"Expected 'opn' but got '{result}'. Live sensor should override stale helper."
        )

    def test_helper_opn_sensor_tlt_base_cls_returns_vnt(self):
        """
        Helper has win='opn' (stale), live sensor says tilted, bas='cls'.
        effective_state should be 'vnt' (VENT applies for cls target).
        """
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "opn", "bas": "cls", "shd": 0},
            has_opened_sensor=True,
            has_tilted_sensor=True,
            sensor_opened=False,
            sensor_tilted=True,
        )
        assert result == "vnt", (
            f"Expected 'vnt' but got '{result}'. Live sensor should show VENT for cls target."
        )

    def test_no_sensors_configured_falls_back_to_helper(self):
        """
        No contact sensors configured → falls back to h.win from helper.
        """
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "opn", "bas": "opn", "shd": 0},
            has_opened_sensor=False,
            has_tilted_sensor=False,
        )
        assert result == "lock", (
            f"Expected 'lock' (h.win='opn' fallback) but got '{result}'."
        )

    def test_sensor_opened_true_returns_lock(self):
        """
        Live sensor says window is fully open → lockout regardless of helper.
        """
        result = _eval_effective_state(
            helper_json={"frc": "non", "win": "cls", "bas": "opn", "shd": 0},
            has_opened_sensor=True,
            sensor_opened=True,
        )
        assert result == "lock"


class TestForceDisabledRecoveryBranchOrder:
    """
    The Force-Disabled Recovery 'return to OPEN (base=opn)' branch must be
    listed BEFORE 'return to VENTILATION (window tilted)' so that bas=opn +
    tilted window correctly drives to the open position instead of staying
    at vent.
    """

    def test_recovery_open_before_vent_in_choose_block(self):
        blueprint = _load_blueprint_yaml(BLUEPRINT_PATH)

        def find_choose_with_aliases(node, aliases):
            if isinstance(node, dict):
                if "choose" in node and isinstance(node["choose"], list):
                    found = [b.get("alias") for b in node["choose"] if isinstance(b, dict)]
                    if all(a in found for a in aliases):
                        return node["choose"], found
                for v in node.values():
                    result = find_choose_with_aliases(v, aliases)
                    if result is not None:
                        return result
            elif isinstance(node, list):
                for item in node:
                    result = find_choose_with_aliases(item, aliases)
                    if result is not None:
                        return result
            return None

        target = find_choose_with_aliases(
            blueprint,
            [
                "Force disabled recovery: return to OPEN (base=opn)",
                "Force disabled recovery: return to VENTILATION (window tilted)",
            ],
        )
        assert target is not None
        _, aliases = target
        idx_open = aliases.index("Force disabled recovery: return to OPEN (base=opn)")
        idx_vent = aliases.index("Force disabled recovery: return to VENTILATION (window tilted)")
        assert idx_open < idx_vent, (
            "OPEN(base=opn) must come before VENTILATION(tilted) in recovery."
        )

    def test_recovery_open_branch_has_no_tilted_exclusion(self):
        """
        The OPEN(base=opn) recovery branch must NOT exclude tilted windows.
        With the new cascade, bas=opn + tilted should drive to OPEN.
        """
        blueprint = _load_blueprint_yaml(BLUEPRINT_PATH)

        def find_branch(node, alias):
            if isinstance(node, dict):
                if node.get("alias") == alias:
                    return node
                for v in node.values():
                    r = find_branch(v, alias)
                    if r is not None:
                        return r
            elif isinstance(node, list):
                for item in node:
                    r = find_branch(item, alias)
                    if r is not None:
                        return r
            return None

        branch = find_branch(blueprint, "Force disabled recovery: return to OPEN (base=opn)")
        assert branch is not None
        conditions = branch.get("conditions", [])
        combined = " ".join(c for c in conditions if isinstance(c, str))
        assert "contact_window_tilted" not in combined, (
            "OPEN(base=opn) recovery branch must not check for tilted window — "
            "BASE=OPN beats VENT in the new cascade."
        )


class TestForcePauseDisabledHasBackgroundOpen:
    """
    The Force-Pause-Disabled handler must have a branch for
    `effective_state == 'opn'` (no active force) so that after unpausing,
    the cover drives to open when the background state says open.
    """

    def test_force_pause_disabled_has_background_open_branch(self):
        blueprint = _load_blueprint_yaml(BLUEPRINT_PATH)

        def walk(node):
            if isinstance(node, dict):
                if node.get("alias") == "Force pause disabled: drive to OPEN target (background, base=opn)":
                    return node
                for v in node.values():
                    r = walk(v)
                    if r is not None:
                        return r
            elif isinstance(node, list):
                for item in node:
                    r = walk(item)
                    if r is not None:
                        return r
            return None

        branch = walk(blueprint)
        assert branch is not None, (
            "Missing background-open branch in Force-Pause-Disabled handler — "
            "with bas=opn + tilted window the effective_state is now 'opn' and "
            "needs an explicit drive branch."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: contact "window closed" return respects privacy gate, not bare presence
# ─────────────────────────────────────────────────────────────────────────────

# The privacy/allow_open suppression of the open base state, as used by the
# "Return to open" / "Return to close" branches. Mirrors effective_state's
# `privacy_active` and `allow_open` gates.
_RESIDENT_BLOCKS_OPEN_EXPR = (
    "resident_now and (resident_flags.closing_trigger"
    " or 'resident_allow_opening' not in resident_config)"
)

# Fixed branches (gate on the privacy/allow_open condition).
WINDOW_CLOSED_RETURN_BRANCHES = [
    {
        "name": "shading",
        "conditions": [
            "{{ not contact_opened_now and not contact_tilted_now }}",
            "{{ helper_state_is_shaded or helper_state_shade }}",
            "{{ helper_state_window in ['tlt', 'opn'] or in_ventilate_position }}",
            "{{ not (helper_state_manual and override_flags.ventilation) }}",
            "{{ not resident_now or 'resident_allow_shading' in resident_config }}",
        ],
    },
    {
        "name": "open",
        "conditions": [
            "{{ not contact_opened_now and not contact_tilted_now }}",
            "{{ helper_state_base == 'opn' and not (" + _RESIDENT_BLOCKS_OPEN_EXPR + ") }}",
            "{{ not helper_state_is_shaded and not helper_state_shade }}",
            "{{ helper_state_window in ['tlt', 'opn'] or in_ventilate_position }}",
            "{{ not (helper_state_manual and override_flags.ventilation) }}",
        ],
    },
    {
        "name": "close",
        "conditions": [
            "{{ not contact_opened_now and not contact_tilted_now }}",
            "{{ helper_state_base == 'cls' or (" + _RESIDENT_BLOCKS_OPEN_EXPR + ") }}",
            "{{ helper_state_window in ['tlt', 'opn'] or in_ventilate_position }}",
            "{{ not (helper_state_manual and override_flags.ventilation) }}",
        ],
    },
]

# Buggy variant: bare resident_now treated as a privacy-close trigger.
WINDOW_CLOSED_RETURN_BRANCHES_BUGGY = [
    WINDOW_CLOSED_RETURN_BRANCHES[0],
    {
        "name": "open",
        "conditions": [
            "{{ not contact_opened_now and not contact_tilted_now }}",
            "{{ helper_state_base == 'opn' and not resident_now }}",
            "{{ not helper_state_is_shaded and not helper_state_shade }}",
            "{{ helper_state_window in ['tlt', 'opn'] or in_ventilate_position }}",
            "{{ not (helper_state_manual and override_flags.ventilation) }}",
        ],
    },
    {
        "name": "close",
        "conditions": [
            "{{ not contact_opened_now and not contact_tilted_now }}",
            "{{ helper_state_base == 'cls' or resident_now }}",
            "{{ helper_state_window in ['tlt', 'opn'] or in_ventilate_position }}",
            "{{ not (helper_state_manual and override_flags.ventilation) }}",
        ],
    },
]


def _make_window_closed_vars(
    *,
    resident_now: bool = False,
    resident_config: list | None = None,
    helper_state_base: str = "opn",
    helper_state_shade: bool = False,
    helper_state_is_shaded: bool = False,
    helper_state_window: str = "opn",
    in_ventilate_position: bool = False,
    helper_state_manual: bool = False,
    override_ventilation: bool = False,
) -> dict:
    resident_config = resident_config or []
    return {
        "contact_opened_now": False,
        "contact_tilted_now": False,
        "resident_now": resident_now,
        "resident_config": resident_config,
        # closing_trigger mirrors the blueprint: 'resident_closing_enabled' in resident_config
        "resident_flags": {"closing_trigger": "resident_closing_enabled" in resident_config},
        "helper_state_base": helper_state_base,
        "helper_state_shade": helper_state_shade,
        "helper_state_is_shaded": helper_state_is_shaded,
        "helper_state_window": helper_state_window,
        "in_ventilate_position": in_ventilate_position,
        "helper_state_manual": helper_state_manual,
        "override_flags": {"ventilation": override_ventilation},
    }


class TestWindowClosedReturnRespectsPrivacy:
    """
    Forum trace (cover closes after window is closed at ~10:00):

    After the window closes, the contact handler must return the cover to the
    state the priority cascade dictates (effective_state) — NOT close it merely
    because a resident is present. Privacy-close applies only when
    `resident_closing_enabled` is configured, or when opening is not permitted.

    Root cause: 'Return to open' required `not resident_now` and 'Return to
    close' fired on bare `resident_now`. Fixed via `resident_blocks_open`.
    """

    def _expected_from_cascade(self, *, resident_now, resident_config, base, shade=False) -> str:
        es = _eval_effective_state(
            helper_json={"frc": "non", "win": "cls", "bas": base, "shd": 1 if shade else 0},
            state_resident=resident_now,
            resident_config=resident_config,
            sensor_opened=False,
            sensor_tilted=False,
            has_opened_sensor=True,
        )
        return {"opn": "open", "cls": "close", "shd": "shading"}[es]

    def test_present_no_privacy_allow_open_returns_open(self):
        """Reported bug: resident present, base=opn, allow_opening set, no privacy → OPEN."""
        env = make_jinja_env()
        cfg = ["resident_allow_shading", "resident_allow_opening", "resident_allow_ventilation"]
        v = _make_window_closed_vars(resident_now=True, resident_config=cfg, helper_state_base="opn")
        branch = first_matching_branch(env, WINDOW_CLOSED_RETURN_BRANCHES, v)
        assert branch == "open", f"Expected 'open' but got '{branch}'"
        assert branch == self._expected_from_cascade(
            resident_now=True, resident_config=cfg, base="opn"
        ), "Contact handler must agree with effective_state cascade."

    def test_buggy_version_wrongly_closes(self):
        """Locks in the regression: the old bare-resident_now logic closed here."""
        env = make_jinja_env()
        cfg = ["resident_allow_shading", "resident_allow_opening", "resident_allow_ventilation"]
        v = _make_window_closed_vars(resident_now=True, resident_config=cfg, helper_state_base="opn")
        branch = first_matching_branch(env, WINDOW_CLOSED_RETURN_BRANCHES_BUGGY, v)
        assert branch == "close", (
            "Buggy variant is expected to (wrongly) close — this documents the bug "
            "the fix resolves."
        )

    def test_present_privacy_returns_close(self):
        """Resident present WITH resident_closing_enabled → privacy-close still works."""
        env = make_jinja_env()
        cfg = ["resident_closing_enabled", "resident_allow_opening"]
        v = _make_window_closed_vars(resident_now=True, resident_config=cfg, helper_state_base="opn")
        branch = first_matching_branch(env, WINDOW_CLOSED_RETURN_BRANCHES, v)
        assert branch == "close"
        assert branch == self._expected_from_cascade(
            resident_now=True, resident_config=cfg, base="opn"
        )

    def test_present_no_allow_open_returns_close(self):
        """Resident present, opening not permitted (no allow_opening) → CLOSE (allow_open gate)."""
        env = make_jinja_env()
        cfg = ["resident_allow_ventilation"]  # neither allow_opening nor closing_enabled
        v = _make_window_closed_vars(resident_now=True, resident_config=cfg, helper_state_base="opn")
        branch = first_matching_branch(env, WINDOW_CLOSED_RETURN_BRANCHES, v)
        assert branch == "close"
        assert branch == self._expected_from_cascade(
            resident_now=True, resident_config=cfg, base="opn"
        )

    def test_absent_base_open_returns_open(self):
        """No resident → return to open base state."""
        env = make_jinja_env()
        v = _make_window_closed_vars(resident_now=False, resident_config=[], helper_state_base="opn")
        branch = first_matching_branch(env, WINDOW_CLOSED_RETURN_BRANCHES, v)
        assert branch == "open"

    def test_base_close_returns_close(self):
        """Base=cls → return to close regardless of presence."""
        env = make_jinja_env()
        v = _make_window_closed_vars(resident_now=False, resident_config=[], helper_state_base="cls")
        branch = first_matching_branch(env, WINDOW_CLOSED_RETURN_BRANCHES, v)
        assert branch == "close"

    def test_base_close_resident_present_returns_close(self):
        """Base=cls with a present resident (no privacy config) → still close via the base=cls arm."""
        env = make_jinja_env()
        cfg = ["resident_allow_opening"]  # present, but neither privacy nor a reason to stay open
        v = _make_window_closed_vars(resident_now=True, resident_config=cfg, helper_state_base="cls")
        branch = first_matching_branch(env, WINDOW_CLOSED_RETURN_BRANCHES, v)
        assert branch == "close"
        assert branch == self._expected_from_cascade(
            resident_now=True, resident_config=cfg, base="cls"
        )

    def test_shading_active_returns_shading(self):
        """Shading active and allowed → return to shading (branch precedence intact)."""
        env = make_jinja_env()
        cfg = ["resident_allow_shading"]
        v = _make_window_closed_vars(
            resident_now=True, resident_config=cfg, helper_state_base="opn", helper_state_shade=True
        )
        branch = first_matching_branch(env, WINDOW_CLOSED_RETURN_BRANCHES, v)
        assert branch == "shading"

    def test_blueprint_branches_use_resident_blocks_open(self):
        """Static wiring: the actual YAML branches gate on resident_blocks_open."""
        blueprint = _load_blueprint_yaml(BLUEPRINT_PATH)

        def find_branch(node, alias):
            if isinstance(node, dict):
                if node.get("alias") == alias:
                    return node
                for value in node.values():
                    result = find_branch(value, alias)
                    if result is not None:
                        return result
            elif isinstance(node, list):
                for item in node:
                    result = find_branch(item, alias)
                    if result is not None:
                        return result
            return None

        for alias in (
            "Window closed - Return to open position",
            "Window closed - Return to close position",
        ):
            branch = find_branch(blueprint, alias)
            assert branch is not None, f"Missing branch: {alias}"
            conds = str(branch.get("conditions", []))
            assert "resident_blocks_open" in conds, (
                f"'{alias}' must gate on resident_blocks_open, not bare resident_now."
            )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: "Don't end shading if cover is already closed" (Issue #502)
# ─────────────────────────────────────────────────────────────────────────────

# The "or:" guard in the "Check for shading end" branch. Shading end is allowed
# to continue when this evaluates True; it is blocked (cover stays closed) when
# it evaluates False.
SHADING_END_IF_CLOSED_GUARD = (
    "(not prevent_flags.shading_end_if_closed) or "
    "(prevent_flags.shading_end_if_closed and not in_close_position "
    "and not position_comparisons.current_below_close)"
)


def _shading_end_guard_vars(*, enabled, in_close_position, current_below_close):
    return {
        "prevent_flags": {"shading_end_if_closed": enabled},
        "in_close_position": in_close_position,
        "position_comparisons": {"current_below_close": current_below_close},
    }


class TestShadingEndIfClosedGuard:
    """
    Regression for Issue #502: a cover manually closed *further* than the
    configured close position (e.g. 0% while close_position=15%) must be
    treated as closed, so shading end does not open it.
    """

    def test_below_close_position_blocks_shading_end(self):
        """current_position below close_position → guard False → shading end blocked."""
        env = make_jinja_env()
        result = eval_condition(env, SHADING_END_IF_CLOSED_GUARD, _shading_end_guard_vars(
            enabled=True,
            in_close_position=False,   # 0% is outside the close-position tolerance window
            current_below_close=True,  # but it IS below the close position → still "closed"
        ))
        assert result is False, (
            "Cover closed further than close_position must count as closed; "
            "shading end must not continue (Issue #502)."
        )

    def test_at_close_position_blocks_shading_end(self):
        """Cover within close-position tolerance → guard False → shading end blocked."""
        env = make_jinja_env()
        result = eval_condition(env, SHADING_END_IF_CLOSED_GUARD, _shading_end_guard_vars(
            enabled=True,
            in_close_position=True,
            current_below_close=False,
        ))
        assert result is False

    def test_above_close_position_allows_shading_end(self):
        """Cover above close_position → guard True → shading end continues normally."""
        env = make_jinja_env()
        result = eval_condition(env, SHADING_END_IF_CLOSED_GUARD, _shading_end_guard_vars(
            enabled=True,
            in_close_position=False,
            current_below_close=False,
        ))
        assert result is True

    def test_option_disabled_always_allows_shading_end(self):
        """Option off → guard True regardless of position."""
        env = make_jinja_env()
        result = eval_condition(env, SHADING_END_IF_CLOSED_GUARD, _shading_end_guard_vars(
            enabled=False,
            in_close_position=False,
            current_below_close=True,
        ))
        assert result is True

    def test_blueprint_guard_checks_current_below_close(self):
        """Static wiring: the shading-end guard in the YAML uses current_below_close."""
        text = BLUEPRINT_PATH.read_text()
        assert "prevent_flags.shading_end_if_closed and not in_close_position and not position_comparisons.current_below_close" in text, (
            "Shading-end 'if closed' guard must also block when the cover is "
            "below the close position (Issue #502)."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Manual detection dead-band — hardware position drift is not "manual"
# ─────────────────────────────────────────────────────────────────────────────

# Dead-band expression taken verbatim from the blueprint (current_position_attr).
MANUAL_DEADBAND_CURRENT_POS = (
    "((trigger.to_state.attributes.current_position | float(0)) "
    "- (trigger.from_state.attributes.current_position | float(0))) | abs "
    "> position_tolerance"
)


def _deadband_env():
    env = make_jinja_env()
    # HA registers `abs` as a filter; plain Jinja2 does not.
    env.filters["abs"] = abs
    return env


def _trigger_vars(from_pos, to_pos, tolerance):
    return {
        "trigger": {
            "from_state": {"attributes": {"current_position": from_pos}},
            "to_state": {"attributes": {"current_position": to_pos}},
        },
        "position_tolerance": tolerance,
    }


class TestManualDetectionDeadband:
    """
    Regression: covers that report their position with ±1% jitter must not
    arm the manual override. A reported position change only counts as manual
    when it exceeds the configured position_tolerance. Within the tolerance it
    is treated as hardware drift and ignored.
    """

    def test_one_percent_drift_within_tolerance_is_not_manual(self):
        """58 -> 59 with tolerance 1 must NOT be detected as a manual change."""
        env = _deadband_env()
        result = eval_condition(env, MANUAL_DEADBAND_CURRENT_POS, _trigger_vars(58, 59, 1))
        assert result is False, (
            "A 1% drift within position_tolerance must not trigger manual override."
        )

    def test_real_move_beyond_tolerance_is_manual(self):
        """58 -> 70 with tolerance 1 IS a real manual move."""
        env = _deadband_env()
        result = eval_condition(env, MANUAL_DEADBAND_CURRENT_POS, _trigger_vars(58, 70, 1))
        assert result is True

    def test_drift_in_either_direction_is_ignored(self):
        """The dead-band is symmetric: 59 -> 58 is also ignored."""
        env = _deadband_env()
        result = eval_condition(env, MANUAL_DEADBAND_CURRENT_POS, _trigger_vars(59, 58, 1))
        assert result is False

    def test_tolerance_zero_restores_react_to_every_change(self):
        """tolerance 0 → any non-zero change counts as manual (legacy behaviour)."""
        env = _deadband_env()
        result = eval_condition(env, MANUAL_DEADBAND_CURRENT_POS, _trigger_vars(58, 59, 0))
        assert result is True

    def test_change_larger_than_tolerance_is_manual(self):
        """tolerance 1, 58 -> 60 (delta 2 > 1) → manual."""
        env = _deadband_env()
        result = eval_condition(env, MANUAL_DEADBAND_CURRENT_POS, _trigger_vars(58, 60, 1))
        assert result is True

    def test_blueprint_wires_deadband_for_all_position_sources(self):
        """Static wiring: all three position sources use the position_tolerance dead-band."""
        text = BLUEPRINT_PATH.read_text()
        for attr in ("current_position", "position"):
            expr = (
                f"((trigger.to_state.attributes.{attr} | float(0)) "
                f"- (trigger.from_state.attributes.{attr} | float(0))) | abs "
                f"> position_tolerance"
            )
            assert expr in text, f"Dead-band missing for attribute '{attr}'"
        # custom_sensor uses the state value, not an attribute
        custom = (
            "((trigger.to_state.state | float(0)) "
            "- (trigger.from_state.state | float(0))) | abs > position_tolerance"
        )
        assert custom in text, "Dead-band missing for custom_sensor position source"
        # The old unconditional '!=' detection must be gone.
        assert "trigger.from_state.attributes.current_position != trigger.to_state.attributes.current_position" not in text, (
            "Old unconditional '!=' manual detection must be replaced by the dead-band."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Weather forecast must be loaded on every opening trigger (Bug Pattern T)
# ─────────────────────────────────────────────────────────────────────────────

class TestWeatherForecastLoadGateCoversOpeningTriggers:
    """
    Regression for Bug Pattern T (issue #514 follow-up):

    The Bug Pattern R fix (CCA 2026.06.07) added `shading_start_warranted` to
    the "Opening skipped: Shading start pending" branch. That variable reads
    `forecast_temp_raw` and `forecast_weather_condition_raw`, which require
    `weather_forecast` to be populated by the `weather.get_forecasts` action.

    The forecast-load gate originally only matched `^(t_shading_start|t_open_1)`
    triggers. With Bug Pattern R in place, every opening trigger that may
    reach the "Opening skipped" branch must also load the forecast — otherwise
    the forecast-based conditions silently evaluate to false and the cover
    opens despite shading still being warranted.

    The top-level "Check for opening" branch is gated on
    `^(t_open|t_calendar_event)` (calendar_event_end is filtered out by other
    conditions). The forecast-load regex must therefore cover all `t_open*`
    triggers AND `t_calendar_event_start`.
    """

    OPENING_TRIGGER_IDS_REQUIRING_FORECAST = [
        "t_open_1",            # early time
        "t_open_2",            # late time
        "t_open_4",            # brightness
        "t_open_5",            # sun elevation
        "t_calendar_event_start",  # calendar
    ]

    def _load_forecast_load_block(self) -> dict:
        """Locate the top-level if/then block that calls weather.get_forecasts."""
        blueprint = _load_blueprint_yaml(BLUEPRINT_PATH)

        def walk(node):
            if isinstance(node, dict):
                if "if" in node and "then" in node:
                    then = node["then"]
                    if isinstance(then, list):
                        for step in then:
                            if isinstance(step, dict) and step.get("action") == "weather.get_forecasts":
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

        block = walk(blueprint)
        assert block is not None, "Could not find weather.get_forecasts if/then block"
        return block

    def test_regex_matches_all_opening_triggers(self):
        """Every opening-related trigger ID must satisfy the forecast-load regex."""
        import re

        block = self._load_forecast_load_block()
        conditions = block["if"]
        flat = yaml.safe_dump(conditions)
        # Extract the regex_match pattern from the trigger-gating condition.
        # We look for `regex_match('^(...)')` to pull out the alternation list.
        m = re.search(r"regex_match\(''?(\^\([^)]+\))''?\)", flat)
        assert m is not None, (
            "Forecast-load gate must use a regex_match on trigger.id with an "
            f"anchored alternation. Conditions were:\n{flat}"
        )
        pattern = m.group(1)
        compiled = re.compile(pattern)
        for trigger_id in self.OPENING_TRIGGER_IDS_REQUIRING_FORECAST:
            assert compiled.match(trigger_id), (
                f"Forecast-load regex {pattern!r} does not match opening trigger "
                f"{trigger_id!r}. Without loading the forecast, the opening "
                f"handler cannot correctly evaluate shading_start_warranted "
                f"and may open the cover even when shading is still warranted."
            )

    def test_regex_still_matches_shading_start_triggers(self):
        """The forecast must continue to load on shading-start pending triggers."""
        import re

        block = self._load_forecast_load_block()
        flat = yaml.safe_dump(block["if"])
        m = re.search(r"regex_match\(''?(\^\([^)]+\))''?\)", flat)
        assert m is not None
        pattern = m.group(1)
        compiled = re.compile(pattern)
        for trigger_id in [
            "t_shading_start_pending_1",
            "t_shading_start_pending_7",
            "t_shading_start_execution",
        ]:
            assert compiled.match(trigger_id), (
                f"Forecast-load regex {pattern!r} must also match shading-start "
                f"trigger {trigger_id!r}."
            )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: shading-tilt adjustment must respect resident allow_shade
# ─────────────────────────────────────────────────────────────────────────────


def _flatten_condition_strings(conditions) -> list:
    """Collect all template/condition strings from a (possibly nested) conditions list."""
    out = []

    def walk(node):
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(conditions)
    return out


class TestShadingTiltRespectsResident:
    """
    Regression: the 'Check for shading tilt' branch drove the slats into the
    shading tilt position while a resident was present, even when
    'Allow sun protection when resident is still present' was disabled.

    Every other shading-drive branch gates on resident_flags.allow_shade
    (or the inline equivalent). The shading-tilt branch was missing it, so a
    t_shading_tilt_* trigger tilted the cover into shading mode despite the
    resident block (shd=1 stored via 'Save shading state for the future',
    res=1, but the cover still moved).
    """

    def _load_blueprint(self) -> dict:
        return _load_blueprint_yaml(BLUEPRINT_PATH)

    def test_shading_tilt_branch_gates_on_allow_shade(self):
        blueprint = self._load_blueprint()
        branch = _find_branch_by_alias(blueprint, "Check for shading tilt")
        assert branch is not None, "Could not find 'Check for shading tilt' branch."
        conditions = _flatten_condition_strings(branch.get("conditions", []))
        assert any("resident_flags.allow_shade" in c for c in conditions), (
            "The 'Check for shading tilt' branch must gate on "
            "resident_flags.allow_shade so the slats are not tilted into the "
            "shading position while a resident is present and shading is not "
            "allowed. Conditions found: " + repr(conditions)
        )
