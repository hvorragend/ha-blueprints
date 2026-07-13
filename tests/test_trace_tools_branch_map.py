"""
The trace tools must agree with the blueprint about which branch is which.

A Home Assistant trace only records the POSITIONAL index of the branch that ran
("action/N/choose/M"), never its name. The tools therefore resolve M against the
branch aliases: from the trace's own `config` section when it is present, and
against the hardcoded BRANCH_ORDER fallback when it is not (a truncated trace has
no config - see repairTruncatedJson).

That fallback is the part that rots. It has silently drifted out of sync with the
blueprint every time a branch was inserted into the choose:, and the failure mode is
the worst kind - the tool does not error, it confidently names the wrong branch. A
user reports "the cover closed although the window was open", the analyzer says
"Resident Update", and the branch that actually ran was the contact handler.

These tests make that drift a red suite instead of a support dead end.
"""
import json
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
BLUEPRINT = ROOT / "blueprints" / "automation" / "cover_control_automation.yaml"
TOOLS = {
    "trace-analyzer": ROOT / "docs" / "trace-analyzer" / "index.html",
    "trace-compare": ROOT / "docs" / "trace-compare" / "index.html",
}


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!input", lambda loader, node: ["__input__"])


def _blueprint_branch_aliases() -> list[str]:
    """The aliases of the main dispatch choose, in execution order."""
    with open(BLUEPRINT, encoding="utf-8") as f:
        bp = yaml.load(f, Loader=_Loader)
    for step in bp["actions"]:
        if isinstance(step, dict) and isinstance(step.get("choose"), list) and len(step["choose"]) > 5:
            return [b["alias"] for b in step["choose"]]
    raise AssertionError("main dispatch choose not found in the blueprint")


def _js_array(html: str, name: str) -> list[str]:
    """Pull a `const <name> = [ ... ];` string array out of the tool's JS."""
    m = re.search(rf"const\s+{name}\s*=\s*\[(.*?)\];", html, re.S)
    assert m, f"{name} not found"
    return re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(1))


def _js_object_keys(html: str, name: str) -> list[str]:
    """Pull the quoted keys of a `const <name> = { ... };` object out of the JS."""
    m = re.search(rf"const\s+{name}\s*=\s*\{{(.*?)\n        \}};", html, re.S)
    assert m, f"{name} not found"
    return re.findall(r"^\s{12}'((?:[^'\\]|\\.)*)'\s*:", m.group(1), re.M)


@pytest.mark.parametrize("tool", TOOLS)
class TestBranchMap:
    def test_fallback_order_matches_the_blueprint(self, tool):
        """BRANCH_ORDER is what a truncated trace (no config) is resolved against.
        If it drifts, every trace from the insertion point on is mislabelled."""
        html = TOOLS[tool].read_text(encoding="utf-8")
        assert _js_array(html, "BRANCH_ORDER") == _blueprint_branch_aliases()

    def test_every_branch_has_a_definition(self, tool):
        """A branch with no entry falls back to 'Branch N' / 'Unknown branch'."""
        html = TOOLS[tool].read_text(encoding="utf-8")
        defined = set(_js_object_keys(html, "BRANCH_DEFINITIONS"))
        missing = [a for a in _blueprint_branch_aliases() if a not in defined]
        assert not missing, f"{tool}: no BRANCH_DEFINITIONS entry for {missing}"

    def test_no_stale_definitions(self, tool):
        """A leftover entry for a branch that no longer exists is dead weight and a
        sign the map was edited without looking at the blueprint."""
        html = TOOLS[tool].read_text(encoding="utf-8")
        aliases = set(_blueprint_branch_aliases())
        stale = [k for k in _js_object_keys(html, "BRANCH_DEFINITIONS") if k not in aliases]
        assert not stale, f"{tool}: BRANCH_DEFINITIONS has entries for unknown branches {stale}"

    def test_the_index_is_not_used_as_the_primary_key(self, tool):
        """Guard against a revert to `BRANCH_DEFINITIONS[branchNum]`: the whole point is
        that the index is only the fallback, the alias is the key."""
        html = TOOLS[tool].read_text(encoding="utf-8")
        assert not re.search(r"BRANCH_DEFINITIONS\[\s*(branchNum|num|i)\s*\]", html), (
            f"{tool}: BRANCH_DEFINITIONS is indexed by position again - that is the bug "
            "this map was restructured to prevent"
        )


class TestConfigResolution:
    """The tools must prefer the aliases carried in the trace's own config, so a trace
    from a different blueprint version still resolves correctly."""

    @pytest.mark.parametrize("tool", TOOLS)
    def test_the_resolver_reads_the_trace_config(self, tool):
        html = TOOLS[tool].read_text(encoding="utf-8")
        assert "branchAliasesFromConfig" in html
        assert re.search(r"(setBranchAliases|resolveBranch)\(.*?\.config", html), (
            f"{tool}: the resolver never looks at the trace's config section"
        )

    def test_the_blueprint_aliases_are_unique(self):
        """Alias-keyed resolution only works while the aliases are unique - which the
        Code Quality gate in CLAUDE.md requires anyway ('unique alias per branch')."""
        aliases = _blueprint_branch_aliases()
        dupes = [a for a in set(aliases) if aliases.count(a) > 1]
        assert not dupes, f"duplicate branch aliases: {dupes}"
