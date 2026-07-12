{% raw %}
# ⏰ Time & Calendar Control

> Part of the [CCA Handbook](index). These options live in the **Time Control Configuration** section of the blueprint.

Configure the time windows for morning opening and evening closing.<br />
  Time control can be enabled and the type selected in the <strong>Automation Options</strong> section above.
  <br />
  For comprehensive explanations, examples, and timing diagrams, see:
  <a href="https://hvorragend.github.io/ha-blueprints/TIME_CONTROL_VISUALIZATION">Time Control Guide</a>

<a id="time_up_early"></a>

## 🔼 Time For Drive Up - Early On Workdays

*Blueprint input: `time_up_early`* *(default: `06:00:00`)*

The earliest time at which the cover may be opened. The cover will be opened if <ins>AFTER</ins> this time the defined brightness or sun-elevation value is high enough. (**NOTE**: A resident must also be awake if one is defined).

<a id="time_up_early_non_workday"></a>

## 🔼 Time For Drive Up - Early On Non-Workdays

*Blueprint input: `time_up_early_non_workday`* *(default: `07:00:00`)*

As directly above, but for non-workdays.

<a id="time_up_late"></a>

## 🔼 Time For Drive Up - Late On Workdays

*Blueprint input: `time_up_late`* *(default: `08:00:00`)*

The latest time at which the cover should be opened. If the required brightness or sun-elevation value has <ins>NOT</ins> yet been reached by this time, the cover will still be opened. (**NOTE**: If a resident has been defined and the resident is still asleep, then the cover will NOT be opened.)

<a id="time_up_late_non_workday"></a>

## 🔼 Time For Drive Up - Late On Non-Workdays

*Blueprint input: `time_up_late_non_workday`* *(default: `08:00:00`)*

As directly above, but for non-workdays.

<a id="time_down_early"></a>

## 🔻 Time For Drive Down - Early On Workdays

*Blueprint input: `time_down_early`* *(default: `16:00:00`)*

The earliest time at which the cover may be closed. The cover will be closed if <ins>AFTER</ins> this time the defined brightness or sun-elevation value is low enough.

<a id="time_down_early_non_workday"></a>

## 🔻 Time For Drive Down - Early On Non-Workdays

*Blueprint input: `time_down_early_non_workday`* *(default: `16:00:00`)*

As directly above, but for non-workdays.

<a id="time_down_late"></a>

## 🔻 Time For Drive Down - Late On Workdays

*Blueprint input: `time_down_late`* *(default: `22:00:00`)*

The latest time at which the cover should be closed. If the required brightness or sun-elevation value has <ins>NOT</ins> yet been reached by this time, the cover will still be closed. <br /> Please do not enter 0:00, because that would be the next day!

<a id="time_down_late_non_workday"></a>

## 🔻 Time For Drive Down - Late On Non-Workdays

*Blueprint input: `time_down_late_non_workday`* *(default: `22:00:00`)*

As directly above, but for non-workdays. <br /> Please do not enter 0:00, because that would be the next day!

<a id="workday_sensor"></a>

## 💼 Sensor For Workday Today

*Blueprint input: `workday_sensor`*

It may be desired to open a cover at a different time on work days than on non-work days. The corresponding binary sensor can be defined here. If not set, the cover will open every time at time_up_early. <br /><br /> I recommend using the [Workday integration](https://www.home-assistant.io/integrations/workday/). <br /><br /> Example: `binary_sensor.workday_today` <br /><br />`Optional`

<a id="workday_sensor_tomorrow"></a>

## 💼 Sensor For Workday Tomorrow (only for closing)

*Blueprint input: `workday_sensor_tomorrow`*

When <ins>closing</ins> the blinds, you have the option of checking the times for tomorrow rather than the current day. This has the advantage that you can <ins>close</ins> the blinds earlier if <ins>tomorrow</ins> is a working day. This makes sense if, for example, there is school tomorrow but today is actually still the weekend. But the child has to go to bed earlier.<br /> If this field is not configured here, the normal working day sensor is used. <br /><br /> I recommend using the [Workday integration](https://www.home-assistant.io/integrations/workday/). <br /><br /> Example: `binary_sensor.workday_tomorrow` <br /><br />`Optional`

<a id="calendar_entity"></a>

## 📅 Calendar Entity

*Blueprint input: `calendar_entity`*

Select a Home Assistant calendar for time control.

### How to use calendar control

**Event Titles (exact match, case-insensitive):**
  - **"Open Cover"** - Marks the daytime window (cover should be open)
  - **"Close Cover"** - Marks the evening window (cover should be closed)
  - The event title must match the configured title exactly (ignoring
    upper/lower case and surrounding spaces). "Open Cover Bedroom" does
    **not** match the title "Open Cover" - so several covers can share
    one calendar with different event titles.

**How it works:**
  - When an "Open Cover" event starts, the automation treats it like morning time
  - When a "Close Cover" event starts, the automation treats it like evening time
  - Events can span multiple days
  - Multiple events per day are supported

**Example schedule:**
  - Monday to Friday: "Open Cover" from 06:00-20:00
  - Saturday/Sunday: "Open Cover" from 08:00-22:00
  - Automatically handles weekday/weekend differences

**Advantages over time input:**
  - No need for separate workday/non-workday times
  - Can define different times for each day
  - Can create exceptions (holidays, vacations)
  - Changes take effect immediately without automation reload

<a id="calendar_open_title"></a>

## 📂 Open Event Title

*Blueprint input: `calendar_open_title`* *(default: `Open Cover`)*

Title of calendar events that define the daytime window (case-insensitive match). Default: "Open Cover".

<a id="calendar_close_title"></a>

## 📁 Close Event Title

*Blueprint input: `calendar_close_title`* *(default: `Close Cover`)*

Title of calendar events that define the evening/close window (case-insensitive match). Default: "Close Cover".

{% endraw %}
