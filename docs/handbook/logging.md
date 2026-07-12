{% raw %}
# 📝 Logging

[📖 CCA Handbook](index) › Blueprint section: **Logging**

Optional logbook output for retrospective debugging. Each automation run writes one combined logbook entry containing the trigger, the resulting effective state, and a snapshot of all relevant sensor values. Useful when the 5-trace history is not enough to understand a cover's behavior over the day.

**On this page:** [📓 Enable Logbook entries](#enable_logbook) · [📜 Number of stored traces](#trace_count)

---

<a id="enable_logbook"></a>

## 📓 Enable Logbook entries

> 🧩 Input: `enable_logbook` · Default: `False`

When enabled, every automation run writes a single logbook entry with full context. Disabled by default to avoid noise in the Activities view. Toggle on while debugging a configuration.

---

<a id="trace_count"></a>

## 📜 Number of stored traces

> 🧩 Input: `trace_count` · Default: `5`

Set how many traces Home Assistant shall keep for this automation.

---

[⬅️ Handbook index](index) · Previous: [🩺 Configuration Check](configcheck)

{% endraw %}
