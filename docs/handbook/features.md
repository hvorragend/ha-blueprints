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

---

[⬅️ Handbook index](index) · Previous: [🧱 Basics: Cover & Status Helper](basics) · Next: [📐 Positions](positions)

{% endraw %}
