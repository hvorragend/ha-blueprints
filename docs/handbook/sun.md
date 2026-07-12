{% raw %}
# ☀️ Sun Elevation

[📖 CCA Handbook](index) › Blueprint section: **Sun Elevation Settings**

<strong>Only for morning opening &amp; evening closing!</strong><br />
  This condition opens the cover when the sun rises above a threshold and closes it when the sun drops below a threshold.<br />
  <strong>This is NOT sun protection / shading</strong> (which controls midday partial closing).

**On this page:** [☀️ Sun Sensor](#default_sun_sensor) · [☀️ Sun Time Duration](#sun_time_duration) · [☀️ Sun Elevation Mode](#sun_elevation_mode) · [☀️ Sun Elevation Value For Opening The Cover](#sun_elevation_up) · [☀️ Sun Elevation Value For Closing The Cover](#sun_elevation_down) · [☀️ Sun Elevation Up Sensor (Dynamic/Hybrid - Optional)](#sun_elevation_up_sensor) · [☀️ Sun Elevation Down Sensor (Dynamic/Hybrid - Optional)](#sun_elevation_down_sensor)

---

<a id="default_sun_sensor"></a>

## ☀️ Sun Sensor

> 🧩 Input: `default_sun_sensor` · Default: `sun.sun`

Which sensors provides attributes with current azimuth and elevation of sun. I strongly suggest to use sun.sun ([Sun integration](https://www.home-assistant.io/integrations/sun/)). Please make sure that the integration is activated and provides the attributes. This sensor is also used for sun protection / sunshade control. <br /><br /> <ins>A few examples of threshold values:</ins> <ul> <li>+18° Astronomical Dusk</li> <li>+12° Nautical Dusk</li> <li>+6° Dusk</li> <li>0° Sunrise/Sunset (Default)</li> <li>-6° Civil Dawn</li> <li>-12° Nautical Dawn</li> <li>-18° Astronomical Dawn/Night</li> </ul> <br />`Optional` / `Shading`

---

<a id="sun_time_duration"></a>

## ☀️ Sun Time Duration

> 🧩 Input: `sun_time_duration` · Default: `30`

Defines the time to given sun sensor must be stay above/below the thresholds.

---

<a id="sun_elevation_mode"></a>

## ☀️ Sun Elevation Mode

> 🧩 Input: `sun_elevation_mode` · Default: `fixed`

**Select how sun elevation thresholds are determined:** <br /><br /> **🔒 Fixed Mode** (Default) <br /> Uses only the fixed values configured below (Sun Elevation Value For Opening/Closing). Sensors are ignored even if configured. <br /><br /> **📊 Dynamic Mode** <br /> Uses only the sensor values (Sun Elevation Up/Down Sensor). Fixed values are ignored. Sensors must be configured and provide valid numeric values. <br /><br /> **🔄 Hybrid Mode** <br /> Combines both: Sensor value + Fixed value as offset. Example: Sensor=2.0° + Fixed=1.5° = Threshold of 3.5°. Allows seasonal adaptation with manual fine-tuning offset. <br /><br /> `Optional` / `Default: Fixed`

---

<a id="sun_elevation_up"></a>

## ☀️ Sun Elevation Value For Opening The Cover

> 🧩 Input: `sun_elevation_up` · Default: `0`

**Fixed Mode**: Direct threshold value for opening. <br /> **Dynamic Mode**: Ignored (sensor value is used). <br /> **Hybrid Mode**: Added as offset to sensor value. <br /><br /> The cover will be <ins>opened</ins> if the sun elevation is over the calculated threshold.

---

<a id="sun_elevation_down"></a>

## ☀️ Sun Elevation Value For Closing The Cover

> 🧩 Input: `sun_elevation_down` · Default: `0`

**Fixed Mode**: Direct threshold value for closing. <br /> **Dynamic Mode**: Ignored (sensor value is used). <br /> **Hybrid Mode**: Added as offset to sensor value. <br /><br /> The cover will be <ins>closed</ins> if the sun elevation is under the calculated threshold.

---

<a id="sun_elevation_up_sensor"></a>

## ☀️ Sun Elevation Up Sensor (Dynamic/Hybrid - Optional)

> 🧩 Input: `sun_elevation_up_sensor`

Optional sensor that provides a **dynamic elevation threshold** for opening based on season. This sensor value is compared with the **sun elevation from the sun integration** (`sun.sun` attribute `elevation`). <br /><br /> **Behavior depends on Sun Elevation Mode:** <br /> • **Fixed Mode**: Sensor is ignored even if configured <br /> • **Dynamic Mode**: Sensor value is used directly as threshold (required) <br /> • **Hybrid Mode**: Sensor value + Fixed value as combined threshold <br /><br /> **How it works**: The cover opens when the **current sun elevation is higher** than the calculated threshold. The sensor provides the threshold (in degrees) — dynamic instead of fixed in the blueprint. <br /><br /> **Example (Dynamic Mode)**: Sensor value = 2.5° → Cover opens when `sun.sun` elevation rises above 2.5°. In summer (sensor = 5.0°) the cover opens later than in winter (sensor = -2.0°), matching seasonal sunrise times. <br /><br /> **Example (Hybrid Mode)**: Sensor value = 2.0°, Fixed value = 1.5° → Threshold = 3.5°. Allows seasonal adaptation with manual fine-tuning. <br /><br /> **Multiple covers**: For different behavior per cover (e.g., east vs. west facing), create multiple template sensors with different thresholds. <br /><br /> **Recommended options**:<br /> • **Template sensor** with seasonal interpolation for automatic year-round adaptation ([Guide](https://hvorragend.github.io/ha-blueprints/DYNAMIC_SUN_ELEVATION))<br /> • **Input Number helper** for manual GUI-based configuration via dashboard <br /><br /> `Optional` / `Required for Dynamic Mode`

---

<a id="sun_elevation_down_sensor"></a>

## ☀️ Sun Elevation Down Sensor (Dynamic/Hybrid - Optional)

> 🧩 Input: `sun_elevation_down_sensor`

Optional sensor that provides a **dynamic elevation threshold** for closing based on season. This sensor value is compared with the **sun elevation from the sun integration** (`sun.sun` attribute `elevation`). <br /><br /> **Behavior depends on Sun Elevation Mode:** <br /> • **Fixed Mode**: Sensor is ignored even if configured <br /> • **Dynamic Mode**: Sensor value is used directly as threshold (required) <br /> • **Hybrid Mode**: Sensor value + Fixed value as combined threshold <br /><br /> **How it works**: The cover closes when the **current sun elevation is lower** than the calculated threshold. The sensor provides the threshold (in degrees) — dynamic instead of fixed in the blueprint. <br /><br /> **Example (Dynamic Mode)**: Sensor value = 0.5° → Cover closes when `sun.sun` elevation sets below 0.5°. In summer (sensor = 2.0°) the cover closes later than in winter (sensor = -4.0°), matching seasonal sunset times. <br /><br /> **Example (Hybrid Mode)**: Sensor value = 0.0°, Fixed value = -1.0° → Threshold = -1.0°. Allows seasonal adaptation with manual fine-tuning. <br /><br /> **Multiple covers**: For different behavior per cover (e.g., east vs. west facing), create multiple template sensors with different thresholds. <br /><br /> **Recommended options**:<br /> • **Template sensor** with seasonal interpolation for automatic year-round adaptation ([Guide](https://hvorragend.github.io/ha-blueprints/DYNAMIC_SUN_ELEVATION))<br /> • **Input Number helper** for manual GUI-based configuration via dashboard <br /><br /> `Optional` / `Required for Dynamic Mode`

---

[⬅️ Handbook index](index) · Previous: [💡 Brightness](brightness) · Next: [🚪 Window Contacts & Ventilation](contacts)

{% endraw %}
