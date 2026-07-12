{% raw %}
# 💡 Brightness

[📖 CCA Handbook](index) › Blueprint section: **Brightness Configuration**

<strong>Only for morning opening &amp; evening closing!</strong><br />
  This condition allows the cover to open earlier in the morning or close earlier in the evening,<br />
  triggered by ambient brightness reaching its threshold.<br />
  <strong>This is NOT related to sun protection / shading.</strong>

**On this page:** [🔅 Default Brightness Sensor](#default_brightness_sensor) · [🔅 Brightness Time Duration](#brightness_time_duration) · [🔅 Brightness Value For Opening The Cover](#brightness_up) · [🔅 Brightness Value For Closing The Cover](#brightness_down) · [🔅 Brightness Hysteresis Value](#brightness_hysteresis)

---

<a id="default_brightness_sensor"></a>

## 🔅 Default Brightness Sensor

> 🧩 Input: `default_brightness_sensor`

This default brightness sensor can be defined here, which is used for daily up and down.

---

<a id="brightness_time_duration"></a>

## 🔅 Brightness Time Duration

> 🧩 Input: `brightness_time_duration` · Default: `30`

Defines the time to given brightness sensor must be stay above/below the thresholds.

---

<a id="brightness_up"></a>

## 🔅 Brightness Value For Opening The Cover

> 🧩 Input: `brightness_up` · Default: `0`

At what brightness value should the cover be opened?

---

<a id="brightness_down"></a>

## 🔅 Brightness Value For Closing The Cover

> 🧩 Input: `brightness_down` · Default: `0`

At what brightness value should the cover be closed? Must be lower then the brightness up value.

---

<a id="brightness_hysteresis"></a>

## 🔅 Brightness Hysteresis Value

> 🧩 Input: `brightness_hysteresis` · Default: `0`

Cover will open only when brightness exceeds (brightness_up + hysteresis), and close only when it drops below (brightness_down - hysteresis). Prevents frequent open/close cycles.

---

[⬅️ Handbook index](index) · Previous: [⏰ Time & Calendar Control](time) · Next: [☀️ Sun Elevation](sun)

{% endraw %}
