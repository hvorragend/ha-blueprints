{% raw %}
# 🪟 Tilt Positions (Venetian Blinds)

> Part of the [CCA Handbook](index). These options live in the **Cover Tilt Position Settings** section of the blueprint.

<a id="cover_tilt_wait_mode"></a>

## 🔄 Tilt Wait Mode

*Blueprint input: `cover_tilt_wait_mode`* *(default: `fixed_delay`)*

Choose how CCA waits before sending tilt commands:
**Fixed Delay (Standard)**: Uses the configured tilt delay value. Works well for most devices.
**Wait Until Idle (Z-Wave)**: Waits until cover reports 'open' or 'closed' state before sending tilt. Prevents tilt commands from being ignored on devices that block tilt during motor movement (e.g., Shelly Qubino Wave Shutter).
If your tilt positions are unreliable, try switching to 'Wait Until Idle' mode.

<a id="cover_tilt_wait_timeout"></a>

## 🔄 Tilt Wait Timeout

*Blueprint input: `cover_tilt_wait_timeout`* *(default: `30`)*

Maximum time to wait for cover to become idle before sending tilt command. Only used when 'Wait Until Idle' mode is selected.

<a id="tilt_delay"></a>

## 🕛 Default Tilt Delay

*Blueprint input: `tilt_delay`* *(default: `0`)*

Delay between <em>set_cover_position</em> and <em>set_cover_tilt_position</em>. Only necessary when using the tilt functions. This separates the two commands in terms of time. <br /><br />`Optional`

<a id="cover_tilt_config"></a>

## 📐 Tilt Position Feature

*Blueprint input: `cover_tilt_config`* *(default: `cover_tilt_disabled`)*

⚠️ <strong>Note:</strong> Tilt control is only available for blinds/shutters, not for awnings. <br /><br /> If the cover and the integration support it, the tilt position of the cover can be set. The standard attribute ‘current_tilt_position’ is used for this.

<a id="cover_tilt_reposition_config"></a>

## 📐 Tilt Reposition Feature

*Blueprint input: `cover_tilt_reposition_config`* *(default: `cover_tilt_reposition_disabled`)*

If Tilt Reposition Feature is enabled you can choose if the blinds are closed before tilting to a new position. In some cases tilting the blinds in small steps can lead to false positions. This is because of the minimum time the motor needs to run. If the runtime between current tilt position and target tilt position is to small the motor will not stop at the right position. Thus the blinds will be preclosed to 0 and then run to the target position.

<a id="open_tilt_position"></a>

## 🔼 Open Tilt Position

*Blueprint input: `open_tilt_position`* *(default: `50`)*

To which tilt position should the cover be moved when opening?

<a id="close_tilt_position"></a>

## 🔻 Close Tilt Position

*Blueprint input: `close_tilt_position`* *(default: `50`)*

To which tilt position should the cover be moved when closing?

<a id="ventilate_tilt_position"></a>

## 💨 Ventilate Tilt Position

*Blueprint input: `ventilate_tilt_position`* *(default: `50`)*

To which tilt position should the cover be moved for ventilation?

<a id="shading_tilt_position_0"></a>

## 🥵 Sun Shading Tilt Position

*Blueprint input: `shading_tilt_position_0`* *(default: `0`)*

Minimum tilt position for shading. The cover will be tilted to this position if the sun elevation is below the value of elevation 1.

<a id="shading_tilt_position_1"></a>

## 🥵 Sun Shading Tilt Position 1

*Blueprint input: `shading_tilt_position_1`* *(default: `20`)*

To which tilt position should the cover be moved for shading when the sun is above elevation 1?

<a id="shading_tilt_elevation_1"></a>

## 🥵 Sun Shading Tilt Elevation 1

*Blueprint input: `shading_tilt_elevation_1`* *(default: `20`)*

Sun elevation for tilt position 1.

<a id="shading_tilt_position_2"></a>

## 🥵 Sun Shading Tilt Position 2

*Blueprint input: `shading_tilt_position_2`* *(default: `37`)*

To which tilt position should the cover be moved for shading when the sun is above elevation 2?

<a id="shading_tilt_elevation_2"></a>

## 🥵 Sun Shading Tilt Elevation 2

*Blueprint input: `shading_tilt_elevation_2`* *(default: `30`)*

Sun elevation for tilt position 2.

<a id="shading_tilt_position_3"></a>

## 🥵 Sun Shading Tilt Position 3

*Blueprint input: `shading_tilt_position_3`* *(default: `50`)*

To which tilt position should the cover be moved for shading when the sun is above elevation 3?

<a id="shading_tilt_elevation_3"></a>

## 🥵 Sun Shading Tilt Elevation 3

*Blueprint input: `shading_tilt_elevation_3`* *(default: `48`)*

Sun elevation for tilt position 3.

{% endraw %}
