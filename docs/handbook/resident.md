{% raw %}
# 🛏️ Resident Mode

[📖 CCA Handbook](index) › Blueprint section: **Resident Settings**

<br />
  (1) The purpose of resident mode is to the close the cover (without checking the defined times) when the resident sensor switches to ‘on/true’. For example, when a resident goes to sleep.
  <br />
  (2) The cover will stay closed as long as the sensor remains in this state.
  <br />
  (3) When the resident sensor switches to ‘off/false’, the cover is automatically opened in the morning.
  <br />
  (4) In addition, the usual automatic opening of the cover is prevented as long as the sensor is set to ‘on/true’ or the resident.
  <br /><br />
  All these settings are optional.

**On this page:** [🛌 Resident Sensor](#resident_sensor) · [🛌 Resident Configuration](#resident_config)

---

<a id="resident_sensor"></a>

## 🛌 Resident Sensor

> 🧩 Input: `resident_sensor`

You can use this to define a resident for the room

---

<a id="resident_config"></a>

## 🛌 Resident Configuration

> 🧩 Input: `resident_config`

Configure how the automation responds to resident sensor changes.

- **Opening enabled**: Cover opens when resident wakes up, but only if time, brightness, and sun elevation conditions are met
- **Closing enabled**: Cover closes when resident goes to sleep (immediate, ignores other conditions)

---

[⬅️ Handbook index](index) · Previous: [🪟 Tilt Positions (Venetian Blinds)](tilt) · Next: [✋ Manual Override & Reset](override)

{% endraw %}
