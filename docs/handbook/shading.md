{% raw %}
# 🌤️ Sun Shading

> Part of the [CCA Handbook](index). These options live in the **Sun Shading / Sun Protection** section of the blueprint.

<center><p><small>
  Settings if the feature '🥵 - Sun Protection / Shading — Partially close when sun shines on window' has been activated above.
  <br />
  All these settings are optional / The attributes of default sun sensor (configured above) is used.
</small></p></center>
<details> <summary><code><strong>CLICK HERE:</strong> How the shading process works (two phases)</code></summary>

**Phase 1 — Pending (trigger):**
When ANY configured shading trigger fires (sun azimuth, elevation, brightness, temperature, forecast), the automation arms a "pending" timer. This sets the status to <em>t_shading_start_pending</em> and starts the waiting time.

**Phase 2 — Execution (after waiting time):**
After the waiting time expires, the automation re-evaluates ALL configured conditions. Only if they are <strong>still valid</strong> at this point, the cover actually moves to the shading position.

**Common reasons why shading stays stuck at "pending":**
- <strong>Forecast temperature sensor misconfigured:</strong> If using a weather entity, make sure it provides temperature data (check Developer Tools → States). If the forecast returns "unavailable" or "unknown", the condition fails.
- <strong>Time window mismatch:</strong> Shading only executes within the configured daytime window (between earliest opening time and latest closing time). If no time control is configured, enable "Disable Time Control" or configure valid times.
- <strong>"Additional Condition" blocks execution:</strong> The "Additional Condition When Activating Sun Shading" is checked at execution time. If configured, it must be true for the cover to move.
- <strong>Cover already at/below shading position:</strong> If the cover is already at or below the shading position, no movement occurs (but the state is saved).
- <strong>Helper shows stale data:</strong> Check the input_text helper entity in Developer Tools → States. Look for <code>"pnd":"beg"</code> and verify that <code>"ts.due"</code> is a valid future timestamp.

**Debugging tip:** Enable the Logbook option and check the automation trace after the waiting time expires. Look for the <em>t_shading_start_execution</em> trigger — if it doesn't appear, the template trigger may not be evaluating correctly. If it appears but the trace shows "conditions not met", check which specific condition fails using Developer Tools → Template.
</details>

<a id="shading_conditions_start_and"></a>

## 🌞 Shading START - Required Conditions (AND)

*Blueprint input: `shading_conditions_start_and`* *(default: `['cond_azimuth', 'cond_elevation', 'cond_brightness', 'cond_temp1', 'cond_temp2', 'cond_forecast_temp', 'cond_forecast_weather']`)*

**Conditions that MUST ALL be met to START shading**

<details>
<summary><code><strong>CLICK HERE:</strong> How START conditions work</code></summary>


**Required (AND) conditions for START:**

- ALL selected conditions must be valid

- If ANY fails, shading will NOT start

- Use for critical conditions


**Example - Conservative approach:**

- Select ALL: Azimuth, Elevation, Brightness, Temperature

- Result: Shading only when everything is perfect


**Example - Flexible approach:**

- Select: Azimuth, Elevation (sun position)

- Leave others for OR list

- Result: Sun must be in range, plus other criteria


**Important:** Conditions without a configured sensor are automatically satisfied (skipped). You can safely leave all conditions selected — only those with a matching sensor configured below will actually be evaluated. However, if a sensor IS configured but returns "unavailable" or "unknown", the condition will FAIL — sun shading then does not start, but the rest of the automation (opening, closing, ventilation) keeps working normally. Once the sensor reports again, the sun shading conditions are re-evaluated, so a shading that was missed while the sensor was down is not lost.

</details>

<a id="shading_conditions_start_or"></a>

## 🌞 Shading START - Optional Conditions (OR)

*Blueprint input: `shading_conditions_start_or`*

**Conditions where AT LEAST ONE must be met to START shading**
<details> <summary><code><strong>CLICK HERE:</strong> When to use OR conditions</code></summary>

**Optional (OR) conditions for START:**
- At least ONE must be valid
- Useful for redundant sensors
- Useful for alternative triggers

**Example - Redundant temperature sensors:**
- AND: Azimuth, Elevation, Brightness
- OR: Temp1, Temp2
- Result: Sun + Brightness + (Temp1 OR Temp2)
- If Temp1 fails, Temp2 can still trigger

**Combined logic:**
- Final = (ALL AND conditions) AND (ONE OR condition)
</details>

<a id="shading_conditions_end_and"></a>

## 🌥️ Shading END - Required Conditions (AND)

*Blueprint input: `shading_conditions_end_and`*

**Conditions that MUST ALL become invalid to END shading**
<details> <summary><code><strong>CLICK HERE:</strong> How END conditions work</code></summary>

**Required (AND) conditions for END:**
- ALL selected conditions must become invalid
- Shading continues if ANY is still valid
- Use for stable shading (avoid flickering)

**Example - Quick response:**
- AND: (empty)
- OR: Azimuth, Elevation, Brightness
- Result: End immediately when ANY condition fails

**Example - Stable shading:**
- AND: Brightness, Temp1
- OR: (empty)
- Result: Keep shading until BOTH brightness AND temp drop

**Tip:** Usually END should be MORE permissive than START
</details>

<a id="shading_conditions_end_or"></a>

## 🌥️ Shading END - Optional Conditions (OR)

*Blueprint input: `shading_conditions_end_or`* *(default: `['cond_azimuth', 'cond_elevation', 'cond_brightness', 'cond_temp1', 'cond_temp2', 'cond_forecast_temp', 'cond_forecast_weather']`)*

**Conditions where AT LEAST ONE must become invalid to END shading**
<details> <summary><code><strong>CLICK HERE:</strong> Typical END configurations</code></summary>

**Optional (OR) conditions for END:**
- At least ONE must become invalid to end
- Shading ends quickly when conditions change

**Recommended: Quick sun position response**
- AND: (empty)
- OR: Azimuth, Elevation
- Result: End immediately when sun moves out of range

**Combining AND + OR groups (both combined with OR):**
- AND: Azimuth, Elevation
- OR: Brightness
- Result: End when the sun is fully out of range (Azimuth AND Elevation outside) **OR** when it gets dark (Brightness below) — whichever happens first

**Keep shading longer (require multiple conditions):**
- AND: Azimuth, Elevation, Brightness
- OR: (empty)
- Result: End only when ALL three become invalid (sun out of range AND dark)

**Combined logic:**
- Final = (ALL AND invalid) OR (ONE OR invalid)
- The AND group and the OR group are themselves combined with **OR** (unlike START, where they are combined with AND). To require several end conditions together, put them ALL in the AND group and leave the OR group empty.
</details>

<a id="shading_azimuth_start"></a>

## 📐 Sun Shading - Azimuth Start Value

*Blueprint input: `shading_azimuth_start`* *(default: `95`)*

What is the minimum azimuth at which the sun hits the window? (Shading will start)

<a id="shading_azimuth_end"></a>

## 📐 Sun Shading - Azimuth End Value

*Blueprint input: `shading_azimuth_end`* *(default: `265`)*

What is the maximum azimuth at which the sun hits the window? (Shading will stop)

<a id="shading_elevation_min"></a>

## 📈 Sun Shading - Elevation Minimum Value

*Blueprint input: `shading_elevation_min`* *(default: `25`)*

Starting from which elevation of the sun should the window be shaded? (Here it makes sense to consider surrounding buildings, trees, etc.).

<a id="shading_elevation_max"></a>

## 📈 Sun Shading - Elevation Maximum Value

*Blueprint input: `shading_elevation_max`* *(default: `90`)*

What is the maximal elevation for elevation? (In most cases, 90 degrees is probably the most reasonable value. However, this can also be different due to surrounding buildings, etc.).

<a id="shading_brightness_sensor"></a>

## 🔆 Sun Shading - Brightness Sensor

*Blueprint input: `shading_brightness_sensor`*

This sensor is only used for shading.

<a id="shading_sun_brightness_start"></a>

## 🔆 Sun Shading - Brightness Start Value

*Blueprint input: `shading_sun_brightness_start`* *(default: `35000`)*

The minimum brightness value from which shading should start. (Must be above the value of brightness end!)

<a id="shading_sun_brightness_end"></a>

## 🔆 Sun Shading - Brightness End Value

*Blueprint input: `shading_sun_brightness_end`* *(default: `25000`)*

The brightness value from which shading is no longer necessary. (Must be below the value of brightness start!).

<a id="shading_sun_brightness_hysteresis"></a>

## 🔆 Sun Shading - Brightness Hysteresis

*Blueprint input: `shading_sun_brightness_hysteresis`* *(default: `0`)*

Hysteresis value to prevent flickering. The brightness must exceed (start + hysteresis) to activate shading and fall below (end - hysteresis) to deactivate it. See: [FAQ: How does hysteresis work?](https://hvorragend.github.io/ha-blueprints/FAQ#q-how-does-hysteresis-work)

<a id="shading_temperatur_sensor1"></a>

## 1️⃣ Sun Shading - Temperature Sensor 1 (eg. indoor)

*Blueprint input: `shading_temperatur_sensor1`*

This is the first temperature sensor used for sun shading logic.<br /> For example, you can use the current **indoor temperature** as a condition to trigger shading.

<a id="shading_min_temperatur1"></a>

## 1️⃣ Sun Shading - Temperature Sensor 1 Minimum Value

*Blueprint input: `shading_min_temperatur1`* *(default: `18`)*

Minimum temperature for sensor 1 above which shading should occur.

<a id="shading_temperature_hysteresis1"></a>

## 1️⃣ Sun Shading - Temperature Sensor 1 Hysteresis Value

*Blueprint input: `shading_temperature_hysteresis1`* *(default: `0.2`)*

Shading will end only when temperature drops below (minimum - hysteresis value) to prevent frequent open/close cycles. See: [FAQ: How does hysteresis work?](https://hvorragend.github.io/ha-blueprints/FAQ#q-how-does-hysteresis-work)

<a id="shading_temperatur_sensor2"></a>

## 2️⃣ Sun Shading - Temperature Sensor 2 (eg. outdoor)

*Blueprint input: `shading_temperatur_sensor2`*

This is an optional secondary temperature sensor, typically used for **outdoor temperature**. <br /> It can serve as an additional condition for sun shading logic. <br /><br /> This sensor also plays a role in the calculation of the <ins>Sun Shading - Forecast Temperature Value</ins>. Please refer to that section for more details.

<a id="shading_min_temperatur2"></a>

## 2️⃣ Sun Shading - Temperature Sensor 2 Minimum Value

*Blueprint input: `shading_min_temperatur2`* *(default: `18`)*

Minimum temperature for sensor 2 above which shading should occur.

<a id="shading_temperature_hysteresis2"></a>

## 2️⃣ Sun Shading - Temperature Sensor 2 Hysteresis Value

*Blueprint input: `shading_temperature_hysteresis2`* *(default: `0.2`)*

Shading will end only when temperature drops below (minimum - hysteresis value) to prevent frequent open/close cycles. See: [FAQ: How does hysteresis work?](https://hvorragend.github.io/ha-blueprints/FAQ#q-how-does-hysteresis-work)

<a id="shading_forecast_sensor"></a>

## 📊 Sun Shading - Forecast Weather Entity

*Blueprint input: `shading_forecast_sensor`*

Weather entity for forecast data (temperature & conditions). This is the primary and recommended method for forecast-based shading.
<details>
  <summary><code><strong>CLICK HERE:</strong> How to configure</code></summary>

  Select a weather entity (e.g., weather.home, weather.openweathermap).

  The system will:

  - Query forecast temperature for comparison

  - Check weather conditions if configured

  - Use daily or hourly forecast based on your selection below

  **Most users should use this field.**

  The idea is that it can happen, especially in spring, that the value of the
  <em>Forecast Temperature Value</em> is exceeded by strong solar radiation and
  the shading would be started. However, in spring you may not want shading,
  but the solar radiation as a welcome, free heating is desired.
  So you can define via the forecast that shading is only started at an
  expected daily maximum temperature.

</details>

<a id="shading_forecast_type"></a>

## 📊 Sun Shading - Forecast Source

*Blueprint input: `shading_forecast_type`* *(default: `daily`)*

Please select whether you want to use the **daily** or **hourly** weather forecast. This only works if a weather entity has been configured above. <br /> The first entry in the forecast array will always be used — this corresponds to the current day or current hour. <br /><br /> Note: Your weather entity must support `weather.get_forecasts`, which was introduced in Home Assistant 2023.9. <br /><br /> Alternatively, you can choose **not to use** the forecast service at all. In that case, the current weather attributes from the weather entity will be used instead. <br /><br /> **Recommendation:** Using the **daily forecast** is generally preferred for sun shading purposes. <br /><br /> **Ignored when using temperature sensor below.**

<a id="shading_forecast_temp_sensor"></a>

## 📊 Sun Shading - Direct Temperature Sensor (Alternative)

*Blueprint input: `shading_forecast_temp_sensor`*

**Alternative method:** Use a sensor that directly provides forecasted max temperature.
<details>
  <summary><code><strong>CLICK HERE:</strong> When to use this</code></summary>

  Use this if:

  - Your weather integration provides dedicated forecast sensors

  - You want better performance (no forecast service calls)

  - You have custom template sensors for forecast temperature

  Examples:

  - sensor.pirateweather_daytime_high_apparent_temperature_0d

  - sensor.met_no_forecast_temperature_max

  - sensor.openweathermap_forecast_temperature

  **Priority:** If configured, this takes priority over weather entity above.

  **Limitation:** Weather condition checks are not available with sensors.

</details>

<a id="shading_forecast_temp"></a>

## 📊 Sun Shading - Forecast Temperature Value

*Blueprint input: `shading_forecast_temp`*

This setting defines the <strong>minimum temperature threshold</strong> based on the forecast at which shading should be activated. If the forecasted temperature exceeds this value, the shading system will respond accordingly.
- Minimum temperature threshold for shading activation.
- Works with both weather entity and temperature sensor.
- Leave empty to disable temperature-based forecast shading.
<details>
  <summary><code><strong>CLICK HERE:</strong> Further description</code></summary>

  To enhance reliability, the system can compare this threshold against two sources:

  - The forecasted temperature (this comparison is always active)

  - Temperature Sensor 2 (e.g. outdoor) (can be enabled via the checkbox in the next configuration field)


  <strong>Troubleshooting:</strong> If this condition is in your AND list, the forecast source (weather entity or temperature sensor above) MUST provide a valid numeric temperature value. Check Developer Tools → States that your weather entity or sensor shows a numeric temperature, not "unavailable" or "unknown". If the forecast returns no data, this condition will fail and block shading execution.

</details>

<a id="shading_forecast_temp_hysteresis"></a>

## 📊 Sun Shading - Forecast Temperature Hysteresis

*Blueprint input: `shading_forecast_temp_hysteresis`* *(default: `0`)*

Prevents frequent on/off cycles near threshold.
- Shading starts: forecast > (threshold + hysteresis)
- Shading ends: forecast < (threshold - hysteresis)

See: [FAQ: How does hysteresis work?](https://hvorragend.github.io/ha-blueprints/FAQ#q-how-does-hysteresis-work)

<a id="shading_weather_conditions"></a>

## 🌦️ Sun Shading - Weather Conditions

*Blueprint input: `shading_weather_conditions`*

Check the following weather conditions when activating the shading. Be cautious when making your selection, as weather forecasts may not always be accurate and could lead to incorrect shading decisions. And as mentioned above, weather conditions can only be checked if a weather entity has been configured under ‘Forecast Weather Sensor’. <br /><br /> **Only works with weather entity, not with temperature sensor.** <br /> Be cautious: weather forecasts may not always be accurate.

<a id="shading_config"></a>

## 🥵 Sun Shading - Configuration

*Blueprint input: `shading_config`*

These options allow you to fine-tune how the system handles temperature-based shading. <p><em>Click on the titles to get further help.</em></p> <details> <summary><code><strong>Independent Shading via Temperature Comparison</strong></code></summary>

  Enables shading based solely on temperature — <ins>independently of all other conditions</ins> like brightness, sun position (azimuth <em>and</em> elevation), or time of day.
  - By default, only the external <em>forecasted temperature</em> is compared with the threshold configured in <em>"Independent Temperature Threshold"</em>.
  - You can also enable another comparison by selecting the other checkbox.

  If any value exceeds the independent threshold, shading is activated — <strong>even if all other shading conditions are false</strong>.

  <strong>⚠️ This bypasses the sun position.</strong> With this option enabled, shading can start while the sun azimuth is <em>outside</em> your configured range and the sun elevation is <em>below</em> your threshold — i.e. even when the sun is not on this facade at all. The bypass is <ins>not limited to the morning</ins>: it applies every time a shading-start trigger fires throughout the day, as long as the temperature stays above the threshold. If you want shading to keep respecting the sun position, leave this option <strong>unchecked</strong> and rely on the normal AND/OR conditions (which include azimuth and elevation).

  <strong>Why this exists:</strong> it lets the system decide early in the morning — from the forecast alone — that the day will be hot, and move the blinds straight into the shading position instead of first opening them fully, before the sun even reaches the facade.

  Additionally, one hour before the earliest possible opening time, the system retrieves the latest weather forecast.

  This allows it to compare the updated forecasted temperature with the configured threshold and make an early shading decision based on the most current data.

  <strong>Note:</strong> The independent path uses its own <em>"Independent Temperature Threshold"</em>, which is separate from <em>"Forecast Temperature Value"</em> used in the normal AND/OR conditions. Set the independent threshold lower to allow early shading on hot days without loosening the normal forecast gate.

</details> <br /> <details> <summary><code><strong>Also trigger if 'Temperature Sensor 2' exceeds 'Forecast Temperature Value'</strong></code></summary>

  This activates an extended comparison for the independent shading path. The shading condition will be true if <em>one</em> of the following conditions is met:
  - The external forecasted temperature exceeds the <em>"Independent Temperature Threshold"</em>, or<br />
  - <em>"Temperature Sensor 2"</em> reports a temperature above the <em>"Independent Temperature Threshold"</em>.

  This mechanism improves the responsiveness and reliability of the shading system by using real-time sensor input as an optional condition, especially when forecast data is uncertain.
  Note: This function has nothing to do with normal temperature comparison, but is used exclusively in the context of the forecast function.
</details>

<a id="shading_independent_temp"></a>

## 🥵 Sun Shading - Independent Temperature Threshold

*Blueprint input: `shading_independent_temp`* *(default: `25`)*

Temperature threshold used exclusively by the <em>"Independent Shading via Temperature Comparison"</em> mode. Shading is activated independently of all other conditions (brightness, sun azimuth <em>and</em> elevation, etc.) when either the forecasted temperature or (if enabled) <em>"Temperature Sensor 2"</em> exceeds this value. <br /><br /> Set this lower than <em>"Forecast Temperature Value"</em> to allow the independent path to trigger on warmer-than-average days without tightening the normal forecast gate.

<a id="shading_waitingtime_start"></a>

## 🥵 Sun Shading - Start Waiting Time

*Blueprint input: `shading_waitingtime_start`* *(default: `300`)*

Waiting time between the initial shading trigger and the actual cover movement. After this time expires, <ins>all</ins> configured start conditions (AND + OR) are re-checked. The cover only moves if conditions are <strong>still valid</strong> at execution time. This waiting time is also used for the periodic condition checks within the retry loop. <br /><br /> <strong>If shading stays at "pending" and never executes:</strong> The conditions were no longer met after the waiting time expired. Check the automation trace for <em>t_shading_start_execution</em>.

<a id="shading_start_max_duration"></a>

## 🥵 Sun Shading - Maximum duration for shading start retry loop

*Blueprint input: `shading_start_max_duration`* *(default: `7200`)*

Maximum time to keep retrying shading start conditions after initial trigger.
The Start Waiting Time is used for the periodic condition checks during this retry loop.
If conditions remain unstable for longer than this timeout, the retry loop is stopped.
Shading will not start and waits for a new shading start trigger.

**Use case:** Prevents automation from being stuck in "waiting for stable conditions"
when weather is highly unstable (rapidly changing clouds).

**0 = disabled** (no periodic retry, stops immediately - old "trigger_reset" behavior)
**Recommended: 3600-7200 seconds (1-2 hours)**

<a id="shading_waitingtime_end"></a>

## 🥵 Sun Shading - End Waiting Time

*Blueprint input: `shading_waitingtime_end`* *(default: `300`)*

To avoid excessive load on the motor, a waiting time can be defined here before the shading is ended. Shading ends if one of the conditions is not fulfilled for the entire waiting time. This waiting time is also used for the periodic condition checks within the retry loop.

<a id="shading_end_max_duration"></a>

## 🥵 Sun Shading - Maximum duration for shading end retry loop

*Blueprint input: `shading_end_max_duration`* *(default: `7200`)*

Maximum time to keep retrying shading end conditions after initial trigger.
The End Waiting Time is used for the periodic condition checks during this retry loop.
If conditions remain unstable for longer than this timeout, the retry loop is stopped.
Shading remains active and waits for a new shading end trigger.

**Use case:** Prevents automation from being stuck in "waiting for stable conditions"
when weather is highly unstable (rapidly changing clouds).

**0 = disabled** (no periodic retry, behaves like old version)
**Recommended: 3600-7200 seconds (1-2 hours)**

<a id="shading_end_immediate_by_sun_position"></a>

## 🥵 End Sun Shading - Immediately When Out Of Range

*Blueprint input: `shading_end_immediate_by_sun_position`* *(default: `False`)*

Speeds up the END of shading: once the sun leaves the azimuth or elevation range, shading ends after only a few seconds instead of waiting for the configured end waiting time.

**Important:** This option only controls the *timing* of the end — not *which* conditions actually end the shading. For it to have any effect, "Sun Azimuth" and/or "Sun Elevation" must be part of your END conditions. Put them in the **OR** group if a single axis leaving its range should already end the shading. If they are in the **AND** group, shading ends only once *all* selected AND conditions are out of range at the same time (e.g. azimuth AND elevation together) — a single axis leaving its range is then not enough.

If disabled, the configured end waiting time is always used.

{% endraw %}
