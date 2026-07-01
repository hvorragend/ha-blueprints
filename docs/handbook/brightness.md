{% raw %}
# 💡 Brightness

> Part of the [CCA Handbook](index). These options live in the **Brightness Configuration** section of the blueprint.

<center><p><small>
  <strong>Only for morning opening &amp; evening closing!</strong><br />
  This condition allows the cover to open earlier in the morning or close earlier in the evening,<br />
  triggered by ambient brightness reaching its threshold.<br />
  <strong>This is NOT related to sun protection / shading.</strong>
</small></p></center>

<a id="default_brightness_sensor"></a>

## 🔅 Default Brightness Sensor

*Blueprint input: `default_brightness_sensor`*

This default brightness sensor can be defined here, which is used for daily up and down.

<a id="brightness_time_duration"></a>

## 🔅 Brightness Time Duration

*Blueprint input: `brightness_time_duration`* *(default: `30`)*

Defines the time to given brightness sensor must be stay above/below the thresholds.

<a id="brightness_up"></a>

## 🔅 Brightness Value For Opening The Cover

*Blueprint input: `brightness_up`* *(default: `0`)*

At what brightness value should the cover be opened?

<a id="brightness_down"></a>

## 🔅 Brightness Value For Closing The Cover

*Blueprint input: `brightness_down`* *(default: `0`)*

At what brightness value should the cover be closed? Must be lower then the brightness up value.

<a id="brightness_hysteresis"></a>

## 🔅 Brightness Hysteresis Value

*Blueprint input: `brightness_hysteresis`* *(default: `0`)*

Cover will open only when brightness exceeds (brightness_up + hysteresis), and close only when it drops below (brightness_down - hysteresis). Prevents frequent open/close cycles.

{% endraw %}
