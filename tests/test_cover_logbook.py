"""
Structural tests for the cover-facing logbook line (enable_logbook_cover).

Invariant 12 keeps the *diagnostic* logbook free of reason inference: it dumps
trigger.id plus the raw update_values. The second, user-facing line on the
cover is allowed to name a reason - but only as a per-branch `log_user` string
(same mechanic as `log_extra`), never as a central table. These tests pin the
mechanic, not the wording:

  1. The step lives inside apply_transition, is gated by enable_logbook_cover
     and by "drove or opted in", and sits BEFORE the helper persist (so the
     anchor still ends in the write - see TestApplyTransitionAnchorShape).
  2. It writes to the covers, not to the automation.
  3. Every log_user is a short, single-line, non-empty string.
  4. state_labels covers every state the target chains can produce, so a
     `state_labels[<target>]` lookup can never raise.
  5. The message template renders for drive / tilt-only / suppressed runs.
"""
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


def _load_blueprint_yaml() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor(
        "!input",
        lambda loader, node: loader.construct_scalar(node),
    )
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


def _anchors() -> dict:
    return _load_blueprint_yaml()["actions"][0]["variables"]


def _logbook_step() -> dict:
    for step in _anchors()["apply_transition"]["sequence"]:
        if "logbook.log" in str(step):
            return step
    raise AssertionError("cover logbook step missing from apply_transition")


def _message_template() -> str:
    return _logbook_step()["then"][0]["repeat"]["sequence"][0]["data"]["message"]


class TestTheStepIsWiredCorrectly:
    def test_input_exists_and_defaults_to_off(self):
        blueprint = _load_blueprint_yaml()["blueprint"]
        section = blueprint["input"]["logging_section"]["input"]
        assert "enable_logbook_cover" in section, "input missing"
        assert section["enable_logbook_cover"]["default"] is False, (
            "the cover logbook must be opt-in"
        )
        assert "boolean" in section["enable_logbook_cover"]["selector"]

    def test_input_is_bound_to_a_variable(self):
        variables = _load_blueprint_yaml()["variables"]
        assert variables.get("enable_logbook_cover") == "enable_logbook_cover"

    def test_step_is_gated_by_the_toggle_and_by_drove_or_opted_in(self):
        gate = str(_logbook_step()["if"])
        assert "enable_logbook_cover" in gate, "step must honour the toggle"
        assert "log_user is defined" in gate, "opt-in path missing"
        assert "run" in gate and "drive_plan" in gate, "drive path missing"

    def test_step_runs_before_the_helper_persist(self):
        # Invariant 2 / TestApplyTransitionAnchorShape: the anchor must still
        # END in the unconditional write, so the logbook cannot be last.
        seq = _anchors()["apply_transition"]["sequence"]
        logbook_idx = next(i for i, s in enumerate(seq) if "logbook.log" in str(s))
        persist_idx = next(
            i for i, s in enumerate(seq) if "input_text.set_value" in str(s)
        )
        assert logbook_idx < persist_idx

    def test_it_writes_to_the_covers_not_the_automation(self):
        step = _logbook_step()
        repeat = step["then"][0]["repeat"]
        assert "blind_entities" in str(repeat["for_each"])
        data = repeat["sequence"][0]["data"]
        assert "repeat.item" in data["entity_id"]
        assert "this.entity_id" not in str(data), (
            "the diagnostic entry targets the automation; this one targets the cover"
        )

    def test_it_is_prerender_safe(self):
        # Invariant 14: the anchor body is rendered on every run, so every
        # runtime-context reference needs a guard.
        flat = str(_logbook_step())
        assert "repeat is defined" in flat
        assert "log_user is defined" in flat
        unguarded = re.findall(r"(?<!\()drive_plan\.\w+", flat)
        assert unguarded == [], f"unguarded drive_plan references: {unguarded}"

    def test_it_does_not_reach_for_action_scope_variables_unguarded(self):
        """state_labels lives in a later action step than the anchor definition,
        so an unguarded subscript raises during the pre-render of every run as
        soon as a force function is active."""
        anchor_step_index, labels_step_index = None, None
        for index, step in enumerate(_load_blueprint_yaml()["actions"]):
            variables = step.get("variables") if isinstance(step, dict) else None
            if isinstance(variables, dict):
                if "apply_transition" in variables:
                    anchor_step_index = index
                if "state_labels" in variables:
                    labels_step_index = index
        assert anchor_step_index is not None and labels_step_index is not None
        if labels_step_index > anchor_step_index:
            flat = str(_logbook_step())
            assert "state_labels[" not in flat, (
                "subscripting state_labels inside the anchor is unsafe - use "
                "(state_labels | default({})).get(...)"
            )


class TestLogUserStrings:
    """log_user is free-form, but it ends up in a user's history - keep it sane."""

    def _log_user_values(self) -> list[str]:
        """Every log_user is written as a one-line double-quoted scalar."""
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        assert "log_user: >" not in text, (
            "keep log_user a one-line quoted scalar - folded blocks make the "
            "logbook row unpredictable"
        )
        return re.findall(r'^\s*log_user:\s*"([^"]+)"\s*$', text, re.MULTILINE)

    @staticmethod
    def _literal_part(value: str) -> str:
        """The value with Jinja expressions removed - what is fixed wording."""
        return re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", value)

    def test_there_are_log_user_strings(self):
        assert len(self._log_user_values()) >= 25, (
            "expected the drive/suppress branches to name their decision"
        )

    def test_every_value_is_short_and_single_line(self):
        for value in self._log_user_values():
            assert value.strip(), "empty log_user"
            assert "\n" not in value, f"log_user must be one line: {value!r}"
            # Measured on the literal wording: a Jinja expression is long in
            # source and short once rendered.
            literal = self._literal_part(value)
            assert len(literal) <= 110, (
                f"log_user too long for a logbook row: {value!r}"
            )

    def test_no_helper_field_names_leak_into_the_user_text(self):
        # Users read this, not developers: no schema fields or trigger ids.
        for value in self._log_user_values():
            bare = self._literal_part(value)
            for token in ("helper_json", "update_values", "t_shading", "t_open",
                          "t_close", "effective_state", "drive_plan"):
                assert token not in bare, f"{token!r} leaks into {value!r}"


class TestStateLabels:
    def test_labels_cover_every_target_state(self):
        anchors_and_vars = _load_blueprint_yaml()["actions"]
        labels = targets = None
        for step in anchors_and_vars:
            variables = step.get("variables") if isinstance(step, dict) else None
            if isinstance(variables, dict):
                labels = variables.get("state_labels", labels)
                targets = variables.get("state_targets", targets)
        assert labels and targets
        missing = set(targets) - set(labels)
        assert missing == set(), f"state_labels misses {missing}"
        assert "non" in labels, "'non' targets must render too"

    def test_every_label_lookup_uses_a_key_that_exists(self):
        """The chains resolve to lock/opn/vnt/shd/cls/non - nothing else."""
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        lookups = set(re.findall(r"state_labels\[(\w+)\]", text))
        known_chains = {
            "recovered_state", "return_target", "leave_target", "recovery_target",
            "force_kind", "next_active_force", "resume_state", "reset_state",
            "helper_state_force",
        }
        assert lookups <= known_chains, (
            f"unknown target variable in a state_labels lookup: {lookups - known_chains}"
        )


class TestMessageRendering:
    def _render(self, **context) -> str:
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        base = dict(
            is_paused=False,
            helper_state_manual=False,
            helper_state_force="non",
            is_cover_tilt_enabled_and_possible=False,
            drive_action_set="",
            # Blueprint-level variables - always defined, even at pre-render time.
            current_position=100,
            current_tilt_position=101,
            position_tolerance=0,
            tilt_position_tolerance=0,
            state_labels={"lock": "fully open (window open)", "opn": "open",
                          "vnt": "ventilation position", "shd": "sun shading position",
                          "cls": "closed", "non": "no change"},
        )
        base.update(context)
        return env.from_string(_message_template()).render(**base).strip()

    def test_a_drive_names_position_and_reason(self):
        out = self._render(drive_plan={"run": True, "target": 40},
                           log_user="shading started")
        assert out == "moved to 40% · shading started"

    def test_a_tilt_cover_gets_its_slat_angle(self):
        out = self._render(drive_plan={"run": True, "target": 40, "target_tilt": 50},
                           is_cover_tilt_enabled_and_possible=True,
                           log_user="shading started")
        assert out == "moved to 40% / tilt 50% · shading started"

    def test_a_tilt_only_move_does_not_claim_a_position(self):
        out = self._render(drive_plan={"run": True, "move": "tilt", "target_tilt": 80},
                           log_user="shading tilt adjusted")
        assert out == "tilt to 80% · shading tilt adjusted"


    def test_a_drive_without_log_user_falls_back_to_the_action_set(self):
        out = self._render(drive_plan={"run": True, "target": 100},
                           current_position=0, drive_action_set="up")
        assert out == "moved to 100% · opening as scheduled"

    def test_a_suppressed_run_names_the_suppressor(self):
        blocked = self._render(drive_plan={"run": False}, is_paused=True,
                               log_user="opening time reached")
        assert blocked == "no movement [force pause] · opening time reached"

        manual = self._render(drive_plan={"run": False}, helper_state_manual=True,
                              log_user="closing time reached")
        assert manual == "no movement [manual override] · closing time reached"

        forced = self._render(drive_plan={"run": False}, helper_state_force="shd",
                              log_user="closing time reached")
        assert forced == (
            "no movement [force: sun shading position] · closing time reached"
        )

    def test_a_suppressed_run_without_a_known_suppressor_stays_plain(self):
        out = self._render(drive_plan={"run": False}, log_user="shading noted for later")
        assert out == "no movement · shading noted for later"

    def test_it_survives_a_missing_drive_plan_and_missing_labels(self):
        # Invariant 14: the anchor body is pre-rendered before the action-scope
        # variables exist - with a force active, an unguarded state_labels
        # lookup would raise here. Only blueprint-level variables (which are
        # rendered before the action tree) may be relied on.
        # trigger_variables and the automation-level variables are both
        # rendered before the action tree, so the anchor may use them unguarded.
        blueprint = _load_blueprint_yaml()
        pre_action = set(blueprint["variables"]) | set(blueprint["trigger_variables"])
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        for name in ("current_position", "current_tilt_position",
                     "position_tolerance", "tilt_position_tolerance",
                     "is_cover_tilt_enabled_and_possible", "is_paused",
                     "helper_state_manual", "helper_state_force"):
            assert name in pre_action, (
                f"{name} is set inside the action tree - the anchor is "
                f"pre-rendered before that and may not use it unguarded"
            )
        out = env.from_string(_message_template()).render(
            is_paused=False, helper_state_manual=False, helper_state_force="cls",
            is_cover_tilt_enabled_and_possible=False, current_position=50,
            current_tilt_position=101, position_tolerance=0,
            tilt_position_tolerance=0,
        ).strip()
        assert out == "no movement [force: cls] · status update"


class TestNothingWouldHaveMoved:
    """The cover's history is for movements: one that happened, or one that was
    wanted and then suppressed. A drive decided onto a position the cover
    already holds is neither - cover_move_action sends nothing, Home Assistant
    logs nothing, so CCA must stay quiet too. Same for a suppressed drive whose
    target was already reached."""

    def _fires(self, **context) -> bool:
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        base = dict(
            enable_logbook_cover=True,
            is_cover_tilt_enabled_and_possible=False,
            current_position=100,
            current_tilt_position=101,
            position_tolerance=0,
            tilt_position_tolerance=0,
        )
        base.update(context)
        rendered = env.from_string(str(_logbook_step()["if"])).render(**base).strip()
        assert rendered in ("True", "False"), rendered
        return rendered == "True"

    def test_a_real_movement_is_logged(self):
        assert self._fires(drive_plan={"run": True, "target": 40})

    def test_a_drive_onto_the_held_position_is_not_logged(self):
        assert not self._fires(drive_plan={"run": True, "target": 100})

    def test_the_position_tolerance_counts_as_held(self):
        assert not self._fires(drive_plan={"run": True, "target": 98},
                               position_tolerance=3)
        assert self._fires(drive_plan={"run": True, "target": 98},
                           position_tolerance=1)

    def test_a_suppressed_drive_onto_the_held_position_is_not_logged(self):
        """state_gates already yield run=false when the cover sits at the
        target - that is not a suppressed movement, it is a non-event."""
        assert not self._fires(drive_plan={"run": False, "target": 100},
                               log_user="the resident is no longer present")

    def test_a_suppressed_drive_that_would_have_moved_is_logged(self):
        assert self._fires(drive_plan={"run": False, "target": 0},
                           log_user="closing time reached")

    def test_matching_position_but_wrong_slats_still_counts_as_movement(self):
        assert self._fires(drive_plan={"run": True, "target": 100, "target_tilt": 50},
                           is_cover_tilt_enabled_and_possible=True,
                           current_tilt_position=10)

    def test_a_tilt_only_plan_compares_only_the_slats(self):
        assert not self._fires(
            drive_plan={"run": True, "move": "tilt", "target_tilt": 80},
            is_cover_tilt_enabled_and_possible=True, current_tilt_position=80)
        assert self._fires(
            drive_plan={"run": True, "move": "tilt", "target_tilt": 80},
            is_cover_tilt_enabled_and_possible=True, current_tilt_position=10)

    def test_a_branch_without_any_target_still_reports_its_reason(self):
        """Deferrals and pending arms carry no plan - a movement was expected
        and did not happen, which is exactly what the user wants to read."""
        assert self._fires(drive_plan={},
                           log_user="waiting to see whether sun shading starts")
        assert self._fires(log_user="the cover was moved by hand")

    def test_the_tilt_sentinel_is_never_compared(self):
        """target_tilt 101 means 'no tilt change' - comparing it to a real slat
        angle would keep every entry alive for no reason."""
        assert not self._fires(drive_plan={"run": True, "target": 100},
                               is_cover_tilt_enabled_and_possible=True,
                               current_tilt_position=30)


class TestIntegrityEvents:
    """Rare, user-relevant events that never reach apply_transition: the status
    helper being migrated/rebuilt, and the hard config errors that stop a run."""

    def test_the_repair_case_is_classified(self):
        variables = None
        for step in _load_blueprint_yaml()["actions"]:
            if isinstance(step, dict) and isinstance(step.get("variables"), dict):
                if "helper_repair" in step["variables"]:
                    variables = step["variables"]["helper_repair"]
        assert variables, "helper_repair classification missing"
        for case in ("migrated", "initialised", "rebuilt", "cleaned", "non"):
            assert case in variables, f"{case!r} case not classified"

    def _repair_block(self) -> str:
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        return text.split("helper_repair != 'non'")[1][:2500]

    def test_every_repair_case_has_a_message(self):
        block = self._repair_block()
        for case in ("migrated", "initialised", "rebuilt", "cleaned"):
            assert f"'{case}':" in block, f"no message for the {case!r} case"

    def test_the_repair_is_reported_to_all_three_audiences(self):
        """Three different questions lead to this event, each asked somewhere
        else: the helper itself, the cover, and the automation's dump."""
        block = self._repair_block()
        assert "entity_id: !input cover_status_helper" in block, (
            "someone debugging the status helper looks at the helper first"
        )
        assert "blind_entities" in block and "enable_logbook_cover" in block, (
            "the cover line explains the consequence and honours the toggle"
        )
        assert "log_extra:" in block, (
            "the automation's diagnostic dump must say that this was a repair"
        )

    def test_the_repair_label_cannot_bleed_into_later_entries(self):
        """log_extra is a run-wide variable: without the reset, every later
        branch without its own log_extra would inherit the repair label."""
        block = self._repair_block()
        assert block.count("log_extra:") == 2 and 'log_extra: ""' in block, (
            "set log_extra for the repair dump, then reset it"
        )
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        assert text.count("{% if log_extra is defined and log_extra %}") == 2, (
            "an empty log_extra must render nothing, not 'extra='"
        )

    def test_config_errors_reach_every_cover(self):
        """One of them used to target only blind_entities[0], another one the
        status helper - where a user hunting a misbehaving cover never looks."""
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        assert "blind_entities[0]" not in text, (
            "a config error must be logged on every cover, not just the first"
        )
        for stop in ("Missing Cover Status Helper configuration",
                     "Cover Status Helper max length too small",
                     "state-critical entity disabled or deleted"):
            before = text.split(stop)[0][-1200:]
            assert "blind_entities" in before and "logbook.log" in before, (
                f"the {stop!r} stop does not report on the covers"
            )
