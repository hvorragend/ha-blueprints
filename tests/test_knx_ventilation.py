"""Execute the blueprint's KNX actions against an offline, deterministic HA model.

Only the action subset exercised here is interpreted. Unsupported actions fail
loudly; services are recorded locally and never sent to Home Assistant. Native
template conversion deliberately uses literal_eval, not JSON boolean coercion.
"""

import ast
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from types import SimpleNamespace

from jinja2 import Environment, StrictUndefined
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


class Input(str):
    """Keep blueprint input references distinct from literal strings."""


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor("!input", lambda loader, node: Input(loader.construct_scalar(node)))
CCA = yaml.load(
    (ROOT / "blueprints/automation/cover_control_automation.yaml").read_text(encoding="utf-8"),
    Loader=Loader,
)


def find_alias(value, name):
    if isinstance(value, dict):
        if value.get("alias") == name:
            return value
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return None
    for item in children:
        found = find_alias(item, name)
        if found is not None:
            return found
    return None


PRE = find_alias(
    CCA["actions"],
    "KNX ventilation: persist cycle, validate feedback and re-arm nonblocking settle timer",
)
RESUME = find_alias(
    CCA["actions"],
    "KNX ventilation: resume current automatic target after native restoration settles",
)
assert PRE is not None, "KNX ventilation bookkeeping action missing from blueprint"
assert RESUME is not None, "KNX ventilation resume action missing from blueprint"
OPEN = find_alias(CCA["actions"], "Normal opening of the cover")
MANUAL = find_alias(CCA["actions"], "Checking for manual position changes")
ALIASES = CCA["actions"][0]["variables"]
MANUAL_GUARD = next(
    item for item in MANUAL["conditions"]
    if isinstance(item, dict) and "h.k" in item.get("value_template", "")
)
TIMER = next(trigger for trigger in CCA["triggers"] if trigger.get("id") == "t_knx_settle")
TARGETS = next(
    action["variables"]["state_targets"] for action in CCA["actions"]
    if "state_targets" in action.get("variables", {})
)


def dt(value):
    return datetime.fromtimestamp(value, timezone.utc)


class State:
    def __init__(self, entity_id, value, timestamp, attributes=None):
        self.entity_id = entity_id
        self.state = str(value)
        self.last_updated = dt(timestamp)
        self.last_changed = dt(timestamp)
        self.attributes = attributes or {}


class StateAccess:
    def __init__(self, world):
        self.world = world

    def __call__(self, entity_id):
        state = self.world.entities.get(entity_id) if isinstance(entity_id, str) else None
        return state.state if state is not None else "unknown"

    def __getitem__(self, entity_id):
        return self.world.entities.get(entity_id)


class Stop(Exception):
    """An HA condition or stop action terminates the current sequence."""


class World:
    def __init__(self, enabled=True, base="cls", manual=0, shade=0):
        self.time = self.start = 1700000000.0
        self.commands = []
        self.tilt_commands = []
        self.helper_writes = []
        self.errors = []
        self.deadline = None
        self.enabled = enabled
        self.input_conditions = {}
        self.variable_overrides = {}
        self.input_values = {}
        self.delay_hook = None
        self.entities = {
            "cover.test": State("cover.test", "closed", self.time - 1000, {"current_position": 0}),
            "binary_sensor.window": State("binary_sensor.window", "off", self.time - 1000),
            "binary_sensor.tilt": State("binary_sensor.tilt", "off", self.time - 1000),
            "input_boolean.pause": State("input_boolean.pause", "off", self.time - 1000),
        }
        self.helper_id = "input_text.test"
        self.initial_helper = dict(
            bas=base, shd=shade, pnd="non", win="cls", frc="non", res=0, man=manual,
            ts=dict.fromkeys(["opn", "cls", "shd", "due", "arm", "man"], 0),
            v=6, t=int(self.time - 1000), d=0,
        )
        self.set_helper(self.initial_helper, self.time - 1000)
        self.states = StateAccess(self)
        self.env = Environment(undefined=StrictUndefined)
        self.env.filters.update(
            from_json=self.from_json,
            to_json=lambda value: json.dumps(value, separators=(",", ":"), ensure_ascii=False),
            regex_match=lambda value, pattern: re.match(pattern, str(value)) is not None,
            regex_search=lambda value, pattern: re.search(pattern, str(value)) is not None,
        )
        self.env.globals.update(
            states=self.states,
            state_attr=lambda entity, name: self.entities[entity].attributes.get(name)
            if isinstance(entity, str) and entity in self.entities else None,
            is_state=lambda entity, value: self.states(entity) == value,
            as_timestamp=lambda value, default=0: value.timestamp()
            if isinstance(value, datetime) else default,
            is_number=self.is_number,
            now=lambda: dt(self.time),
            dict=dict,
        )

    @staticmethod
    def is_number(value):
        try:
            return value is not None and float("-inf") < float(value) < float("inf")
        except (ValueError, TypeError):
            return False

    @staticmethod
    def from_json(value, default=None):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default

    def set_helper(self, helper, timestamp=None):
        self.entities[self.helper_id] = State(
            self.helper_id, json.dumps(helper, separators=(",", ":")),
            self.time if timestamp is None else timestamp, {"max": 255},
        )

    def render(self, value, variables):
        if isinstance(value, Input):
            if value in self.input_values:
                return copy.deepcopy(self.input_values[value])
            if value == "cover_status_helper":
                return self.helper_id
            if value.startswith("auto_") and ("action" in value or "condition" in value):
                return []
            raise AssertionError(f"Unsupported input {value}")
        if isinstance(value, dict):
            return {key: self.render(item, variables) for key, item in value.items()}
        if isinstance(value, list):
            return [self.render(item, variables) for item in value]
        if not isinstance(value, str) or not ("{{" in value or "{%" in value):
            return value
        result = self.env.from_string(value).render(**variables).strip()
        try:
            return ast.literal_eval(result)
        except (ValueError, SyntaxError):
            return result

    @property
    def helper(self):
        return json.loads(self.states(self.helper_id))

    @property
    def positions(self):
        return [position for _, position in self.commands]

    def context(self, trigger=None):
        h = self.helper
        position = self.entities["cover.test"].attributes.get("current_position", 101)
        values = {
            "is_knx_ventilation": self.enabled,
            "ventilation_knx_controlled": self.enabled,
            "ventilation_knx_restore_delay": 60,
            "contact_window_opened": "binary_sensor.window", "contact_window_tilted": [],
            "blind": "cover.test", "blind_entities": ["cover.test"],
            "cover_status_helper": self.helper_id,
            "position_source": "current_position_attr", "custom_position_sensor": [],
            "invalid_states": CCA["trigger_variables"]["invalid_states"],
            "force_pause": "input_boolean.pause",
            "instance_active": [], "instance_active_on_states": ["on", "true"],
            "helper_json": h, "helper_state_force": h["frc"], "helper_state_base": h["bas"],
            "helper_state_manual": bool(h["man"]), "helper_state_window": h["win"],
            "helper_state_shade": bool(h["shd"]), "helper_state_is_shaded": bool(h["shd"]),
            "helper_ts_drive": h["d"], "drive_time": 90,
            "position_tolerance": 0, "tilt_position_tolerance": 0,
            "open_position": 100, "close_position": 0, "ventilate_position": 100,
            "effective_lockout_position": 100, "open_tilt_position": 0,
            "close_tilt_position": 0, "ventilate_tilt_position": 0,
            "effective_shading_position": 25, "shading_tilt_position": 0,
            "shading_position": 25, "shading_position_alt": 25,
            "shading_position_alt_entity": [], "current_position": position,
            "current_tilt_position": 101, "is_cover_tilt_enabled_and_possible": False,
            "tilt_first": False, "is_tilt_before_position_mode": False,
            "is_tilt_wait_idle_mode": False, "is_cover_tilt_enabled": False,
            "tilt_wait_mode": "delay", "tilt_delay": 0,
            "resident_sensor": [], "resident_config": [], "state_resident": False,
            "resident_flags": {"allow_open": True, "allow_shade": True, "allow_ventilate": True,
                               "closing_trigger": False},
            "is_ventilation_enabled": True, "shading_over_ventilation": False,
            "is_opening_scheduled": True, "is_closing_scheduled": True, "closing_target_owned": True,
            "is_up_enabled": True, "is_down_enabled": True, "is_shading_enabled": True,
            "is_awning": False,
            "auto_up_force": [], "auto_down_force": [],
            "auto_shading_start_force": [], "auto_ventilate_force": [],
            "is_forced_open": False, "is_forced_close": False,
            "is_forced_shade": False, "is_forced_vent": False,
            "force_allows_open": True, "force_allows_close": True,
            "force_allows_shade": True, "force_allows_ventilate": True,
            "drive_delay_standard": 0, "enable_logbook": False, "enable_logbook_cover": False,
            "prevent_flags": {"default_cover_actions": False},
            "base_gates": {"opening": {"override_ok": not h["man"]}},
            "in_shading_position": False, "in_reset_override_position": False,
            "adopt_flags": {"opening": False, "closing": False},
            "in_open_position": position == 100, "in_ventilate_position": False,
            "in_close_position": position == 0,
            "is_opening_phase": False, "is_closing_phase": False,
            "position_comparisons": {"current_above_open": False, "current_below_close": False},
            "state_labels": {"opn": "open", "cls": "closed", "shd": "shade",
                             "lock": "lock", "vnt": "vent"},
            "trigger": trigger or SimpleNamespace(id="t_knx_rearm"),
        }
        values.update(self.variable_overrides)
        for key in ("knx_ventilation_hold", "is_paused", "effective_state"):
            values[key] = self.render(CCA["variables"][key], values)
        values["state_targets"] = self.render(TARGETS, values)
        return values

    def condition(self, item, variables):
        if isinstance(item, Input):
            return self.input_conditions.get(str(item), True)
        if isinstance(item, str):
            return bool(self.render(item, variables))
        if "or" in item:
            return any(self.condition(value, variables) for value in item["or"])
        if "and" in item:
            return all(self.condition(value, variables) for value in item["and"])
        condition = item["condition"]
        if isinstance(condition, Input):
            return self.input_conditions.get(str(condition), True)
        if condition == "template":
            return bool(self.render(item["value_template"], variables))
        raise AssertionError(item)

    def all_conditions(self, items, variables):
        return all(self.condition(item, variables)
                   for item in (items if isinstance(items, list) else [items]))

    def run(self, actions, variables):
        if isinstance(actions, Input):
            actions = self.render(actions, variables)
        for action in actions:
            if "variables" in action:
                for key, value in action["variables"].items():
                    variables[key] = self.render(value, variables)
            elif "if" in action:
                branch = "then" if self.all_conditions(action["if"], variables) else "else"
                self.run(action.get(branch, []), variables)
            elif "choose" in action:
                for choice in action["choose"]:
                    if self.all_conditions(choice["conditions"], variables):
                        self.run(choice["sequence"], variables)
                        break
                else:
                    self.run(action.get("default", []), variables)
            elif "sequence" in action:
                try:
                    self.run(action["sequence"], variables)
                except Stop:
                    pass
            elif "condition" in action:
                if not self.condition(action, variables):
                    raise Stop()
            elif "stop" in action:
                raise Stop()
            elif "delay" in action:
                delay = self.render(action["delay"], variables)
                seconds = delay.get("seconds", 0) if isinstance(delay, dict) else delay
                self.time += seconds
                if self.delay_hook is not None:
                    self.delay_hook(seconds)
            elif "wait_template" in action:
                assert self.render(action["wait_template"], variables), (
                    "Offline model only supports already-satisfied template waits"
                )
                variables["wait"] = SimpleNamespace(completed=True)
            elif "repeat" in action:
                for value in self.render(action["repeat"]["for_each"], variables):
                    variables["repeat"] = SimpleNamespace(item=value)
                    self.run(action["repeat"]["sequence"], variables)
            elif "action" in action:
                self.service(action, variables)
            else:
                raise AssertionError(action)

    def service(self, action, variables):
        name = action["action"]
        if name == "input_text.set_value":
            value = self.render(action["data"], variables)["value"]
            if isinstance(value, dict):
                value = json.dumps(value, separators=(",", ":"))
            old = self.states(self.helper_id)
            self.helper_writes.append(value)
            self.entities[self.helper_id] = State(self.helper_id, value, self.time, {"max": 255})
            assert len(value) <= 255, value
            if old != value and self.enabled:
                self.deadline = self.time + float(self.render(TIMER["for"]["seconds"], variables))
        elif name == "system_log.write":
            self.errors.append(self.render(action["data"], variables))
        elif name == "cover.set_cover_tilt_position":
            position = self.render(action["data"], variables)["tilt_position"]
            self.tilt_commands.append((self.time, position))
            self.entities["cover.test"].attributes["current_tilt_position"] = position
        elif name in ("cover.open_cover", "cover.close_cover", "cover.set_cover_position"):
            position = (100 if name == "cover.open_cover" else 0 if name == "cover.close_cover"
                        else self.render(action["data"], variables)["position"])
            self.commands.append((self.time, position))
            self.entities["cover.test"] = State(
                "cover.test", "open" if position == 100 else "closed",
                self.time, {"current_position": position},
            )
        elif name != "logbook.log":
            raise AssertionError(name)

    def invoke(self, action, trigger=None):
        values = self.context(trigger)
        try:
            self.run([action], values)
        except Stop:
            pass
        return values

    def event(self, entity_id, value, at, attributes=None):
        self.time = self.start + at
        before = copy.deepcopy(self.entities.get(entity_id))
        self.entities[entity_id] = State(entity_id, value, self.time, attributes)
        trigger = SimpleNamespace(
            id="t_knx_contact" if entity_id.startswith("binary_sensor.") else "t_knx_feedback",
            entity_id=entity_id, from_state=before, to_state=copy.deepcopy(self.entities[entity_id]),
        )
        self.invoke(PRE, trigger)
        return trigger

    def release(self, at=None):
        self.time = self.deadline if at is None else self.start + at
        values = self.context(SimpleNamespace(id="t_knx_settle"))
        try:
            self.run([PRE, RESUME], values)
        except Stop:
            pass
        return values

    def begin_cycle(self):
        self.event("binary_sensor.window", "on", 1)
        self.event("cover.test", "open", 10, {"current_position": 100})
        self.time = self.start + 20
        self.invoke(OPEN)
        self.event("binary_sensor.window", "off", 100)

    def restore(self, at=132):
        return self.event("cover.test", "closed", at, {"current_position": 0})


def test_native_template_conversion_does_not_coerce_json_booleans():
    world = World()
    assert world.render("{{ false }}", {}) is False
    assert world.render("{% if true %}false{% endif %}", {}) == "false"
    assert world.from_json('{"enabled":false}') == {"enabled": False}


@pytest.mark.parametrize("options,expected", [
    ([], False), (["shading_over_ventilation"], False),
    (["ventilation_knx_controlled"], True),
    (["ventilation_start_no_delay", "ventilation_knx_controlled"], True),
])
def test_checkbox_binding_is_native_boolean(options, expected):
    binding = CCA["trigger_variables"]["ventilation_knx_controlled"]
    assert not isinstance(binding, Input)
    assert World().render(binding, {"auto_ventilate_options": options}) is expected


@pytest.mark.parametrize("checked,ventilation_enabled,expected", [
    (False, False, False), (False, True, False),
    (True, False, False), (True, True, True),
])
def test_feature_activation_requires_enabled_ventilation_and_checkbox(
    checked, ventilation_enabled, expected,
):
    world = World()
    values = world.context()
    values.update(
        ventilation_knx_controlled=checked, is_ventilation_enabled=ventilation_enabled,
    )
    assert world.render(CCA["trigger_variables"]["is_knx_ventilation"], values) is expected


def test_checkbox_and_restore_delay_ui_contract():
    inputs = CCA["blueprint"]["input"]["contacts_section"]["input"]
    assert inputs["auto_ventilate_options"]["default"] == []
    options = inputs["auto_ventilate_options"]["selector"]["select"]
    assert options["multiple"] is True
    assert options["mode"] == "list"
    assert options["options"][-1] == {
        "value": "ventilation_knx_controlled", "label": "💨 Ventilation controlled by KNX",
    }
    keys = list(inputs)
    assert keys.index("ventilation_knx_restore_delay") == keys.index("contact_delay_status") + 1
    delay = inputs["ventilation_knx_restore_delay"]
    assert delay["default"] == 60
    assert delay["name"] == "🕛 Window Close Restore Delay"
    assert delay["selector"]["number"]["mode"] == "slider"
    assert delay["selector"]["number"]["unit_of_measurement"] == (
        inputs["contact_delay_status"]["selector"]["number"]["unit_of_measurement"]
    )


def test_blueprint_templates_compile():
    environment = Environment()
    templates = []

    def visit(value):
        if isinstance(value, str) and ("{{" in value or "{%" in value):
            environment.parse(value)
            templates.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(CCA)
    assert len(templates) > 500


def test_night_open_morning_bookkeeping_native_restore_then_resume():
    world = World(base="cls")
    world.begin_cycle()
    assert world.positions == []
    assert world.helper["bas"] == "opn"
    assert world.helper["ts"]["opn"] == int(world.start + 20)
    assert world.helper["win"] == "knx"
    world.restore()
    assert world.deadline == world.start + 160
    world.release()
    assert world.positions == [100]
    assert world.helper["win"] == "cls"
    assert world.helper["man"] == 0
    assert world.helper["k"] > 0


@pytest.mark.parametrize("trigger_id", ["t_manual_position", "t_manual_tilt"])
def test_late_native_feedback_uses_original_event_timestamp(trigger_id):
    world = World()
    world.begin_cycle()
    restore = world.restore()
    world.release()
    world.time = world.start + 250
    restore.id = trigger_id
    assert world.condition(MANUAL_GUARD, world.context(restore)) is False
    later = SimpleNamespace(
        id=trigger_id, to_state=State("cover.test", "closed", world.helper["k"] + 0.001),
    )
    assert world.condition(MANUAL_GUARD, world.context(later)) is True


def test_close_before_morning_stays_closed():
    world = World()
    world.event("binary_sensor.window", "on", 1)
    world.event("cover.test", "open", 10, {"current_position": 100})
    world.event("binary_sensor.window", "off", 100)
    world.restore()
    world.release()
    assert world.positions == []
    assert world.helper["bas"] == "cls"
    assert world.helper["win"] == "cls"


def test_minimum_settle_applies_even_at_target():
    world = World(base="opn")
    world.begin_cycle()
    assert world.deadline == world.start + 160
    world.release(at=110)
    assert world.helper["win"] == "knx"
    assert world.positions == []
    assert world.deadline == world.start + 160
    world.restore()
    world.release()
    assert world.positions == [100]


def test_late_feedback_extends_quiet_time_but_background_event_does_not():
    world = World()
    world.begin_cycle()
    world.restore(at=157)
    assert world.deadline == world.start + 167
    world.time = world.start + 159
    world.invoke(PRE, SimpleNamespace(id="t_other_background"))
    assert world.deadline == world.start + 167
    world.release()
    assert world.positions == [100]


def test_shading_target_resumes():
    world = World(base="opn", shade=1)
    world.event("binary_sensor.window", "on", 1)
    world.event("cover.test", "open", 10, {"current_position": 100})
    world.event("binary_sensor.window", "off", 100)
    world.restore()
    world.release()
    assert world.positions == [25]


def test_reopen_cancels_old_release():
    world = World(base="opn")
    world.begin_cycle()
    world.event("binary_sensor.window", "on", 155)
    world.release(at=160)
    assert world.helper["win"] == "knx"
    assert world.positions == []
    world.event("binary_sensor.window", "off", 165)
    world.restore(at=197)
    assert world.deadline == world.start + 225
    world.release()
    assert world.positions == [100]


@pytest.mark.parametrize("entity,value,attributes", [
    ("binary_sensor.window", "unavailable", None),
    ("cover.test", "closed", {"current_position": "unknown"}),
    ("cover.test", "unavailable", {"current_position": 0}),
])
def test_invalid_contact_or_feedback_retains_hold_and_recovers(entity, value, attributes):
    world = World(base="opn")
    world.begin_cycle()
    world.event(entity, value, 132, attributes)
    world.release(at=160)
    assert world.helper["win"] == "knx"
    assert world.errors
    assert world.positions == []
    if entity.startswith("binary_sensor."):
        world.event(entity, "off", 175)
        world.restore(at=177)
    else:
        world.restore(at=175)
    world.release()
    assert world.helper["win"] == "cls"


def test_reload_rearms_pending_cycle():
    world = World()
    world.begin_cycle()
    world.restore()
    world.deadline = None
    world.time = world.start + 150
    world.invoke(PRE, SimpleNamespace(id="t_knx_rearm"))
    assert world.deadline == world.start + 160
    world.release()
    assert world.positions == [100]


def test_independent_pause_keeps_prior_manual_override():
    world = World(base="opn", manual=1)
    world.begin_cycle()
    world.restore()
    world.entities["input_boolean.pause"] = State("input_boolean.pause", "on", world.start + 150)
    world.release()
    assert world.positions == []
    assert world.helper["man"] == 1
    assert world.helper["win"] == "cls"


def test_noop_resume_preserves_prior_manual_override():
    world = World(base="opn", manual=1)
    world.begin_cycle()
    world.release()
    assert world.positions == []
    assert world.helper["man"] == 1
    assert world.helper["k"] > 0


def test_live_guard_blocks_reopen_and_refreshes_position_before_dispatch():
    world = World(base="opn")
    values = world.context()
    world.entities["binary_sensor.window"] = State("binary_sensor.window", "on", world.time)
    assert world.condition(ALIASES["knx_drive_guard"], values) is False
    world.entities["binary_sensor.window"] = State("binary_sensor.window", "off", world.time)
    assert world.condition(ALIASES["knx_drive_guard"], values) is True
    values.update(current_position=100, drive_plan={
        "run": True, "target": 100, "target_tilt": 0, "action_set": "up",
    })
    world.run([ALIASES["apply_transition"]], values)
    assert world.positions == [100]


def test_default_disabled_guards_are_real_booleans_and_writer_keeps_v6_schema():
    world = World(enabled=False)
    values = world.context()
    assert world.render(ALIASES["knx_drive_guard"]["value_template"], values) is True
    assert world.render(MANUAL_GUARD["value_template"], values) is True
    assert world.render(CCA["variables"]["knx_ventilation_hold"], values) is False
    values.update(update_values={"bas": "opn", "ts": {"opn": "now"}}, drive_dispatched=False)
    world.run([ALIASES["helper_update"]], values)
    expected = copy.deepcopy(world.initial_helper)
    expected.update(bas="opn", t=int(world.time))
    expected["ts"]["opn"] = int(world.time)
    assert world.helper == expected
    before = world.helper
    world.invoke(PRE)
    assert world.helper == before
    assert world.positions == []


def test_worst_case_helper_payload_fits_255_characters():
    world = World()
    world.time = 1999999999.123456
    h = dict(
        bas="opn", shd=1, pnd="beg", win="knx", frc="non", res=1, man=1,
        ts=dict.fromkeys(["opn", "cls", "shd", "due", "arm", "man"], 1999999999),
        v=6, t=1999999999, d=1999999999, k=-1999999999.999999,
    )
    world.set_helper(h)
    values = world.context()
    values["update_values"] = {}
    world.run([ALIASES["helper_update"]], values)
    assert world.helper["k"] == h["k"]
    assert len(world.states(world.helper_id)) <= 255


def test_additional_target_condition_blocks_drive_without_clearing_manual():
    world = World(base="opn", manual=1)
    world.begin_cycle()
    world.restore()
    world.input_conditions["auto_up_condition"] = False
    world.release()
    assert world.positions == []
    assert world.helper["man"] == 1
    assert world.helper["win"] == "cls"


def test_pending_cycle_survives_restart_with_reset_entity_timestamps():
    world = World(base="opn")
    world.begin_cycle()
    world.restore()
    world.time = world.start + 200
    for key in ("binary_sensor.window", "cover.test"):
        world.entities[key].last_changed = dt(world.time)
        world.entities[key].last_updated = dt(world.time)
    world.deadline = None
    world.invoke(PRE, SimpleNamespace(id="t_knx_rearm"))
    assert world.deadline == world.start + 260
    world.release()
    assert world.positions == [100]


@pytest.mark.parametrize("target,target_tilt", [(0, 0), (25, 0), (100, 0), (100, 40)])
def test_hold_prevents_builtin_dispatch(target, target_tilt):
    world = World(base="opn")
    world.event("binary_sensor.window", "on", 1)
    values = world.context()
    if target_tilt:
        values.update(is_cover_tilt_enabled_and_possible=True, is_cover_tilt_enabled=True,
                      current_tilt_position=10)
    values["drive_plan"] = {
        "run": True, "target": target, "target_tilt": target_tilt, "action_set": "up",
    }
    world.run([ALIASES["apply_transition"]], values)
    assert world.positions == []
    assert world.condition(ALIASES["knx_drive_guard"], values) is False


def test_own_delayed_feedback_does_not_restart_completed_cycle():
    world = World(base="opn")
    world.begin_cycle()
    world.restore()
    world.release()
    old_k = world.helper["k"]
    world.event("cover.test", "open", 163, {"current_position": 100})
    assert world.helper["win"] == "cls"
    assert world.helper["k"] == old_k


def test_real_manual_outside_cycle_runs_original_classifier():
    world = World(base="opn")
    world.begin_cycle()
    world.restore()
    world.release()
    trigger = world.event("cover.test", "open", 400, {"current_position": 80})
    trigger.id = "t_manual_position"
    trigger.attribute = "current_position"
    world.time = world.start + 460
    world.invoke({"sequence": [PRE, {"choose": [MANUAL]}]}, trigger)
    assert world.helper["man"] == 1
    assert world.helper["ts"]["man"] == int(world.time)
    assert world.positions == [100]


def test_queued_feedback_rereads_current_helper_not_pending_snapshot():
    world = World(base="opn")
    world.begin_cycle()
    world.restore()
    queued_values = world.context(SimpleNamespace(id="t_knx_feedback"))
    assert queued_values["helper_json"]["win"] == "knx"
    world.release()
    try:
        world.run([PRE], queued_values)
    except Stop:
        pass
    assert world.helper["win"] == "cls"
    assert world.helper["k"] > 0


def test_pause_release_uses_existing_resume_path():
    world = World(base="opn")
    world.begin_cycle()
    world.restore()
    world.entities["input_boolean.pause"] = State("input_boolean.pause", "on", world.start + 150)
    world.release()
    old_k = world.helper["k"]
    world.time = world.start + 175
    world.entities["input_boolean.pause"] = State("input_boolean.pause", "off", world.time)
    handler = find_alias(CCA["actions"], "Drive to target position after force pause disabled")
    world.invoke({"choose": [handler]}, SimpleNamespace(id="t_force_pause_disabled"))
    assert world.positions == [100]
    assert world.helper["k"] == old_k


def test_resident_privacy_wins_over_open_base_on_release():
    world = World(base="opn")
    world.begin_cycle()
    world.event("cover.test", "open", 132, {"current_position": 100})
    world.entities["binary_sensor.resident"] = State("binary_sensor.resident", "on", world.start + 150)
    world.variable_overrides.update(
        resident_sensor="binary_sensor.resident", resident_config=["resident_closing_enabled"],
    )
    world.release()
    assert world.positions == [0]


def test_latest_live_force_wins_on_release():
    world = World(base="opn")
    world.begin_cycle()
    world.restore()
    world.entities["input_boolean.force_open"] = State("input_boolean.force_open", "on", world.start + 130)
    world.entities["input_boolean.force_shade"] = State("input_boolean.force_shade", "on", world.start + 150)
    world.variable_overrides.update(
        auto_up_force="input_boolean.force_open",
        auto_shading_start_force="input_boolean.force_shade",
    )
    world.release()
    assert world.positions == [25]
    assert world.helper["frc"] == "shd"


def test_same_second_reload_changes_helper_and_rearms_timer():
    world = World(base="opn")
    world.begin_cycle()
    world.time = world.start + 120.1
    world.invoke(PRE, SimpleNamespace(id="t_knx_rearm"))
    first = world.states(world.helper_id)
    world.deadline = None
    world.time = world.start + 120.2
    world.invoke(PRE, SimpleNamespace(id="t_knx_rearm"))
    assert world.states(world.helper_id) != first
    assert world.deadline == world.start + 160


def test_moving_cover_cannot_release():
    world = World(base="opn")
    world.begin_cycle()
    world.event("cover.test", "closing", 147, {"current_position": 0})
    world.release(at=160)
    assert world.helper["win"] == "knx"
    assert world.positions == []
    world.restore(at=165)
    assert world.deadline == world.start + 175
    world.release()
    assert world.positions == [100]


def test_helper_recovery_without_marker_does_not_create_cycle():
    world = World(base="opn", manual=1)
    world.time = world.start + 100
    restored = copy.deepcopy(world.entities[world.helper_id])
    restored.last_updated = dt(world.time)
    trigger = SimpleNamespace(
        id="t_knx_settle", entity_id=world.helper_id,
        from_state=State(world.helper_id, "unavailable", world.time - 10), to_state=restored,
    )
    world.invoke(PRE, trigger)
    assert world.helper["win"] == "cls"
    assert world.helper["man"] == 1
    assert world.deadline is None
    assert world.helper_writes == []
    world.release(at=160)
    assert world.positions == []


def test_overdue_moving_cover_does_not_self_rearm_in_a_loop():
    world = World(base="opn")
    world.begin_cycle()
    world.event("cover.test", "closing", 147, {"current_position": 0})
    before = world.states(world.helper_id)
    writes = len(world.helper_writes)
    for attempt in range(5):
        world.release(at=160 + attempt * 0.1)
        assert world.states(world.helper_id) == before
        assert len(world.helper_writes) == writes
        assert world.positions == []
    world.restore(at=165)
    assert world.deadline == world.start + 175
    world.release()
    assert world.positions == [100]


def test_cover_outage_without_window_cycle_does_not_override_manual():
    world = World(base="opn", manual=1)
    world.event("cover.test", "unavailable", 1, {"current_position": 0})
    world.restore(at=10)
    world.release(at=61)
    assert world.helper["man"] == 1
    assert world.helper["win"] == "cls"
    assert "k" not in world.helper
    assert world.helper_writes == []
    assert world.positions == []


def test_manual_feedback_after_fault_only_recovery_is_classified():
    world = World(base="opn")
    world.event("cover.test", "unavailable", 1, {"current_position": 0})
    world.restore(at=10)
    movement = world.event("cover.test", "closed", 20, {"current_position": 40})
    movement.id = "t_manual_position"
    movement.attribute = "current_position"
    world.time = world.start + 80
    assert world.condition(MANUAL_GUARD, world.context(movement)) is True
    world.invoke({"sequence": [PRE, {"choose": [MANUAL]}]}, movement)
    assert world.helper["man"] == 1
    assert world.helper["ts"]["man"] == int(world.time)
    assert world.helper["win"] == "cls"
    assert world.positions == []


def test_real_window_cycle_during_outage_retains_cycle_priority():
    world = World(base="opn", manual=1)
    world.event("cover.test", "unavailable", 1, {"current_position": 0})
    world.event("binary_sensor.window", "on", 2)
    assert world.helper["win"] == "knx"
    assert world.helper["k"] < 0
    world.event("binary_sensor.window", "off", 100)
    world.restore()
    world.release()
    assert world.positions == [100]
    assert world.helper["man"] == 0


def test_writer_contact_fault_preserves_known_cycle_without_granting_new_priority():
    world = World(base="opn", manual=1)
    world.entities["binary_sensor.window"] = State("binary_sensor.window", "unavailable", world.time)
    values = world.context()
    values["update_values"] = {"bas": "opn"}
    world.run([ALIASES["helper_update"]], values)
    assert world.helper["win"] == "cls"
    assert world.helper["k"] == 0
    assert world.helper["man"] == 1
    h = world.helper
    h.update(win="knx", k=-world.time)
    world.set_helper(h)
    values = world.context()
    values.update(knx_releasing=True, update_values={"win": "cls", "k": world.time})
    world.run([ALIASES["helper_update"]], values)
    assert world.helper["win"] == "knx"
    assert world.helper["k"] == h["k"]


def test_force_open_wins_over_closed_background_after_release():
    world = World(base="cls")
    world.event("binary_sensor.window", "on", 1)
    world.event("cover.test", "open", 10, {"current_position": 100})
    world.event("binary_sensor.window", "off", 100)
    world.restore()
    world.entities["input_boolean.force"] = State("input_boolean.force", "on", world.start + 130)
    world.variable_overrides["auto_up_force"] = "input_boolean.force"
    world.release()
    assert world.positions == [100]
    assert world.helper["frc"] == "opn"


def test_tilt_contact_participates_in_hold_and_closure_wait():
    world = World(base="opn")
    world.variable_overrides["contact_window_tilted"] = "binary_sensor.tilt"
    world.event("binary_sensor.tilt", "on", 1)
    assert world.helper["win"] == "knx"
    assert world.condition(ALIASES["knx_drive_guard"], world.context()) is False
    world.event("binary_sensor.tilt", "off", 100)
    assert world.deadline == world.start + 160


@pytest.mark.parametrize("enabled", [False, True])
def test_empty_optional_inputs_do_not_raise_or_create_cycle(enabled):
    world = World(enabled=enabled)
    world.variable_overrides.update(
        contact_window_opened=[], contact_window_tilted=[],
        force_pause=[], resident_sensor=[], custom_position_sensor=[],
    )
    values = world.context()
    assert values["knx_ventilation_hold"] is enabled
    assert world.render(ALIASES["knx_drive_guard"]["value_template"], values) is (not enabled)
    world.invoke(PRE)
    assert world.helper == world.initial_helper
    assert world.positions == []


def install_strict_state_access(world, reject_all=False):
    def validate(entity_id):
        assert not reject_all, f"Feature-off guard read state for {entity_id!r}"
        assert isinstance(entity_id, str), f"State lookup used an unset input: {entity_id!r}"

    class StrictStateAccess(StateAccess):
        def __call__(self, entity_id):
            validate(entity_id)
            return super().__call__(entity_id)

        def __getitem__(self, entity_id):
            validate(entity_id)
            return super().__getitem__(entity_id)

    states = StrictStateAccess(world)
    original_state_attr = world.env.globals["state_attr"]

    def state_attr(entity_id, attribute):
        validate(entity_id)
        return original_state_attr(entity_id, attribute)

    world.env.globals.update(
        states=states, state_attr=state_attr,
        is_state=lambda entity_id, value: states(entity_id) == value,
    )


@pytest.mark.parametrize("overrides", [
    {"cover_status_helper": []},
    {"position_source": "custom_sensor", "custom_position_sensor": []},
], ids=["missing-helper", "empty-custom-position-source"])
@pytest.mark.parametrize("guard", ["drive", "knx_health_ok", "knx_ready"])
def test_opted_in_missing_inputs_fail_closed_without_empty_state_lookup(overrides, guard):
    world = World()
    values = world.context()
    values.update(overrides)
    install_strict_state_access(world)
    template = (
        ALIASES["knx_drive_guard"]["value_template"] if guard == "drive"
        else PRE["then"][0]["variables"][guard]
    )
    result = world.render(template, values)
    assert type(result) is bool
    if guard == "knx_ready":
        # Timing readiness is consumed only after the independent health gate.
        health = world.render(PRE["then"][0]["variables"]["knx_health_ok"], values)
        assert health is False
        assert (health and result) is False
    else:
        assert result is False
    if guard == "drive":
        with pytest.raises(Stop):
            world.run([PRE], values)
        assert world.errors
    assert world.positions == []
    assert world.helper_writes == []


@pytest.mark.parametrize("guard,expected", [
    ("drive", True), ("manual", True), ("hold", False),
])
def test_disabled_knx_guards_do_not_read_any_state(guard, expected):
    world = World(enabled=False)
    values = world.context()
    install_strict_state_access(world, reject_all=True)
    templates = {
        "drive": ALIASES["knx_drive_guard"]["value_template"],
        "manual": MANUAL_GUARD["value_template"],
        "hold": CCA["variables"]["knx_ventilation_hold"],
    }
    assert world.render(templates[guard], values) is expected


@pytest.mark.parametrize("stored", [
    "empty", "corrupt", "v5-active-shading", "v5-pending-shading",
])
def test_helper_initialization_and_migration_precede_knx_health_gate(stored):
    world = World()
    values = world.context()
    legacy = {
        "open": {"a": 1, "t": 1700000000},
        "close": {"a": 0, "t": 0},
        "shading": {"a": 1, "t": 1700000001, "p": 0, "q": 0},
        "vfull": {"a": 0}, "vpart": {"a": 0},
        "manual": {"a": 1, "t": 1700000002}, "v": 5,
    }
    if stored == "v5-pending-shading":
        legacy["shading"].update(a=0, p=1700000060)
    if stored == "empty":
        raw = ""
    elif stored == "corrupt":
        raw = "not-json"
    else:
        raw = json.dumps(legacy, separators=(",", ":"))
    assert len(raw) <= 255
    world.entities[world.helper_id].state = raw
    values["helper_json"] = world.render(CCA["variables"]["helper_json"], values)
    expected = copy.deepcopy(values["helper_json"])
    repair_index = next(
        index for index, action in enumerate(CCA["actions"])
        if "helper_repair" in action.get("variables", {})
    )
    last_setup_index = max(CCA["actions"].index(PRE), repair_index + 1)
    try:
        world.run(CCA["actions"][1:last_setup_index + 1], values)
    except Stop:
        pass
    assert world.helper_writes
    assert world.errors == []
    assert world.helper["v"] == 6
    for field in ("bas", "shd", "pnd", "man", "ts"):
        assert world.helper[field] == expected[field]
    if stored.startswith("v5"):
        assert world.helper["man"] == 1
        assert world.helper["ts"]["man"] == 1700000002
        if stored == "v5-active-shading":
            assert world.helper["shd"] == 1
            assert world.helper["ts"]["shd"] == 1700000001
        else:
            assert world.helper["pnd"] == "beg"
            assert world.helper["ts"]["due"] == 1700000060
    assert world.positions == []
    assert world.tilt_commands == []


@pytest.mark.parametrize("contact_state", ["on", "unavailable"])
def test_contact_change_during_before_action_blocks_preliminary_tilt_drive(contact_state):
    world = World(base="opn", manual=1)
    world.entities["cover.test"] = State(
        "cover.test", "open", world.time - 1000,
        {"current_position": 100, "current_tilt_position": 50},
    )
    world.input_values["auto_down_action_before"] = [{"delay": {"seconds": 5}}]

    def change_contact(seconds):
        if seconds == 5:
            world.entities["binary_sensor.window"] = State(
                "binary_sensor.window", contact_state, world.time,
            )

    world.delay_hook = change_contact
    values = world.context()
    values.update(
        is_tilt_before_position_mode=True, is_cover_tilt_enabled_and_possible=True,
        is_cover_tilt_enabled=True, update_values={"bas": "cls"},
        drive_plan={"run": True, "target": 0, "target_tilt": 0, "action_set": "down"},
    )
    world.run([ALIASES["apply_transition"]], values)
    assert world.time == world.start + 5
    assert world.positions == []
    assert world.tilt_commands == []
    assert values["drive_dispatched"] is False
    assert world.helper["bas"] == "cls"
    assert world.helper["man"] == 1
    assert world.helper["d"] == 0


@pytest.mark.parametrize("entity_id,blocked_state,instance_active", [
    ("binary_sensor.window", "on", []),
    ("input_boolean.pause", "on", []),
    ("input_boolean.instance", "off", "input_boolean.instance"),
], ids=["contact-opened", "pause-enabled", "instance-deactivated"])
def test_veto_during_tilt_delay_blocks_undispatched_final_tilt(
    entity_id, blocked_state, instance_active,
):
    world = World(manual=1)
    world.entities["cover.test"] = State(
        "cover.test", "open", world.time - 1000,
        {"current_position": 50, "current_tilt_position": 10},
    )
    world.input_values["tilt_delay"] = 5
    if instance_active != []:
        world.entities[instance_active] = State(instance_active, "on", world.time - 1000)

    def activate_veto(seconds):
        if seconds == 5:
            world.entities[entity_id] = State(entity_id, blocked_state, world.time)

    world.delay_hook = activate_veto
    values = world.context()
    values.update(
        is_cover_tilt_enabled_and_possible=True, target_tilt_position=40,
        drive_dispatched=False, instance_active=instance_active,
    )
    world.run([ALIASES["tilt_move_action"]], values)
    assert world.time == world.start + 5
    assert world.positions == []
    assert world.tilt_commands == []
    assert values["drive_dispatched"] is False


def test_contact_opening_between_cover_commands_blocks_remaining_covers():
    world = World()
    world.entities["cover.test"] = State(
        "cover.test", "open", world.time - 1000, {"current_position": 100},
    )
    world.entities["cover.second"] = State(
        "cover.second", "open", world.time - 1000, {"current_position": 100},
    )

    def open_contact(seconds):
        if seconds > 0:
            world.entities["binary_sensor.window"] = State(
                "binary_sensor.window", "on", world.time,
            )

    world.delay_hook = open_contact
    values = world.context()
    values.update(
        blind_entities=["cover.test", "cover.second"], target_position=0,
        target_tilt_position=0, drive_dispatched=False,
    )
    world.run([ALIASES["cover_move_action"]], values)
    assert world.time > world.start
    assert world.positions == [0]
    assert world.tilt_commands == []
    assert values["drive_dispatched"] is True
