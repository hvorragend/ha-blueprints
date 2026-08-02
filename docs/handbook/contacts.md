{% raw %}
# 🚪 Window Contacts & Ventilation

[📖 CCA Handbook](index) › Blueprint section: **Contact Sensors for Ventilation**

Settings if the feature ‘💨 - Ventilation Mode — React to open/tilted windows, prevent lockout’ has been activated above.
  <br />
  All these settings are optional.

**On this page:** [🚪 Contact Sensor For Open Window (Full Ventilation)](#contact_window_opened) · [💨 Contact Sensor For Tilted Window (Partial Ventilation)](#contact_window_tilted) · [💨 Lockout protection for window tilted](#lockout_tilted_options) · [💨 Ventilation Configuration](#auto_ventilate_options) · [🕛 Contact Trigger Delay](#contact_delay_trigger) · [🕛 Contact Sensor Status Delay](#contact_delay_status)

---

<a id="contact_window_opened"></a>

## 🚪 Contact Sensor For Open Window (Full Ventilation)

> 🧩 Input: `contact_window_opened`

Contact sensor of a door or window handle for detecting <ins>total opening</ins>. If this sensor switches to on/true and the [Additional Ventilation Condition](conditions#auto_ventilate_condition) permits the movement, the cover is <ins>fully opened</ins> — to the Open Position, or to the [💨 Full Ventilation Position](positions#lockout_position) if configured. Independently of that proactive movement, lockout protection is <ins>always</ins> activated: CCA records the open window and does not later close or sun-shade the cover while the contact remains open.

### Further descriptions

It must be a binary two-way contact sensor.
If a three-way sensor is available, it must be converted to a binary two-way sensor using a [template sensor](https://www.home-assistant.io/integrations/template/).
See also the [following posts](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539/593) in the forum.

<strong>Important note:</strong> Please do not enter the same sensor in both fields for the contact sensors. This does not work and leads to strange situations.

<strong>If the sensor has no status</strong> — typical for a battery-powered contact after a restart of your hub, which only reports again when the window is next moved — the automation continues with the <ins>last known</ins> window status. It deliberately does not treat the window as closed, because that could lower the cover onto an open window. So while the last known status was <ins>open or tilted</ins>, the automation waits and the cover holds its position; everything resumes as soon as the sensor reports again.

---

<a id="contact_window_tilted"></a>

## 💨 Contact Sensor For Tilted Window (Partial Ventilation)

> 🧩 Input: `contact_window_tilted`

The contact sensor is required for the <ins>partial</ins> ventilation mode. If the contact changes to on/true, the cover is moved to the <ins>ventilation</ins> position. The prerequisite is that the cover is already closed. After the status changes to off/false, the close position is activated again. The same applies in the shading-out situation.

### Further descriptions

It must be a binary two-way contact sensor.
If a three-way sensor is available, it must be converted to a binary two-way sensor using a [template sensor](https://www.home-assistant.io/integrations/template/).
See also the [following posts](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539/593) in the forum.

<strong>Important note:</strong> Please do not enter the same sensor in both fields for the contact sensors. This does not work and leads to strange situations.

<strong>If the sensor has no status</strong> — typical for a battery-powered contact after a restart of your hub, which only reports again when the window is next moved — the automation continues with the <ins>last known</ins> window status. It deliberately does not treat the window as closed, because that could lower the cover onto an open window. So while the last known status was <ins>open or tilted</ins>, the automation waits and the cover holds its position; everything resumes as soon as the sensor reports again.

---

<a id="lockout_tilted_options"></a>

## 💨 Lockout protection for window tilted

> 🧩 Input: `lockout_tilted_options`

For the tilted window (or door, of course), you can individually specify where a lockout protection should be used.

---

<a id="auto_ventilate_options"></a>

## 💨 Ventilation Configuration

> 🧩 Input: `auto_ventilate_options`

Various different ventilation options.

### Further descriptions

- <ins>Disables the drive delay when ventilation starts (window opens/tilts):</ins>
  <br />
  By default, the "Fixed Drive Delay" and "Random Drive Delay" are applied to all cover movements — including ventilation start.
  If you use a large fixed delay to stagger many covers (e.g. for Somfy RF queue limits), this can feel sluggish when only one or two covers need to react to a window opening.
  <br />
  Enable this option to skip the drive delay when a window opens or tilts. The delay still applies to all other movements (open, close, shading).
  <br /><br />
- <ins>Enables a calculated delay after the window is closed:</ins>
  <br />
  Normally, when the window contact is closed, there is no delay in the upcoming drives. If you do want this, you can activate it here.
  <br /><br />
  The "Fixed Drive Delay" and "Random Drive Delay" settings which are already used everywhere are then used.
  <br /><br />
- <ins>Lower cover to the ventilation position when the window tilts and cover is above:</ins>
  <br />
  When the window is tilted and the cover is currently above the ventilation position, drive it <strong>down</strong> to the ventilation position.
  Without this option, the cover stays where it is in that case.
  <br />
  Note: This option takes effect for any cover position above the ventilation position. The dedicated full → tilt transition has its own opt-out below.
  <br /><br />
- <ins>Using the ventilation position when the sun shade is ended:</ins>
  <br />
  The cover can also be moved to the ventilation position when the sun protection/sun shading is ended.
  Normally, the cover would be fully opened when the shading is ended.
  <br />
  To be honest, it makes no sense to switch to the ventilation position during the day if more air can flow in when the cover is open.
  <br /><br />
- <ins>Keep cover at open position when window goes from fully opened to tilted:</ins>
  <br />
  When the window was previously fully opened (cover at the open position) and is then tilted, the cover would normally
  be lowered to the partial ventilation position. Enable this option to keep the cover at the open position in that case.
  <br />
  Useful e.g. for a terrace door: after coming back inside and tilting the door, the cover stays up instead of moving down.
  <br /><br />
- <ins>Sun shading is more important than ventilation: shade even while the window is tilted:</ins>
  <br />
  Normally a tilted window outranks the sun shading: the cover stops at the ventilation position instead of moving down to the shading position, so the tilted window keeps its air gap.
  With the standard positions (ventilation just above shading) the difference is a few percent and hardly noticeable.
  <br />
  It becomes a problem when your ventilation position sits <ins>far</ins> above the shading position — the classic case is a terrace door, where "ventilate" means driving the cover up so the door stays usable. On a window like that, a door left tilted through a summer day switches the sun shading off entirely, even though the automation still considers the shading active.
  <br />
  Enable this option to reverse that one decision: while sun shading is active, the cover moves to (and stays at) the shading position even when the window is tilted. Everything else keeps the ventilation position — a <ins>fully opened</ins> window still triggers the lockout protection, and closing time, presence-based closing and the end of the shading are unaffected.
  <br />
  <br />
  <ins>Why the default is the other way round:</ins> on a genuinely hot day the right move is to keep the windows <ins>shut</ins> — closed window plus shading beats anything else, and that is also why a cover parked at the ventilation position rarely bothered anyone. The case this option is for is the one where the tilted window is no longer a decision you can revise: you left the house with the window on tilt and the day turns out warmer than announced. Then keeping the sun out is what is left, and it still helps a lot — even with the window open, a shaded room heats up far more slowly than one the sun shines into.
  <br />
  A roller shutter in the shading position does not seal a tilted window; it only reduces the airflow. Whether that trade is right depends on the room: for a south-facing living room in summer it usually is, for a bathroom it usually is not.

---

<a id="contact_delay_trigger"></a>

## 🕛 Contact Trigger Delay

> 🧩 Input: `contact_delay_trigger` · Default: `2`

How many seconds must the status of the contact sensors be valid for the automation to trigger?
⚠️ **Race Condition Protection:** If you have multiple contact sensors (e.g., window sensor + lock sensor) that can change simultaneously, increase this value to prevent race conditions.
**Symptoms of race conditions:** - Cover closes despite lockout sensor being active - Check Home Assistant logs for "max_exceeded: warning" messages - If you see these warnings frequently, increase this delay

---

<a id="contact_delay_status"></a>

## 🕛 Contact Sensor Status Delay

> 🧩 Input: `contact_delay_status` · Default: `3`

How long should the automation wait after a contact sensor trigger before re-evaluating all sensor states?
This delay is applied inside the contact sensor handling. After the delay, CCA reads the **live state** of all contact sensors — so the final decision (return to open / close / shading) reflects the actual situation at that moment, not the state at trigger time.

**When to increase this value:**
- Your window/door sensor briefly shows an intermediate state when changing
- You switch the window contact and the resident sensor off in quick
  succession — with a delay of 0.5–1 s, CCA will see the resident as
  already gone and return to open instead of close

**⚠️ Race Condition: Window closed + Resident off in quick succession:**
If `contact_window_opened` and the resident sensor are turned off within milliseconds of each other, CCA may still see the resident as present at trigger time and incorrectly close the cover. Setting this delay to **0.5–1 second** gives the resident sensor enough time to settle before CCA makes its routing decision.

---

[⬅️ Handbook index](index) · Previous: [☀️ Sun Elevation](sun) · Next: [🌤️ Sun Shading](shading)

{% endraw %}
