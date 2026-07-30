"""
The support tools must know every input and every trigger the blueprint has.

Two maps rot silently when the blueprint grows:

- The validator's `validParams` whitelist. A blueprint input that is missing
  there makes the validator flag a perfectly valid configuration with
  "Unknown parameter" - the tool that exists to build trust reports noise
  (happened for trace_count, tilt_position_tolerance, the logbook options and
  the position-based override reset).
- The trace tools' TRIGGER_EXPLANATIONS. A trigger id without an entry renders
  as "Unknown trigger" in the run summary, exactly where a support case needs
  the plain-words answer (happened for the custom shading condition sensor,
  the alternate shading position, t_reset_position and the recovery/resume
  triggers).

These tests make both a red suite instead of a support dead end, like
test_trace_tools_branch_map.py does for the branch maps.
"""
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
BLUEPRINT = ROOT / "blueprints" / "automation" / "cover_control_automation.yaml"
VALIDATOR = ROOT / "docs" / "validator" / "validator.js"
TRACE_TOOLS = {
    "trace-analyzer": ROOT / "docs" / "trace-analyzer" / "index.html",
    "trace-compare": ROOT / "docs" / "trace-compare" / "index.html",
}


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!input", lambda loader, node: ["__input__"])


def _blueprint() -> dict:
    with open(BLUEPRINT, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)


def _blueprint_inputs() -> set[str]:
    """All input names, flattened across the blueprint's input sections."""
    names: set[str] = set()

    def collect(inputs: dict) -> None:
        for key, value in inputs.items():
            if isinstance(value, dict) and isinstance(value.get("input"), dict):
                collect(value["input"])
            else:
                names.add(key)

    collect(_blueprint()["blueprint"]["input"])
    return names


def _blueprint_trigger_ids() -> set[str]:
    bp = _blueprint()
    triggers = bp.get("triggers") or bp.get("trigger")
    return {t["id"] for t in triggers if isinstance(t, dict) and t.get("id")}


def _js_set_or_object_keys(source: str, name: str) -> set[str]:
    """Quoted strings of a `const/this.<name> = new Set([...])` or `= {...}` block."""
    m = re.search(rf"{name}\s*=\s*(new Set\(\[|\{{)(.*?)(\]\)|\n\s*\}});", source, re.S)
    assert m, f"{name} not found"
    return set(re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(2)))


class TestValidatorParams:
    def test_every_blueprint_input_is_a_valid_param(self):
        """An input missing from the whitelist turns a valid config into an
        'Unknown parameter' warning."""
        valid = _js_set_or_object_keys(VALIDATOR.read_text(encoding="utf-8"), r"this\.validParams")
        missing = sorted(_blueprint_inputs() - valid)
        assert not missing, f"validator.js validParams is missing blueprint inputs: {missing}"

    def test_no_stale_valid_params(self):
        """A whitelist entry for an input that no longer exists hides exactly the
        typo/leftover the unknown-parameter check is there to catch. Removed inputs
        belong in deprecatedParams instead."""
        js = VALIDATOR.read_text(encoding="utf-8")
        valid = _js_set_or_object_keys(js, r"this\.validParams")
        ignored = _js_set_or_object_keys(js, r"this\.ignoredParams")
        stale = sorted(valid - _blueprint_inputs() - ignored)
        assert not stale, f"validator.js validParams has entries for unknown inputs: {stale}"


@pytest.mark.parametrize("tool", TRACE_TOOLS)
class TestTriggerExplanations:
    def test_every_trigger_id_is_explained(self, tool):
        """A trigger id without an entry renders as 'Unknown trigger'."""
        html = TRACE_TOOLS[tool].read_text(encoding="utf-8")
        m = re.search(r"TRIGGER_EXPLANATIONS\s*=\s*\{(.*?)\n\s*\};", html, re.S)
        assert m, f"{tool}: TRIGGER_EXPLANATIONS not found"
        explained = set(re.findall(r"'(t_[a-z0-9_]+)'\s*:", m.group(1)))
        missing = sorted(_blueprint_trigger_ids() - explained)
        assert not missing, f"{tool}: TRIGGER_EXPLANATIONS is missing {missing}"

    def test_no_stale_explanations(self, tool):
        html = TRACE_TOOLS[tool].read_text(encoding="utf-8")
        m = re.search(r"TRIGGER_EXPLANATIONS\s*=\s*\{(.*?)\n\s*\};", html, re.S)
        assert m, f"{tool}: TRIGGER_EXPLANATIONS not found"
        explained = set(re.findall(r"'(t_[a-z0-9_]+)'\s*:", m.group(1)))
        stale = sorted(explained - _blueprint_trigger_ids())
        assert not stale, f"{tool}: TRIGGER_EXPLANATIONS has entries for unknown triggers {stale}"
