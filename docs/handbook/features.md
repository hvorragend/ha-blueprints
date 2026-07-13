{% raw %}
# ⚙️ Features & Modes

[📖 CCA Handbook](index) › Blueprint section: **Automation Options**

Configure what CCA controls and how it behaves. Most settings use safe defaults. Expand the descriptions below only if you need details.

**On this page:** [👉 What should CCA control?](#auto_options) · [⏲️ Time Control Type](#time_control) · [🔀 Condition Logic: Brightness & Sun Elevation](#brightness_sun_operator) · [⚙️ Behavior Customization](#individual_config) · [🔄 Recovery after a restart or an outage](#enable_recovery)

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

## 🔄 Recovery after a restart or an outage

> 🧩 Input: `enable_recovery` · Default: `false`

When enabled, CCA recalculates its target state after a Home Assistant restart — and whenever a required source (the cover, the status helper, a position sensor, a window contact, …) becomes usable again after an outage. It then catches up on everything that was missed in the meantime:

- A missed scheduled/calendar **opening or closing** is performed.
- The **sun-shading conditions** are re-evaluated: if shading is due now, it starts; if it is over, it ends.
- A **force function** switched on or off during the outage is applied.
- A **manual-override reset** whose moment fell into the outage is caught up.

**This can move the cover right after a restart** — for example, a shading intent stored before the restart is applied, or a missed morning opening is caught up. A manual override always survives the recovery; only the lockout protection (window fully open) takes precedence.

When **disabled** (default), no recovery run is triggered at all: the cover is never touched after a restart. The trade-off is that events which fell into the restart or outage stay lost — a closing scheduled during a restart simply does not happen, and sun-shading changes that occurred during the outage are not replayed. The automation resumes with the next regular trigger.

**Independent of this switch**, CCA always pauses while the cover, the status helper, or the configured position sensor has no usable state (nothing can be decided without a position), and window contacts / the resident sensor fall back to their last known value while a battery sensor is silent. That protection only *prevents* wrong movements — it never causes any.

---

[⬅️ Handbook index](index) · Previous: [🧱 Basics: Cover & Status Helper](basics) · Next: [📐 Positions](positions)

{% endraw %}
