{% raw %}
# ⚙️ Features & Modes

[📖 CCA Handbook](index) › Blueprint section: **Automation Options**

Configure what CCA controls and how it behaves. Most settings use safe defaults. Expand the descriptions below only if you need details.

**On this page:** [👉 What should CCA control?](#auto_options) · [⏲️ Time Control Type](#time_control) · [🔀 Condition Logic: Brightness & Sun Elevation](#brightness_sun_operator) · [⚙️ Behavior Customization](#individual_config) · [🔄 Catch up after a restart or an outage](#enable_recovery)

---

<a id="auto_options"></a>

## 👉 What should CCA control?

> 🧩 Input: `auto_options` · Default: `['auto_up_enabled', 'auto_down_enabled', 'time_control_enabled']`

Select which opening, closing, and special behaviors CCA should manage.
*Not sure? The defaults (Morning Opening, Evening Closing, Time Control) work for most setups.*

### How these options work together

**Basic Controls (When to move):**

- **Morning Opening / Evening Closing** — Enable automatic opening and/or closing.

**Fine-Tuning (When to trigger):**

- **⏲️ Time Control** — Defines the Early/Late time windows that constrain *all* other triggers.
Keep this ON even when using Brightness or Sun Elevation — the time fields set the boundaries.
Early = earliest the cover may move; Late = guaranteed move (safety net).
**Uncheck to disable all time windows** (pure sensor control — no guaranteed Late safety net).

- **🔅 Brightness** / **☀️ Sun Elevation** — Additional triggers that fire *within* the time window.
Set the condition logic (AND/OR) when both are active.
Configure thresholds and sensors in the dedicated sections below.

**Advanced Features (How to react):**

- **💨 Ventilation** — React to open/tilted windows, prevent lockout.

- **🥵 Sun Protection** — Partially close when sun shines directly on the window (midday heat).

**☀️ Sun Elevation vs. 🥵 Sun Protection are two different things!**

- **Sun Elevation** = *When* to open/close (sunrise/sunset trigger) — configure in *Sun Elevation Settings*

- **Sun Protection** = *Shading* during midday when the sun shines directly on the window

**Example: Sun Elevation + Time Control (most common setup)**

- **6:00** — Early time reached → Sun Elevation trigger is now allowed

- **6:30** — Sun rises above threshold → cover opens

- **8:00** — Late time → cover would open now regardless (but it's already open)

- **20:00** — Early closing time reached → Sun Elevation trigger is now allowed

- **21:00** — Sun drops below threshold → cover closes

- **22:00** — Late closing time → cover would close regardless (safety net)

**Notes on multiple triggering**

Even if multiple opening, closing, shading, etc. is activated, this only works if a trigger is available.
However, the numeric state triggers only trigger under certain circumstances. See: [FAQ: Why are my numeric triggers not firing?](https://hvorragend.github.io/ha-blueprints/FAQ#q-why-are-my-numeric-triggers-not-firing)

---

<a id="time_control"></a>

## ⏲️ Time Control Type

> 🧩 Input: `time_control` · Default: `time_control_input`

Select how time-based opening and closing is scheduled. *(Only relevant when **⏲️ Time Control** is checked in the **👉 What should CCA control?** list above — uncheck it there to disable the time windows entirely.)*

### Further descriptions

<br />
<ins>Input fields for time control</ins><br /><br />
The times for opening and closing the cover are configured in the Time Control section below.
These time fields define the <strong>Early</strong> and <strong>Late</strong> boundaries — even when
using Brightness or Sun Elevation as the actual trigger. Early = earliest allowed trigger time;
Late = guaranteed fallback. See the
<a href="https://hvorragend.github.io/ha-blueprints/TIME_CONTROL_VISUALIZATION">Time Control Guide</a>
for a visual explanation.
<br /><br />
<ins>Calendar Control</ins><br />
You can use a Home Assistant calendar to define when covers should be open or closed.
Create calendar events with titles "Open Cover" (for daytime) or "Close Cover" (for evening).
The automation reacts immediately when events start or end.
<br /><br />
<ins>Disabling time control</ins><br />
Uncheck <strong>⏲️ Time Control</strong> in the <strong>👉 What should CCA control?</strong>
list to disable the time windows entirely — Brightness and Sun Elevation triggers may then
fire at any time of day.
<strong>Warning:</strong> without time windows there is no guaranteed <strong>Late</strong>
opening/closing safety net; the cover only moves when a sensor condition is actually met.

---

<a id="brightness_sun_operator"></a>

## 🔀 Condition Logic: Brightness & Sun Elevation

> 🧩 Input: `brightness_sun_operator` · Default: `or`

How should Brightness and Sun Elevation conditions be combined when **both** are active?

### OR vs. AND - Which to choose?

**⚡ OR** *(Default — recommended for most users)*
The cover opens/closes as soon as **either** condition is met.
Example: Opens when it gets bright enough *or* the sun rises above the threshold.
More responsive — reacts earlier on clear mornings.

**🔒 AND**
The cover opens/closes only when **both** conditions are met simultaneously.
Example: Opens only when it's bright enough *and* the sun is above the threshold.
More conservative — reduces false triggers on overcast mornings.

*Has no effect when only one of the two conditions is enabled.*

---

<a id="individual_config"></a>

## ⚙️ Behavior Customization

> 🧩 Input: `individual_config`

**Fine-tune automation behavior for your specific hardware and preferences.**

### What each category controls

This section lets you customize how CCA behaves in different scenarios:
- **Position Management**: Control cover movements between states (e.g., avoid raising when closing for the evening)
- **Feature Control**: Disable automatic transitions (e.g., stay shaded after sun disappears, don't open after ventilation ends)
- **Daily Frequency Limits**: Prevent repeated actions (e.g., open only once per day)
- **Hardware Compatibility**: Work around device-specific quirks with position/tilt commands

**Hardware-Specific Details**

<ins>Why use custom actions instead of default services?</ins><br />
Some devices (e.g., Shelly, Homematic) have issues when 'set_cover_position' and 'set_cover_tilt_position' are executed sequentially.

**Solutions:**
- Shelly: Use script [cover_position_tilt.yaml](https://gist.github.com/lukasvice/b364724d84c3ac4e160f7a7d8fa37066)
- Homematic: Use custom service [homematicip_local.set_cover_combined_position](https://github.com/SukramJ/custom_homematic?tab=readme-ov-file#homematicip_localset_cover_combined_position)
- Other devices: Implement via "Additional Actions" in the Service Calls section

---

<a id="enable_recovery"></a>

## 🔄 Catch up on what a restart or an outage swallowed

> 🧩 Input: `enable_recovery` · Default: `never`

While a required entity (the cover, the status helper, a position sensor, a window contact) has no usable state, CCA stops — it cannot decide anything without a position, and it must not lower a cover onto a window it can no longer see. The events of that period are then **lost**: a scheduled closing never fires again, a sun shading never starts that day. This setting decides whether CCA **catches those events up** once everything is usable again.

| Setting | After an outage of a device / integration | After a Home Assistant restart, a reload, or saving this automation |
|---|---|---|
| **🚫 Never** (default) | nothing is caught up | nothing is caught up |
| **🔌 Only after an outage** | caught up | **nothing is caught up** |
| **🔄 Always** | caught up | caught up |

**Why the distinction matters.** A Home Assistant restart and a Zigbee stick that dropped out for ten minutes over your closing time are not the same event. Most people who dislike "the covers move after a restart" are perfectly happy for CCA to fix a cover that was left open all night because a gateway hiccupped. **🔌 Only after an outage** is that middle ground.

*(How CCA tells them apart — and why the order in which your integrations load does not matter: a restart, a reload and a save all re-create the automation. Until every required entity is usable again, CCA is blocked and writes nothing, so it still knows it is inside a start-up when the last device finally reports — even if that takes half an hour. And a device that was already unreachable when Home Assistant started stays part of that start-up, however long it then takes to answer. A dropout that **began** while Home Assistant was running is an outage; one that began at boot is not.)*

### What "catching up" does

- A missed scheduled/calendar **opening or closing** is performed — but only if the **additional opening/closing condition** for that direction still allows it (see below). This includes the night: between midnight and the opening time, "closed" counts as the scheduled state (the previous evening continued) — a restart at 2 am after a swallowed evening closing closes the cover instead of opening it.
- The **sun-shading conditions** are re-evaluated: if shading is due now, it starts; if it is over, it ends.
- A **force function** switched on or off during the outage is applied.
- **Lockout, ventilation and privacy closing** are applied from the current window and presence state.

**This can move the cover.** A caught-up movement is a real one, so it also runs the **action you configured for it** (*"Action before/after closing"*, opening, ventilation, sun shading) — a closing that the outage swallowed is still a closing. Those actions only run when the cover actually changes position: if CCA finds everything already in place (the normal case), it stays silent.

A **manual override is respected** and blocks the movement — unless its reset has already come due in the meantime (then it is lifted and the cover follows the automation again), or the lockout protection applies (window fully open), which always takes precedence.

**Your additional conditions are respected.** A scheduled movement that your *additional opening/closing condition* (Conditions section) deliberately suppressed was never "missed", so it is not replayed: before a missed opening or closing is applied, the additional condition for that direction is evaluated. If it says no, CCA keeps the status it had. The *global condition* is respected as well (it drops the whole run). *(Up to `2026.07.13 V6` this was a known limitation — the catch-up derived the movement from the schedule alone and could open a cover your condition had blocked all morning.)*

**⚠️ Saving the automation counts as a restart.** When you change a setting and save, Home Assistant re-creates the automation — for CCA that is the same event as switching it off and on again. With **🔄 Always**, CCA therefore recalculates right after you save, and **the cover may move**. With **🔌 Only after an outage** it does not — that is one of the reasons to prefer the middle setting.

With **🚫 Never**, the cover is never moved because of a restart or an outage. The trade-off is that events which fell into that period stay lost — a closing scheduled during the downtime simply does not happen, and sun-shading changes are not replayed. The automation resumes with the next regular trigger.

### What still happens when nothing is caught up

The setting decides whether CCA may **move** the cover. It does not switch off the protections that keep CCA from moving it *wrongly* — those are always active:

- CCA **pauses** while the cover, the status helper, or the configured position sensor has no usable state (nothing can be decided without a position), and window contacts / the resident sensor fall back to their last known value while a battery sensor is silent.
- CCA **cleans up its status helper** whenever it comes back — after a restart, after being switched off and on again, after you save the automation, **and after a cover, a status helper or a window contact returns from an outage** (none of which anything else reports). A sun shading left over from an earlier day, a waiting period that can no longer run, and an override reset that came due in the meantime are cleared, and the force/resident/window status is re-read from the live entities.
- CCA **re-reads a force function** when its own entity comes back after an outage. While that entity has no status, CCA keeps the force function running (it must not cancel it by accident), so afterwards it has to check whether the function was switched off in the meantime — otherwise the cover would stay in the force position forever. The **force pause** is not part of this: bringing the cover back into a force function that the pause had suspended is a *movement*, so that one does need a catch-up setting.
- CCA **records a manual movement** you make right after a restart or a save, instead of recalculating over it. The recalculation then respects the override like any other.

That clean-up moves nothing. It exists because an outdated status is not a "missed event" — it is a status that would make CCA move the cover wrongly on the *next* regular trigger. Without it, a sun shading from days ago would still count as active and could drive the cover into the shading position at night, a manual override whose reset fell into the downtime would never be lifted at all, and a force function whose switch dropped out and came back *off* would stay recorded forever.

You will therefore still see a CCA run (and a trace) shortly after a restart, shortly after you save the automation, and shortly after a device comes back — even with **🚫 Never**. It updates the status helper and stops; it does not drive the cover. The run waits until the cover (and, where configured, the position sensor and a window contact whose window was last known open) is actually usable again — after a restart where the cover takes a few minutes to come back, the clean-up simply follows a minute after the cover does.

<a id="instance_active"></a>

## 🎚️ Only run this automation while this switch is on

> 🧩 Input: `instance_active` · Default: *(empty — feature off)*

This is what lets you run **several CCA automations for the same cover**, each with its own status helper and its own complete set of settings. One for summer and one for winter. One for when you are at home and one for when you are away. A "holiday" one you switch on for two weeks a year.

Give each automation its own switch — an **`input_boolean`** helper is the natural choice — and select it here. While that switch is off, the automation **does nothing at all** for this cover: no opening, no closing, no shading, no lockout, and it does not react to the cover being moved by anything else either. It is, for that period, not there.

**You are responsible for making sure only one of them is ever on.** CCA does not coordinate the switches; a small automation of your own does (a "summer/winter" `input_select`, a presence trigger, a calendar — whatever fits). If two are on at once they will fight over the cover.

### Handing the cover over

Switching an instance **on** is an explicit *"you are in charge now"*, and it acts like one. The incoming automation re-reads everything from scratch — the window contacts, presence, the force switches, the weather, its own schedule and its own shading settings — and brings the cover to where **its** settings say it belongs. Whatever the previous instance left behind is irrelevant; nothing is inherited.

Because of that, the take-over **moves the cover regardless of the 🔄 catch-up setting above**. That setting exists to stop covers moving after a *restart*; a hand-over is not a restart, and an instance that takes charge and then leaves the cover where the previous one parked it has done nothing at all.

A **manual override** that this instance still had stored from the last time it was in charge is discarded on the take-over. It belonged to the previous shift — and while the instance was off it could not even see the cover being moved, so there is nothing left for it to protect.

### One dropdown instead of many switches

> 🧩 Input: `instance_active_value` · Default: *(empty — plain on/off switch)*

The second input, **"... and it counts as on while it shows this value"**, removes the switching automation entirely for most setups. Fill in a value, and the automation is in charge exactly **while the entity above shows that value**.

- **A dropdown as the selector.** Create one *Dropdown* helper (`input_select`) with one option per automation — say *Summer / Winter / Holiday*. Point every CCA automation at that same dropdown and write its own option into this field. A dropdown always shows exactly one value, so **exactly one automation is in charge — guaranteed, by construction**. Change the option (by hand, or from any automation) and the matching CCA automation takes the cover over.
- **Two automations, one switch.** Write `on` into one automation and `off` into the other, and point both at the same `input_boolean`. One of them is always in charge — never both, never neither.

The value must match the entity's state **exactly** (for a dropdown: the option text, including case). Leave it empty for the normal on/off behavior described above.

### The one rule for your switching automation

**Do not move the cover yourself when switching over.** Just flip the switches and let the incoming automation position the cover.

If your switching automation drives the cover first (say, "when everyone leaves, close the covers, then switch to the away instance"), the incoming instance sees that movement as a **manual override** and politely leaves the cover alone — which is the opposite of what you wanted. Let it do the closing: put the closed position in the away instance's settings instead.

### ⚠️ Every automation needs its **own** status helper

Nothing stops you from pointing two CCA automations at the same *status helper*, and it will even appear to work for a while. **Don't.** Give each automation its own.

The reason is what the status helper actually contains. It holds almost nothing about the *cover* — the window state, presence and the force switches are read live from their entities every time, which is why a hand-over picks them up without a gap. What the helper uniquely stores is **one automation's reading of the situation, under that automation's settings**:

- *"the schedule says open"* — but the summer automation's schedule is not the winter one's.
- *"sun shading is active"* — the winter automation may not even have shading switched on.
- *"a sun-shading waiting period is running"* — started with *that* automation's waiting time and thresholds.
- *"someone overrode me by hand"* — overrode **whom**?
- *"I already opened / closed / shaded today"* — the counters behind the *only once per day* options.

Share the helper and those readings get mixed together: the incoming automation inherits a shading it has no concept of, or a waiting period that was armed under settings it does not have. It also becomes impossible to tell from the helper which automation put the cover where — and that helper is your main tool when something goes wrong.

There is exactly one thing a shared helper would buy you: the *only once per day* counters would then be shared too (see below). If you need that, use a separate `input_boolean` ("already shaded today") in the *additional shading condition* instead — it costs one helper and breaks nothing.

### Not the same as the ⏸️ Force Pause

Both switches stop the cover from moving, and they look interchangeable. They are opposites.

| | ⏸️ **Force Pause** | 🎚️ **`instance_active` (off)** |
|---|---|---|
| The automation keeps running | **yes** — it just does not move the cover | **no** — it does nothing at all |
| The status helper keeps being updated | **yes**, continuously | **no** — it freezes at the last value |
| When it is lifted | drives back to the state it tracked all along — **instant, because it never lost track** | recalculates **everything from scratch**, because it does not know what happened |
| What it means | *"do not move this cover right now"* | *"this automation is not in charge right now — another one is"* |

Use the **Force Pause** when the cover must stay put for a while (someone is cleaning the windows, the terrace door is blocked, a baby is asleep). Use **`instance_active`** when a *different CCA automation* is running the cover.

**Do not try to use the Force Pause for the multi-automation setup.** A paused automation still watches — and it cannot tell the *other* automation's movements apart from you grabbing the slider. It records them as a **manual override** and, once you un-pause it, refuses to touch the cover. `instance_active` switches the automation off entirely, which is exactly what stops that from happening.

### 💡 Bonus: a "re-sync now" switch — even with just one automation

You do not need a second CCA automation to benefit from this input. Point it at an `input_boolean` that is simply **always on**, and you have a re-sync button: whenever you want CCA to *forget everything and start fresh* — after you have been playing with the cover by hand, after re-arranging your settings, after anything that left the cover somewhere it should not be — flip that switch **off and back on**.

Switching on is a full take-over, and it does not care what came before: it re-reads the window contacts, presence, the force switches, the weather and the schedule, **discards a stored manual override**, and drives the cover to where the settings say it belongs — immediately, and regardless of the 🔄 catch-up setting. It is the clean answer to *"just put it back the way it should be, now."*

(Toggling the whole **automation** off and on gets you something similar, but slower and weaker: the clean-up run starts about a minute later, respects the catch-up setting — so with 🚫 *Never* it tidies the status but does not move the cover — and it keeps a manual override in place. The switch is the stronger tool, because switching it on *means* "take the cover over".)

### Things worth knowing

- **The "only once per day" options are per automation.** Each instance has its own status helper, so *Open / Close / Shade cover only once per day* count that instance's own movements. Hand over at noon and the incoming instance may open, close or shade once more that day.
- **A calendar can be the switch.** Select a calendar entity above and the automation is in charge **while a calendar event is running** — a "holiday" instance driven by your vacation calendar needs no switching automation at all: it takes over when the event starts and hands back when it ends. **Any event counts; event titles play no role here** — this is not the ⏲️ calendar *time control*, which reads "Open Cover"/"Close Cover" titles to schedule movements. Use a dedicated calendar, not the one your time control reads.
- **Force functions and window contacts are shared.** They are read live from the entities, so the incoming instance picks up a force function that is already running, and the lockout protection works across a hand-over without a gap.
- **A movement the outgoing instance had already planned is cancelled.** If the previous instance was still waiting out a drive delay when the switch flipped, that pending movement is stopped at the last moment — the outgoing automation cannot move the cover after the hand-over.
- **If the switch itself becomes unavailable**, the automation stops rather than guess — it cannot tell whether it owns the cover, and another instance might. It resumes by itself when the switch comes back.
- **If you delete or disable the switch**, the automation stops and says so in the log. It is a configuration error, not an outage: nothing would ever bring it back.
- Leave this input **empty** if you only run one CCA automation for this cover. Nothing changes then.

---

[⬅️ Handbook index](index) · Previous: [🧱 Basics: Cover & Status Helper](basics) · Next: [📐 Positions](positions)

{% endraw %}
