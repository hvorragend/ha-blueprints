{% raw %}
# 📐 Positions

> Part of the [CCA Handbook](index). These options live in the **Cover Position Settings** section of the blueprint.

<strong>Important notes on configuring the position values</strong>
  <br />
  Please ensure that all position values are unique and do not conflict with each other.
  <br />
  <strong>Position Logic:</strong><br />
  - For Blinds/Shutters: open_position (100%) > shading_position (25%) > close_position (0%)<br />
  - For Awnings: open_position (0%) < shading_position (75%) < close_position (100%)

<a id="position_source"></a>

## 📍 Position Source Type

*Blueprint input: `position_source`* *(default: `current_position_attr`)*

How does your cover provide position information? 

### When to use each option

- **current_position attribute** (Standard): Most covers use this. If CCA detects positions correctly, keep this setting.
  - **position attribute**: Select this if your cover entity has a 'position' attribute but no 'current_position' attribute. Check in Developer Tools → States if unsure.
  - **Custom sensor**:   Use this if: Your cover doesn't report positions at all / You have an external sensor tracking the cover position / Manual position changes aren't detected with the other options

<a id="custom_position_sensor"></a>

## 📍 Custom Position Sensor

*Blueprint input: `custom_position_sensor`*

Select sensor that provides position (0-100%). Only used if 'Custom sensor' selected above

<a id="cover_type"></a>

## 🎯 Cover Type

*Blueprint input: `cover_type`* *(default: `blind`)*

Select the type of cover you want to control. <br /><br /> <strong>Blind/Roller Shutter:</strong> Position 0% = closed (down), 100% = open (up). Shading uses lower positions. <br /><br /> <strong>Awning/Sunshade:</strong> Position 0% = retracted (closed), 100% = extended (open). Shading uses higher positions. <br /><br /> ⚠️ <strong>Note:</strong> Ventilation and tilt features are not available for awnings.

### Position value examples

<strong>For Blinds/Shutters:</strong><br /> - Open Position: 100% (fully up)<br /> - Shading Position: 25% (partially down for sun protection)<br /> - Ventilate Position: 30% (slightly down for air flow)<br /> - Close Position: 0% (fully down)<br /> <br /> <strong>For Awnings:</strong><br /> - Open Position: 0% (retracted/closed)<br /> - Shading Position: 75% (extended for sun protection)<br /> - Close Position: 100% (fully extended)<br /> <br /> <em>Note: Ventilate Position is not used for awnings.</em>

<a id="open_position"></a>

## 🔼 Open Position

*Blueprint input: `open_position`* *(default: `100`)*

What position should the cover be moved into when opening?

<a id="close_position"></a>

## 🔻 Close Position

*Blueprint input: `close_position`* *(default: `0`)*

What position should the cover be moved into when closing?

<a id="ventilate_position"></a>

## 💨 Ventilate Position

*Blueprint input: `ventilate_position`* *(default: `30`)*

What position should the cover move to when the window is tilted? If closing is triggered and the contact sensor is 'on', the cover will move to this position instead of closing completely. <br /><br />Should not be 100. In this case please use 99. And please also note the information in the position tolerance.

<a id="shading_position"></a>

## 🥵 Sun Shading Position

*Blueprint input: `shading_position`* *(default: `25`)*

To which position should the cover be moved for shading?

<a id="shading_position_alt"></a>

## 🥵 Alternate Sun Shading Position

*Blueprint input: `shading_position_alt`*

An optional second shading position. When the gating entity below is 'on', the cover moves to this position for shading instead of the normal shading position. <br /><br />Leave empty to disable the alternate shading position.

<a id="shading_position_alt_entity"></a>

## 🥵 Alternate Sun Shading Position Trigger

*Blueprint input: `shading_position_alt_entity`*

While this entity is 'on', the cover shades to the alternate shading position above instead of the normal shading position. While it is 'off' (or unset), the normal shading position is used. If the cover is already shading when this entity changes, the cover is re-driven to the matching position. <br /><br />Leave empty to disable the alternate shading position.

<a id="position_tolerance"></a>

## 〰️ Position Tolerance

*Blueprint input: `position_tolerance`* *(default: `0`)*

Tolerance to be applied when comparing the current position with the to be position. These are absolute values. Not relative to the previous position values.

<a id="drive_time"></a>

## ⏲️ Cover Drive Time

*Blueprint input: `drive_time`* *(default: `90`)*

Can be used to recognise manual control. Please round up a little and do not adjust too precisely. Is used to delay the trigger if too much or incorrect position data is sent back. <br /><br /> Within this time, it is assumed that CCA has carried out the last action. Otherwise, CCA would react to its own commands and recognize them as manual intervention.

{% endraw %}
