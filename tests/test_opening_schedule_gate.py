"""is_opening_scheduled - the gate that lets BASE=OPN beat the VENT floor.

The flag answers exactly one question: "is bas == 'opn' a real open intent, or is it
just the init default that nothing ever moves?" (Issue #553, Bug Pattern Z). bas is
driven to 'opn' by the opening handler (t_open_* / t_calendar_event_start triggers)
and by the resident-leaving handler (t_resident_update with resident opening
configured, Issue #616) - so the flag must be true iff at least one of those sources
is enabled. Time control is only two of the five sources: brightness and sun
elevation open the cover with time control switched off (Bug Pattern AL), and a
resident opening needs no other source at all.

The tests therefore render the real flag out of the blueprint and compare it against the
real `enabled:` templates of the real opening triggers - a new opening source that forgets
to update the flag fails here.
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


def _load_blueprint() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    # An unconfigured !input is [] in HA; a configured one is set per test config below.
    _Loader.add_constructor("!input", lambda loader, node: [])
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


BP = _load_blueprint()
TRIGGER_VARS = BP["trigger_variables"]

# The trigger_variables the flag is built from, in blueprint order.
DERIVED = [
    "is_calendar_enabled",
    "is_up_enabled",
    "is_brightness_enabled",
    "is_sun_elevation_enabled",
    "is_time_field_enabled",
    "is_time_control_disabled",
    "is_opening_scheduled",
]

# Every trigger that can drive bas to 'opn' (i.e. that the opening branch dispatches on).
OPENING_TRIGGER_IDS = ["t_open_1", "t_open_2", "t_open_4", "t_open_5", "t_calendar_event_start"]

env = jinja2.Environment(undefined=jinja2.StrictUndefined)


def _render_bool(template: str, variables: dict) -> bool:
    """Render and parse like HA does - a bare 'false' string would be TRUTHY."""
    out = env.from_string(template).render(**variables).strip()
    if out == "True":
        return True
    if out == "False":
        return False
    return bool(out)


def _config(auto_options, time_control="time_control_input", calendar_entity=None,
            brightness_sensor=None, sun_sensor="sun.sun", resident_sensor=None,
            resident_config=None) -> dict:
    """A user config, as the !input values reach trigger_variables ([] = not configured)."""
    return {
        "auto_options": auto_options,
        "time_control": time_control,
        "calendar_entity": calendar_entity if calendar_entity is not None else [],
        "default_brightness_sensor": brightness_sensor if brightness_sensor is not None else [],
        "default_sun_sensor": sun_sensor if sun_sensor is not None else [],
        "resident_sensor": resident_sensor if resident_sensor is not None else [],
        "resident_config": resident_config if resident_config is not None else [],
    }


def _trigger_vars(config: dict) -> dict:
    """Render the derived trigger_variables in blueprint order, feeding each into the next."""
    variables = dict(config)
    for key in DERIVED:
        variables[key] = _render_bool(TRIGGER_VARS[key], variables)
    return variables


def _opening_triggers_enabled(config: dict) -> bool:
    """True when at least one real opening trigger is enabled for this config."""
    variables = _trigger_vars(config)
    for trigger in BP["triggers"]:
        if trigger.get("id") in OPENING_TRIGGER_IDS:
            if _render_bool(trigger["enabled"], variables):
                return True
    return False


def _resident_opening_exists(config: dict) -> bool:
    """True when the resident-leaving handler can open the cover: its trigger can fire
    (t_resident_update enabled, a sensor actually configured) and resident opening is on."""
    variables = _trigger_vars(config)
    for trigger in BP["triggers"]:
        if trigger.get("id") == "t_resident_update":
            return (
                _render_bool(trigger["enabled"], variables)
                and config["resident_sensor"] != []
                and "resident_opening_enabled" in config["resident_config"]
            )
    return False


class TestFlagMirrorsTheOpeningTriggers:
    """is_opening_scheduled == is_up_enabled and (any opening trigger enabled)."""

    CONFIGS = {
        "time schedule": _config(["auto_up_enabled", "time_control_enabled"]),
        "calendar": _config(
            ["auto_up_enabled", "time_control_enabled"],
            time_control="time_control_calendar",
            calendar_entity="calendar.covers",
        ),
        "sun only, no time control": _config(["auto_up_enabled", "auto_sun_enabled"]),
        "brightness only, no time control": _config(
            ["auto_up_enabled", "auto_brightness_enabled"],
            brightness_sensor="sensor.brightness",
        ),
        "sun + time control": _config(
            ["auto_up_enabled", "auto_sun_enabled", "time_control_enabled"]
        ),
        # Issue #553: shading-only, no opening automation at all -> bas stays at its init default
        "shading only": _config(["auto_shading_enabled", "auto_ventilate_enabled"]),
        # auto_up checked but every source switched off -> no opening trigger exists either
        "opening enabled without any source": _config(["auto_up_enabled"], time_control=[]),
        # source checked but its sensor is missing -> the trigger is disabled
        "sun enabled without a sun sensor": _config(
            ["auto_up_enabled", "auto_sun_enabled"], sun_sensor=[]
        ),
        "brightness enabled without a sensor": _config(
            ["auto_up_enabled", "auto_brightness_enabled"]
        ),
        # opening automation off, but the sources are on (they only close then)
        "closing only, sun": _config(["auto_down_enabled", "auto_sun_enabled"]),
        # Issue #616: the resident-leaving handler opens (and writes bas='opn') with no
        # time/brightness/sun source at all - a real opening automation
        "resident opening only": _config(
            ["auto_up_enabled"], time_control=[],
            resident_sensor="binary_sensor.res",
            resident_config=["resident_opening_enabled", "resident_closing_enabled"],
        ),
        # the sensor alone opens nothing - resident_opening_enabled is the gate
        "resident sensor without resident opening": _config(
            ["auto_up_enabled"], time_control=[],
            resident_sensor="binary_sensor.res",
            resident_config=["resident_closing_enabled"],
        ),
        # the option without its sensor enables no trigger
        "resident opening without a sensor": _config(
            ["auto_up_enabled"], time_control=[],
            resident_config=["resident_opening_enabled"],
        ),
        # the leave chain requires auto_up_enabled - without it nothing opens
        "resident opening without auto_up": _config(
            ["auto_down_enabled"], time_control=[],
            resident_sensor="binary_sensor.res",
            resident_config=["resident_opening_enabled"],
        ),
    }

    @pytest.mark.parametrize("name", list(CONFIGS))
    def test_flag_is_true_exactly_when_an_opening_trigger_can_fire(self, name):
        config = self.CONFIGS[name]
        variables = _trigger_vars(config)
        expected = variables["is_up_enabled"] and (
            _opening_triggers_enabled(config) or _resident_opening_exists(config)
        )
        assert variables["is_opening_scheduled"] is expected, name


class TestVentFloorAgainstTheRealCascade:
    """End-to-end: the real effective_state, driven by the real flag."""

    def _effective_state(self, config: dict, helper: dict, tilted: bool,
                         present: bool = False) -> str:
        variables = _trigger_vars(config)
        entity_states = {"binary_sensor.tilted": "on" if tilted else "off"}
        cascade_env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        cascade_env.globals["states"] = lambda entity_id: entity_states.get(entity_id, "unknown")
        variables.update(
            helper_json=helper,
            state_resident=present,
            contact_window_opened=[],
            contact_window_tilted="binary_sensor.tilted",
            # Every config in this class carries auto_ventilate_enabled; the
            # vent-disabled scoping has its own tests in test_restart_recovery.
            is_ventilation_enabled=True,
        )
        return cascade_env.from_string(BP["variables"]["effective_state"]).render(**variables).strip()

    OPEN_BASE = {"bas": "opn", "shd": 0, "frc": "non", "win": "tlt"}

    def test_sun_driven_opening_beats_the_vent_floor(self):
        """Bug Pattern AL: the sun opening drove bas to 'opn' - that is a real open intent,
        so a tilted window must not pull the cover back down to the ventilation position."""
        config = _config(["auto_up_enabled", "auto_sun_enabled", "auto_ventilate_enabled"])
        assert self._effective_state(config, self.OPEN_BASE, tilted=True) == "opn"

    def test_brightness_driven_opening_beats_the_vent_floor(self):
        config = _config(
            ["auto_up_enabled", "auto_brightness_enabled", "auto_ventilate_enabled"],
            brightness_sensor="sensor.brightness",
        )
        assert self._effective_state(config, self.OPEN_BASE, tilted=True) == "opn"

    def test_time_driven_opening_beats_the_vent_floor(self):
        config = _config(
            ["auto_up_enabled", "time_control_enabled", "auto_ventilate_enabled"]
        )
        assert self._effective_state(config, self.OPEN_BASE, tilted=True) == "opn"

    def test_shading_only_setup_still_ventilates(self):
        """Issue #553 stays fixed: with no opening automation, bas='opn' is the init
        default and the VENT floor must apply."""
        config = _config(["auto_shading_enabled", "auto_ventilate_enabled"])
        assert self._effective_state(config, self.OPEN_BASE, tilted=True) == "vnt"

    def test_opening_enabled_without_any_source_still_ventilates(self):
        """Same as #553: the checkbox alone drives nothing, so bas='opn' is still the default."""
        config = _config(["auto_up_enabled", "auto_ventilate_enabled"], time_control=[])
        assert self._effective_state(config, self.OPEN_BASE, tilted=True) == "vnt"

    def test_closed_base_still_ventilates_with_a_sun_schedule(self):
        """The gate only lifts the floor for bas='opn' - a closed base keeps the vent floor."""
        config = _config(["auto_up_enabled", "auto_sun_enabled", "auto_ventilate_enabled"])
        helper = {"bas": "cls", "shd": 0, "frc": "non", "win": "tlt"}
        assert self._effective_state(config, helper, tilted=True) == "vnt"

    # The issue #616 setup: resident mode does the opening/closing, ventilation
    # doubles as evening privacy while the resident is present.
    RESIDENT_CONFIG = _config(
        ["auto_up_enabled", "auto_down_enabled", "auto_ventilate_enabled"],
        time_control=[],
        resident_sensor="binary_sensor.res",
        resident_config=[
            "resident_opening_enabled",
            "resident_closing_enabled",
            "resident_allow_ventilation",
        ],
    )

    def test_resident_driven_opening_beats_the_vent_floor_when_absent(self):
        """Issue #616: resident opening/closing is the whole schedule. When the resident
        leaves, a tilted window must not hold the cover at the ventilation position -
        the resident opening is a real open intent."""
        assert self._effective_state(self.RESIDENT_CONFIG, self.OPEN_BASE, tilted=True) == "opn"

    def test_resident_present_keeps_the_vent_floor_for_privacy(self):
        """Same setup, resident present: privacy-closing is active, so the tilted
        window still means the ventilation floor (the evening privacy use case)."""
        assert self._effective_state(
            self.RESIDENT_CONFIG, self.OPEN_BASE, tilted=True, present=True
        ) == "vnt"

    def test_resident_closing_only_still_ventilates(self):
        """Without resident opening the resident sensor opens nothing - bas='opn' is
        still the init default and the vent floor must apply (#553 semantics)."""
        config = _config(
            ["auto_up_enabled", "auto_down_enabled", "auto_ventilate_enabled"],
            time_control=[],
            resident_sensor="binary_sensor.res",
            resident_config=["resident_closing_enabled"],
        )
        assert self._effective_state(config, self.OPEN_BASE, tilted=True) == "vnt"
