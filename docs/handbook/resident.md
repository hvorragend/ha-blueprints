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

> 💡 **Vacation tip:** The resident sensor does not have to be a bed sensor — a shared
> `input_boolean.vacation_mode` turns this feature into a whole-house vacation mode:
> covers close when you leave and stay closed, while Force functions (e.g. a
> bad-weather force open) keep their higher priority. The full recipe, including a
> per-cover presence simulation via Additional Conditions, is in the
> [FAQ](../FAQ#q-how-do-i-set-up-cca-for-a-vacation-nobody-home).

---

[⬅️ Handbook index](index) · Previous: [🪟 Tilt Positions (Venetian Blinds)](tilt) · Next: [✋ Manual Override & Reset](override)

{% endraw %}
