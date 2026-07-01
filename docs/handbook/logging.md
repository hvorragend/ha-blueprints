{% raw %}
# 📝 Logging

> Part of the [CCA Handbook](index). These options live in the **Logging** section of the blueprint.

Optional logbook output for retrospective debugging. Each automation run writes one combined logbook entry containing the trigger, the resulting effective state, and a snapshot of all relevant sensor values. Useful when the 5-trace history is not enough to understand a cover's behavior over the day.

<a id="enable_logbook"></a>

## 📓 Enable Logbook entries

*Blueprint input: `enable_logbook`* *(default: `False`)*

When enabled, every automation run writes a single logbook entry with full context. Disabled by default to avoid noise in the Activities view. Toggle on while debugging a configuration.

<a id="trace_count"></a>

## 📜 Number of stored traces

*Blueprint input: `trace_count`* *(default: `5`)*

Set how many traces Home Assistant shall keep for this automation.

{% endraw %}
