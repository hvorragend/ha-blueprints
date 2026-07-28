{% raw %}
# 📝 Logging

[📖 CCA Handbook](index) › Blueprint section: **Logging**

Optional logbook output for retrospective debugging. Two independent entries are available: a technical one on the automation, and a short plain-word one on the cover. Both are useful when the 5-trace history is not enough to understand a cover's behavior over the day.

**On this page:** [📓 Enable Logbook entries](#enable_logbook) · [🪟 Log decisions on the cover](#enable_logbook_cover) · [📜 Number of stored traces](#trace_count)

---

<a id="enable_logbook"></a>

## 📓 Enable Logbook entries

> 🧩 Input: `enable_logbook` · Default: `False`

When enabled, every automation run writes a single logbook entry with full context: the trigger, the resulting effective state, the cover position and a snapshot of all relevant sensor values. The entry is written to the **automation**, so you find it in the automation's own history — not in the cover's. Disabled by default to avoid noise in the Activities view. Toggle on while debugging a configuration.

---

<a id="enable_logbook_cover"></a>

## 🪟 Log decisions on the cover

> 🧩 Input: `enable_logbook_cover` · Default: `False`

When enabled, a short entry is written to the logbook of the **cover** whenever CCA moves it or deliberately decides against a movement. The entry appears in the cover's history and on its device page, right next to the actual position changes — so the reason for a movement stays visible long after the automation traces have been overwritten.

The line always has the same shape: what happened, then why.

```text
Cover Control  moved to 40% / tilt 50% · sun shading started
Cover Control  moved to 84% · closing as scheduled
Cover Control  moved to 95% · the window was tilted, going to the ventilation position
Cover Control  no movement [manual override] · closing time reached
Cover Control  no movement · sun shading is due, but the window is open
Cover Control  tilt to 100% · sun shading is over, opening the slats only
```

A bracket after `no movement` names what suppressed the drive when CCA can tell: `[force pause]`, `[manual override]` or `[force: sun shading position]`.

Runs that only synchronise status fields — a window contact reporting the state CCA already assumed, a presence update with no consequence, a base-state refresh on a cover that is already where it belongs — write nothing, so the cover's history does not fill up with noise. Repeated waiting cycles of a pending sun shading are silent too; only the final outcome is logged.

**Why this is not just a copy of what Home Assistant already logs:** the built-in logbook only records *state* changes, and a cover's state is `open` / `closed` / `opening` / `closing` — `closed` only at 0 %. The position is an attribute, and attribute changes produce no logbook entry at all. A move from 100 % to 84 % therefore reads as "is closing" followed by "is open", with no number and no reason; a move from 100 % to 95 % may produce nothing whatsoever. Which position CCA aimed for, and why, is information that exists nowhere else once the traces are gone.

### Rare status events

Independently of any movement, the same option logs the handful of events that affect the stored status itself — each of them roughly a once-in-a-lifetime occurrence:

```text
Cover Control  status set up for the first time, this cover is now automated
Cover Control  status format upgraded, nothing changes for you
Cover Control  the stored status was unreadable and had to be rebuilt - sun shading and manual override are cleared
Cover Control  leftovers from an older status format cleaned up, a waiting sun shading was dropped
```

The third one is the interesting case: it explains why a cover suddenly "forgot" that sun shading was active.

These events are also written to the **status helper itself**, without any toggle — if you go looking for the helper because you suspect something is wrong with it, the answer should be waiting there. (Note that many people exclude helpers from the recorder; then only the entry on the cover survives.) With 📓 Enable Logbook entries switched on, the technical entry on the automation names the repair as well.

Hard configuration errors that stop the automation (no status helper configured, its maximum length too small, a required entity switched off or deleted) are written to **every** configured cover as well — these are logged regardless of this option, because a cover that silently stops being controlled is exactly what you need to find out about.

Two things to know:

- **The messages are English only.** A logbook entry has no translation layer, so they cannot follow your Home Assistant language. They are kept short and simple for that reason.
- **They live as long as your recorder keeps them** (`purge_keep_days`, 10 days by default), and they are gone if you exclude the cover from the recorder.

This option is independent of 📓 Enable Logbook entries — you can run either, both, or neither.

---

<a id="trace_count"></a>

## 📜 Number of stored traces

> 🧩 Input: `trace_count` · Default: `5`

Set how many traces Home Assistant shall keep for this automation.

---

[⬅️ Handbook index](index) · Previous: [🩺 Configuration Check](configcheck)

{% endraw %}
