{% raw %}
# 🚪 Window Contacts & Ventilation

> Part of the [CCA Handbook](index). These options live in the **Contact Sensors for Ventilation** section of the blueprint.

Settings if the feature ‘💨 - Ventilation Mode — React to open/tilted windows, prevent lockout’ has been activated above.
  <br />
  All these settings are optional.

<a id="contact_window_opened"></a>

## 🚪 Contact Sensor For Open Window (Full Ventilation)

*Blueprint input: `contact_window_opened`*

Contact sensor of a door or window handle for detecting <ins>total opening</ins>. If this sensor switches to on/true, the cover is <ins>fully opened</ins>. At the same time, a lockout protection is <ins>always</ins> activated. The cover is not closed and the sun shading is not activated when the contact is open.

### Further descriptions

It must be a binary two-way contact sensor.
If a three-way sensor is available, it must be converted to a binary two-way sensor using a [template sensor](https://www.home-assistant.io/integrations/template/).
See also the [following posts](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539/593) in the forum.

<strong>Important note:</strong> Please do not enter the same sensor in both fields for the contact sensors. This does not work and leads to strange situations.

<strong>If the sensor has no status</strong> — typical for a battery-powered contact after a restart of your hub, which only reports again when the window is next moved — the automation continues with the <ins>last known</ins> window status. It deliberately does not treat the window as closed, because that could lower the cover onto an open window. So while the last known status was <ins>open or tilted</ins>, the automation waits and the cover holds its position; everything resumes as soon as the sensor reports again.

<a id="contact_window_tilted"></a>

## 💨 Contact Sensor For Tilted Window (Partial Ventilation)

*Blueprint input: `contact_window_tilted`*

The contact sensor is required for the <ins>partial</ins> ventilation mode. If the contact changes to on/true, the cover is moved to the <ins>ventilation</ins> position. The prerequisite is that the cover is already closed. After the status changes to off/false, the close position is activated again. The same applies in the shading-out situation.

### Further descriptions

It must be a binary two-way contact sensor.
If a three-way sensor is available, it must be converted to a binary two-way sensor using a [template sensor](https://www.home-assistant.io/integrations/template/).
See also the [following posts](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539/593) in the forum.

<strong>Important note:</strong> Please do not enter the same sensor in both fields for the contact sensors. This does not work and leads to strange situations.

<strong>If the sensor has no status</strong> — typical for a battery-powered contact after a restart of your hub, which only reports again when the window is next moved — the automation continues with the <ins>last known</ins> window status. It deliberately does not treat the window as closed, because that could lower the cover onto an open window. So while the last known status was <ins>open or tilted</ins>, the automation waits and the cover holds its position; everything resumes as soon as the sensor reports again.

<a id="lockout_tilted_options"></a>

## 💨 Lockout protection for window tilted

*Blueprint input: `lockout_tilted_options`*

For the tilted window (or door, of course), you can individually specify where a lockout protection should be used.

<a id="auto_ventilate_options"></a>

## 💨 Ventilation Configuration

*Blueprint input: `auto_ventilate_options`*

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

<a id="contact_delay_trigger"></a>

## 🕛 Contact Trigger Delay

*Blueprint input: `contact_delay_trigger`* *(default: `2`)*

How many seconds must the status of the contact sensors be valid for the automation to trigger?
⚠️ **Race Condition Protection:** If you have multiple contact sensors (e.g., window sensor + lock sensor) that can change simultaneously, increase this value to prevent race conditions.
**Symptoms of race conditions:** - Cover closes despite lockout sensor being active - Check Home Assistant logs for "max_exceeded: warning" messages - If you see these warnings frequently, increase this delay

<a id="contact_delay_status"></a>

## 🕛 Contact Sensor Status Delay

*Blueprint input: `contact_delay_status`* *(default: `3`)*

How long should the automation wait after a contact sensor trigger before re-evaluating all sensor states?
This delay is applied inside the contact sensor handling. After the delay, CCA reads the **live state** of all contact sensors — so the final decision (return to open / close / shading) reflects the actual situation at that moment, not the state at trigger time.

**When to increase this value:**
- Your window/door sensor briefly shows an intermediate state when changing
- You switch the window contact and the resident sensor off in quick
  succession — with a delay of 0.5–1 s, CCA will see the resident as
  already gone and return to open instead of close

**⚠️ Race Condition: Window closed + Resident off in quick succession:**
If `contact_window_opened` and the resident sensor are turned off within milliseconds of each other, CCA may still see the resident as present at trigger time and incorrectly close the cover. Setting this delay to **0.5–1 second** gives the resident sensor enough time to settle before CCA makes its routing decision.

{% endraw %}
