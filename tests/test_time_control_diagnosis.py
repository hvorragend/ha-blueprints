"""
"Time Control off while Brightness / Sun Elevation triggers are on" is the
configuration state behind most "the cover opens before the configured time"
reports since the 2026.07.12 breaking change (#544 / #595 / #661): configs from
before the ~2026.05 options consolidation do not store time_control_enabled,
so their sensor triggers keep firing without a time fence. Nothing in such a
run is wrong - is_opening_phase is false and should_be_open_now is true, which
is exactly what "no time window" evaluates to - so no branch or condition
analysis can explain it. Two places have to say it in plain words instead:
the built-in configuration check and the Trace Analyzer's run summary.
"""
import pathlib
import re

import jinja2
import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
BLUEPRINT = ROOT / "blueprints" / "automation" / "cover_control_automation.yaml"
ANALYZER = ROOT / "docs" / "trace-analyzer" / "index.html"


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!input", lambda loader, node: ["__input__"])


def _config_check_items() -> list[dict]:
    with open(BLUEPRINT, encoding="utf-8") as f:
        bp = yaml.load(f, Loader=_Loader)
    choose = next(s for s in bp["actions"]
                  if isinstance(s, dict) and "choose" in s and "default" in s)
    return choose["default"][0]["then"][0]["repeat"]["for_each"]


def _render_bool(template: str, ctx: dict) -> bool:
    out = jinja2.Environment().from_string(template).render(**ctx).strip()
    assert out in ("True", "False"), out
    return out == "True"


HYBRID_OFF = dict(
    is_up_enabled=True, is_down_enabled=False, is_time_control_disabled=True,
    is_brightness_enabled=True, default_brightness_sensor="sensor.lux",
    is_sun_elevation_enabled=False, default_sun_sensor=[],
)


class TestConfigCheckWarnsAboutSensorTriggersWithoutTimeWindows:
    @pytest.fixture(scope="class")
    def condition(self) -> str:
        items = [i for i in _config_check_items()
                 if "WITHOUT time windows" in i["message"]]
        assert len(items) == 1, "exactly one #595 mirror warning expected"
        return items[0]["condition"]

    def test_fires_for_the_issue_661_configuration(self, condition):
        assert _render_bool(condition, HYBRID_OFF) is True
        sun_only = {**HYBRID_OFF, "is_brightness_enabled": False,
                    "is_sun_elevation_enabled": True, "default_sun_sensor": "sun.sun"}
        assert _render_bool(condition, sun_only) is True

    @pytest.mark.parametrize("override", [
        {"is_time_control_disabled": False},        # time windows active: nothing to warn about
        {"is_brightness_enabled": False},           # no sensor source: the "no trigger" check owns it
        {"default_brightness_sensor": []},          # brightness checked but no sensor picked
        {"is_up_enabled": False},                   # neither opening nor closing automated
    ])
    def test_stays_silent_when_time_windows_are_not_the_problem(self, condition, override):
        assert _render_bool(condition, {**HYBRID_OFF, **override}) is False


class TestTraceAnalyzerNamesTheState:
    def test_the_run_summary_carries_the_diagnosis(self):
        html = ANALYZER.read_text(encoding="utf-8")
        assert "function buildConfigDiagnosis" in html
        assert "${configDiagnosis}" in html, "the diagnosis card must land in the summary grid"
        body = re.search(r"function buildConfigDiagnosis.*?\n        function renderSummary", html, re.S).group(0)
        for needle in ("is_time_control_disabled", "is_brightness_enabled", "is_sun_elevation_enabled",
                       "Time Control", "ha-blueprints/FAQ"):
            assert needle in body, needle
