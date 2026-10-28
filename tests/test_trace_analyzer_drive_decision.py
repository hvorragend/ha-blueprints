"""
The Trace Analyzer must tell "state updated, movement withheld" apart from
"executed" — and name the blocker.

Every branch ends in the shared apply_transition step. A blocker (force, manual
override, force pause) suppresses only the cover command; the helper write still
happens (Invariant 15). Such a run used to render as "Branch Executed" with the
hint to "check prevent_flags" (#731: Force Close bound to a humidity sensor that
stays on — the morning opening wrote `bas: opn` and moved nothing). The analyzer
now derives the decision from `drive_plan` / `will_drive` / `drive_required` /
`drive_dispatched` and the blocker variables, and reports it as its own outcome.

These tests pin the maps the analyzer uses to the blueprint and make sure the
new outcome is consumed by every renderer, so neither can drift silently.
"""
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
BLUEPRINT = ROOT / "blueprints" / "automation" / "cover_control_automation.yaml"
ANALYZER = ROOT / "docs" / "trace-analyzer" / "index.html"


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!input", lambda loader, node: ["__input__"])


def _analyzer() -> str:
    return ANALYZER.read_text(encoding="utf-8")


def _js_object_keys(html: str, name: str) -> dict[str, str]:
    m = re.search(rf"const\s+{name}\s*=\s*\{{(.*?)\}};", html, re.S)
    assert m, f"{name} not found in the analyzer"
    return dict(re.findall(r"(\w+):\s*'([^']*)'", m.group(1)))


def _blueprint() -> dict:
    with open(BLUEPRINT, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)


def _blueprint_inputs() -> set[str]:
    """Input names, flattened across sections and top-level inputs."""
    bp = _blueprint()
    names = set()
    for key, value in bp["blueprint"]["input"].items():
        if isinstance(value, dict) and isinstance(value.get("input"), dict):
            names.update(value["input"].keys())
        else:
            names.add(key)
    return names


def _find_key(node, key: str):
    """First value of `key` anywhere in the loaded blueprint tree."""
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for v in node.values():
            found = _find_key(v, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_key(item, key)
            if found is not None:
                return found
    return None


class TestForceMapsMirrorBlueprint:
    def test_force_labels_cover_every_frc_value(self):
        labels = _js_object_keys(_analyzer(), "FORCE_LABELS")
        state_labels = _find_key(_blueprint(), "state_labels")
        assert isinstance(state_labels, dict), "state_labels not found in the blueprint"
        # frc enum: every state_labels key except the non-force ones
        frc_values = set(state_labels) - {"non", "lock"}
        assert set(labels) == frc_values, (
            f"FORCE_LABELS keys {sorted(labels)} must equal the frc enum {sorted(frc_values)}"
        )

    def test_force_inputs_name_the_four_force_entities(self):
        inputs = _js_object_keys(_analyzer(), "FORCE_INPUTS")
        labels = _js_object_keys(_analyzer(), "FORCE_LABELS")
        assert set(inputs) == set(labels), "FORCE_INPUTS and FORCE_LABELS must share their keys"
        blueprint_inputs = _blueprint_inputs()
        for frc, input_name in inputs.items():
            assert input_name in blueprint_inputs, f"FORCE_INPUTS[{frc}] = {input_name!r} is not a blueprint input"
        assert inputs == {
            "opn": "auto_up_force",
            "cls": "auto_down_force",
            "shd": "auto_shading_start_force",
            "vnt": "auto_ventilate_force",
        }

    def test_decision_variables_exist_in_the_blueprint(self):
        """The analyzer reads these run variables; they must exist in apply_transition."""
        bp_text = BLUEPRINT.read_text(encoding="utf-8")
        html = _analyzer()
        m = re.search(r"function analyzeDriveDecision\((.*?)\n        \}\n", html, re.S)
        assert m, "analyzeDriveDecision not found"
        body = m.group(1)
        read = set(re.findall(r"latestVariable\(innerTrace,\s*'(\w+)'\)", body))
        read |= set(re.findall(r"entityOf\('(\w+)'\)", body))
        assert read, "analyzeDriveDecision reads no variables"
        for name in read:
            assert re.search(rf"\b{name}\b", bp_text), f"analyzer reads {name!r}, which the blueprint never defines"
        # the four decision variables are the ones apply_transition owns
        assert {"drive_plan", "drive_required", "drive_dispatched", "will_drive"} <= read


class TestStateOnlyOutcomeIsConsumedEverywhere:
    def test_outcome_is_produced(self):
        html = _analyzer()
        assert "outcome = 'state_only'" in html

    def test_every_renderer_handles_the_outcome(self):
        html = _analyzer()
        consumers = {
            "summary card label": "Branch Executed (No Movement)",
            "summary card detail": "State updated, movement withheld",
            "interpretLastStep": "⛔ State updated, movement withheld",
            "renderLastStepAnalysis": "branchInfo.outcome === 'state_only'",
            "branch decision tree": "state updated, movement withheld: ${branchInfo.drive.reason}",
            "text export": "EXECUTED WITHOUT MOVEMENT",
        }
        for where, needle in consumers.items():
            assert needle in html, f"{where} does not handle the state_only outcome ({needle!r} missing)"

    def test_no_stale_blocker_variable_in_variable_groups(self):
        """`is_cover_movement_blocked` never existed in the blueprint."""
        assert "is_cover_movement_blocked" not in _analyzer()
