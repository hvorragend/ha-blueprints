{% raw %}
# 🪟 Tilt Positions (Venetian Blinds)

[📖 CCA Handbook](index) › Blueprint section: **Cover Tilt Position Settings**

**On this page:**

- [🔄 Tilt Wait Mode](#cover_tilt_wait_mode)
- [🔄 Tilt Wait Timeout](#cover_tilt_wait_timeout)
- [🕛 Default Tilt Delay](#tilt_delay)
- [📐 Tilt Position Feature](#cover_tilt_config)
- [📐 Tilt Reposition Feature](#cover_tilt_reposition_config)
- [🔼 Open Tilt Position](#open_tilt_position)
- [🔻 Close Tilt Position](#close_tilt_position)
- [💨 Ventilate Tilt Position](#ventilate_tilt_position)
- [〰️ Tilt Position Tolerance](#tilt_position_tolerance)
- [🥵 Sun Shading Tilt Position](#shading_tilt_position_0)
- [🥵 Sun Shading Tilt Position 1](#shading_tilt_position_1)
- [🥵 Sun Shading Tilt Elevation 1](#shading_tilt_elevation_1)
- [🥵 Sun Shading Tilt Position 2](#shading_tilt_position_2)
- [🥵 Sun Shading Tilt Elevation 2](#shading_tilt_elevation_2)
- [🥵 Sun Shading Tilt Position 3](#shading_tilt_position_3)
- [🥵 Sun Shading Tilt Elevation 3](#shading_tilt_elevation_3)

---

<a id="cover_tilt_wait_mode"></a>

## 🔄 Tilt Wait Mode

> 🧩 Input: `cover_tilt_wait_mode` · Default: `fixed_delay`

Choose how CCA waits before sending tilt commands:
**Fixed Delay (Standard)**: Uses the configured tilt delay value. Works well for most devices.
**Wait Until Idle (Z-Wave)**: Waits until cover reports 'open' or 'closed' state before sending tilt. Prevents tilt commands from being ignored on devices that block tilt during motor movement (e.g., Shelly Qubino Wave Shutter).
If your tilt positions are unreliable, try switching to 'Wait Until Idle' mode.

---

<a id="cover_tilt_wait_timeout"></a>

## 🔄 Tilt Wait Timeout

> 🧩 Input: `cover_tilt_wait_timeout` · Default: `30`

Maximum time to wait for cover to become idle before sending tilt command. Only used when 'Wait Until Idle' mode is selected.

---

<a id="tilt_delay"></a>

## 🕛 Default Tilt Delay

> 🧩 Input: `tilt_delay` · Default: `0`

Delay between <em>set_cover_position</em> and <em>set_cover_tilt_position</em>. Only necessary when using the tilt functions. This separates the two commands in terms of time. <br /><br />`Optional`

---

<a id="cover_tilt_config"></a>

## 📐 Tilt Position Feature

> 🧩 Input: `cover_tilt_config` · Default: `cover_tilt_disabled`

⚠️ <strong>Note:</strong> Tilt control is only available for blinds/shutters, not for awnings. <br /><br /> If the cover and the integration support it, the tilt position of the cover can be set. The standard attribute ‘current_tilt_position’ is used for this.

---

<a id="cover_tilt_reposition_config"></a>

## 📐 Tilt Reposition Feature

> 🧩 Input: `cover_tilt_reposition_config` · Default: `cover_tilt_reposition_disabled`

If Tilt Reposition Feature is enabled you can choose if the blinds are closed before tilting to a new position. In some cases tilting the blinds in small steps can lead to false positions. This is because of the minimum time the motor needs to run. If the runtime between current tilt position and target tilt position is to small the motor will not stop at the right position. Thus the blinds will be preclosed to 0 and then run to the target position.

---

<a id="open_tilt_position"></a>

## 🔼 Open Tilt Position

> 🧩 Input: `open_tilt_position` · Default: `50`

To which tilt position should the cover be moved when opening?

---

<a id="close_tilt_position"></a>

## 🔻 Close Tilt Position

> 🧩 Input: `close_tilt_position` · Default: `50`

To which tilt position should the cover be moved when closing?

---

<a id="ventilate_tilt_position"></a>

## 💨 Ventilate Tilt Position

> 🧩 Input: `ventilate_tilt_position` · Default: `50`

To which tilt position should the cover be moved for ventilation?

---

<a id="tilt_position_tolerance"></a>

## 〰️ Tilt Position Tolerance

> 🧩 Input: `tilt_position_tolerance` · Default: `0`

Tolerance to be applied when comparing the current tilt position with the to be tilt position. These are absolute values, analogous to the position tolerance. Use this when several states share the same cover position and can only be told apart by their tilt angle (e.g. closed/shading/ventilate all at position 0), or to absorb small tilt motor inaccuracies.

---

<a id="shading_tilt_position_0"></a>

## 🥵 Sun Shading Tilt Position

> 🧩 Input: `shading_tilt_position_0` · Default: `0`

Minimum tilt position for shading. The cover will be tilted to this position if the sun elevation is below the value of elevation 1.

---

<a id="shading_tilt_position_1"></a>

## 🥵 Sun Shading Tilt Position 1

> 🧩 Input: `shading_tilt_position_1` · Default: `20`

To which tilt position should the cover be moved for shading when the sun is above elevation 1?

---

<a id="shading_tilt_elevation_1"></a>

## 🥵 Sun Shading Tilt Elevation 1

> 🧩 Input: `shading_tilt_elevation_1` · Default: `20`

Sun elevation for tilt position 1.

---

<a id="shading_tilt_position_2"></a>

## 🥵 Sun Shading Tilt Position 2

> 🧩 Input: `shading_tilt_position_2` · Default: `37`

To which tilt position should the cover be moved for shading when the sun is above elevation 2?

---

<a id="shading_tilt_elevation_2"></a>

## 🥵 Sun Shading Tilt Elevation 2

> 🧩 Input: `shading_tilt_elevation_2` · Default: `30`

Sun elevation for tilt position 2.

---

<a id="shading_tilt_position_3"></a>

## 🥵 Sun Shading Tilt Position 3

> 🧩 Input: `shading_tilt_position_3` · Default: `50`

To which tilt position should the cover be moved for shading when the sun is above elevation 3?

---

<a id="shading_tilt_elevation_3"></a>

## 🥵 Sun Shading Tilt Elevation 3

> 🧩 Input: `shading_tilt_elevation_3` · Default: `48`

Sun elevation for tilt position 3.

---

[⬅️ Handbook index](index) · Previous: [🌤️ Sun Shading](shading) · Next: [🛏️ Resident Mode](resident)

{% endraw %}
