# 🚀 CCA 2026.01.06 - Forecast Temperature Trigger Coverage

**Note:** Previous changes are archived here: [CHANGELOG_OLD.md](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/CHANGELOG_OLD.md).

## ✨ New Features

- **Added missing state triggers for Forecast Temperature condition**: The `cond_forecast_temp` condition now has dedicated state-change triggers (`t_shading_start_pending_6` and `t_shading_end_pending_6`) for immediate reaction when forecast temperature sensor values change. Previously, forecast temperature was only evaluated via time-based trigger or when other conditions triggered, which caused incomplete AND/OR logic evaluation.

### Example Impact

**Before this update:**
```yaml
shading_conditions_start_and: [cond_forecast_temp, cond_brightness]
```
- Brightness changes → Trigger fires ✅ → Evaluates forecast temp
- Forecast temp sensor changes → **No trigger** ❌ → Automation doesn't react

**After this update:**
```yaml
shading_conditions_start_and: [cond_forecast_temp, cond_brightness]
```
- Brightness changes → Trigger fires ✅ → Evaluates forecast temp
- **Forecast temp sensor changes → Trigger fires ✅ → Evaluates brightness** (NEW!)

### Trigger Organization

All state-based pending triggers now use IDs 1-6, with time-based triggers using 7+:

**State-based triggers (IDs 1-6):**
1. Azimuth + Elevation
2. Brightness
3. Temp1
4. Temp2
5. Weather Conditions
6. **Forecast Temperature** (NEW)

**Time-based triggers (IDs 7+):**
7. Forecast pre-load (1h before opening)

### Note for Weather Entity Users

When using a weather entity for forecast temperature (without a dedicated sensor), the existing weather condition trigger (`t_shading_start_pending_5` / `t_shading_end_pending_4`) will fire on weather entity updates. The forecast temperature is then loaded and evaluated in the action sequence, providing indirect coverage for weather entity-based forecast temperature.

---


# 🚀 CCA 2026.01.02 - Sun Elevation Trigger Mode Support

**Note:** Previous changes are archived here: [CHANGELOG_OLD.md](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/CHANGELOG_OLD.md).

## 🔧 Bug Fixes

- **Fixed sun elevation triggers to respect fixed/dynamic/hybrid modes**: Triggers `t_open_5` and `t_close_5` now correctly implement all three sun elevation modes (fixed, dynamic, hybrid) ensuring consistent threshold calculation across the automation.

---


# 🚀 CCA 2025.12.31 - Force Recovery Environment Check

**Note:** Previous changes are archived here: [CHANGELOG_OLD.md](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/CHANGELOG_OLD.md).

## 🔧 Bug Fixes

- **Fixed helper status update during force-disabled states** (#312): Helper status is now correctly updated even when force functions (e.g., force-close) are active. This ensures the background state is properly tracked during forced states, allowing covers to return to the correct position when force functions are deactivated. Previously, the helper update condition was stricter than the cover movement condition, causing inconsistent state tracking.

- **Fixed force-disabled recovery respecting environmental conditions** (#310): Covers now check sun elevation and brightness before reopening after force-disabled state ends (e.g., rain protection). Time-based triggers at `time_up_late`/`time_down_late` continue to work as ultimate fallback regardless of conditions.

---


# 🚀 CCA 2025.12.30 - Sun Elevation Modes (Fixed/Dynamic/Hybrid)

**Note:** Previous changes are archived here: [CHANGELOG_OLD.md](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/CHANGELOG_OLD.md).

## ☀️ Three Sun Elevation Modes

- **Flexible threshold calculation with three distinct modes**
  Choose how sun elevation thresholds are determined based on your needs and setup complexity.

### 🔒 Fixed Mode (Default)
- **Simple and straightforward**
  Uses only the configured fixed values for sun elevation thresholds. Perfect for users who don't need seasonal adaptation or prefer manual configuration.

- **Sensors are ignored**
  Even if elevation sensors are configured, they will be ignored in this mode. This ensures predictable behavior and prevents confusion.

- **Backward compatible**
  All existing configurations without the mode field automatically use Fixed mode, ensuring seamless upgrades.

### 📊 Dynamic Mode
- **Seasonal adaptation**
  Uses only sensor values for threshold calculation. The fixed values are completely ignored. Ideal for automatic seasonal adjustments using template sensors.

- **Sensors required**
  Both up and down sensors must be configured and provide valid numeric values. Config check validates this requirement.

- **Year-round automation**
  Perfect for users who want fully automated seasonal adaptation without manual intervention. Use with the [Dynamic Sun Elevation Guide](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/DYNAMIC_SUN_ELEVATION.md).

### 🔄 Hybrid Mode
- **Best of both worlds**
  Combines sensor value + fixed value as offset. Allows seasonal adaptation with manual fine-tuning capability.

- **Additive calculation**
  Final threshold = Sensor value + Fixed value. Example: Sensor 2.0° + Fixed 1.5° = Threshold 3.5°.

- **Flexible fine-tuning**
  Use the sensor for seasonal base values and adjust the fixed offset for per-cover tweaking (e.g., different orientations).

### 🔧 Configuration & Validation
- **New sun_elevation_mode selector**
  Easy-to-understand dropdown with clear descriptions for each mode in the Sun Elevation Settings section.

- **Updated field descriptions**
  All sun elevation fields now explain their behavior in each mode, making configuration intuitive.

### 💡 Use Cases
- **Fixed Mode**: Simple setups, manual control preference, no seasonal needs
- **Dynamic Mode**: Full automation, seasonal adaptation, template sensor enthusiasts
- **Hybrid Mode**: Seasonal base + manual offset, multi-cover setups with different orientations

---

## 🔧 Bug Fixes

- **Fixed prevent_multiple_times flags respecting manual intervention**: The
  `prevent_opening_multiple_times`, `prevent_closing_multiple_times`, and
  `prevent_shading_multiple_times` flags now correctly respect manual user
  intervention. Automation will not retry if the user manually changed the
  cover position after an automation attempt, ensuring user decisions are
  always respected.

---

# 🚀 CCA 2025.12.27 - Smart State Memory, Flexible Shading Logic, Calendar Integration, Awning Support & Dynamic Sun Elevation & More

## 🧠 Background State Memory & Force Return

- **Automatic return to target state after force disable**
  When `enable_background_state_tracking` is enabled, the cover automatically returns to the position stored in the helper (background state) after a force function is disabled. This enables seamless transitions from emergency states back to normal automation.

- **Continuous helper updates during force functions**
  The helper now continues to update in the background even when force functions are active, ensuring the target state always reflects the current automation intent. For example, if Force-Open is active but it's evening close time, the helper stores "close" as the background state.

- **Support for all position types**
  Return-to-background works for all cover states: open, close, shading, and ventilation positions. The automation intelligently determines which position to return to based on the helper's background state.

- **Backward compatible (opt-in)**
  The feature is disabled by default (`enable_background_state_tracking = false`), preserving existing behavior. Users must explicitly enable it to use the new functionality.

### 💡 Practical use cases

This feature is particularly useful for emergency and weather-based scenarios where you need manual control but want automation to resume afterward:

- 🌧️ **Rain Protection**: Force-close all covers during heavy rain. When rain stops, covers automatically return to their scheduled state (e.g., shading position during the day, open in the evening).

- 💨 **Wind Protection**: Force-open awnings/blinds during strong winds to prevent damage. Once wind subsides, covers return to sun shading or close position based on time of day.

- ❄️ **Frost Protection**: Force-open covers in winter mornings to prevent ice formation on mechanisms. After sunrise, covers automatically resume normal automation (close for privacy, shade for sun protection).

- 🔥 **Emergency Scenarios**: During fire alarm or security events, force all covers to specific positions. After the event, covers return to their intended automation state without manual intervention.

- 🏠 **Cleaning/Maintenance**: Force covers to full open position for window cleaning. When done, covers automatically return to current schedule (closed in evening, shaded during midday).

- 🌡️ **Extreme Heat Protection**: Temporarily force all covers closed during heat waves. When temperatures normalize, covers return to regular shading schedules.

- 🎬 **Movie Mode**: Force living room covers closed for watching movies during daytime. After movie ends, covers automatically return to open or shading position based on sun conditions.

### 🔁 Example flow
```
10:00 - Normal schedule: Covers open
12:00 - Shading active (sun protection)
14:00 - Heavy rain detected → Force-Close activated
        → Covers close immediately
        → Helper continues tracking: "shading should be active"
15:00 - Rain stops → Force-Close deactivated
        → Covers automatically return to shading position
18:00 - Evening close time
        → Covers close normally
```


## ☀️ Flexible Shading Logic - AND/OR Condition Builder

- **Powerful AND/OR condition builder**
  Decide exactly which shading conditions must all be met (AND) and which act as optional boosters (OR), so you can fine‑tune between conservative and aggressive sun protection without touching your sensor setup.

- **Independent START and END logic**
  Shading start and shading end have fully separate configuration paths, allowing strict criteria for starting shading and more relaxed logic for ending it – or the other way around.

- **Per‑condition on/off switches**
  Each individual shading trigger (e.g. azimuth, elevation, brightness, temperatures, weather) can be enabled or disabled independently, making it easy to experiment with different strategies or temporarily turn off single inputs.

- **Unified, robust retry behavior**
  Both shading start and shading end use a unified retry loop that periodically re‑checks conditions, providing smooth behavior in fast‑changing weather instead of getting stuck or flip‑flopping.

- **Timeouts to prevent endless waiting**
  New maximum duration settings for start and end ensure the automation never remains in an infinite “waiting for conditions” state; if the timeout is reached, the loop stops cleanly and waits for a fresh trigger.


## 🌡️ Forecast & Temperature Intelligence

- **Dedicated forecast inputs for clarity**
  Forecast handling is split into two clearly separated fields: one for standard weather entities (`weather.*`) and one for direct forecast temperature sensors (`sensor.*`), so you always know which source you are using.

- **Smart source priority**
  When both a weather entity and a forecast temperature sensor are configured, the direct sensor is preferred for faster updates and better performance, without extra API calls.

- **Configurable forecast mode (daily, hourly, or live)**
  Choose whether shading should rely on the daily forecast, the hourly forecast, or skip forecast data entirely and use current weather attributes, depending on how “future‑driven” you want your strategy to be.

- **Full hysteresis for all temperature paths**
  Hysteresis is applied not only to current temperature sensors 1 and 2, but also to forecast temperature, dramatically reducing unnecessary open/close cycles around threshold values.


## 📅 Calendar Integration for Time Control

- **New Feature:** Use Home Assistant calendars for flexible cover scheduling!

- ### What's New?
  - **Calendar Control Mode**: Select "Use a Home Assistant calendar" in Time Control Configuration
  - **Simple Event Titles**: Just create calendar events with titles:
    - "Open Cover" for daytime window
    - "Close Cover" for evening window
  - **Instant Response**: Automation reacts immediately when events start or end

- ### Benefits Over Time Scheduler:
  - **More Flexible**: Different times for each day of the week
  - **Exception Handling**: Easy to create holiday/vacation schedules
  - **No Reloads Needed**: Change times in calendar, automation adapts instantly
  - **Visual Planning**: See your schedule in calendar view
  - **Family Friendly**: Anyone can adjust schedule in calendar app

- ### Example Schedule:
  - **Monday-Friday**: "Open Cover" 06:00-20:00
  - **Saturday-Sunday**: "Open Cover" 08:00-22:00
  - **Vacation Week**: "Close Cover" all day (keep closed)


## 🔄 Tilt Position Control - Wait Until Idle Mode

- **New optional mode for reliable tilt control on Z-Wave devices**

- Added "Wait Until Idle" mode that monitors cover state before sending tilt commands, solving reliability issues with Z-Wave devices (e.g., Shelly Qubino Wave Shutter) that block tilt during motor movement.

- **New Configuration Options** (Tilt Position Settings):
  - **Tilt Wait Mode**: "Fixed Delay" (default) or "Wait Until Idle"
  - **Tilt Wait Timeout**: Maximum wait time (default: 30s)

- **Benefits**:
  - Reliable tilt without manual delay tuning
  - Fully backward compatible
  - Timeout protection with warning logs


## ✨ Seasonal Sun Elevation Adaptation / Dynamic Sun Elevation

- **Problem solved:** Fixed sun elevation thresholds don't work optimally year-round. In winter the sun stays lower, in summer higher. With fixed values your covers open/close at the wrong solar times.

- **Solution:** Optional template sensors automatically adapt thresholds to the season. Thanks, Zanuuu, for this idea in issue #285.
  - **Sun Elevation Up Sensor (Dynamic)** – Optional sensor for seasonal opening thresholds
    - Cover opens when **current sun elevation is higher** than the sensor value
    - Example: Sensor = 2.5° → Opens when sun rises above 2.5°
  - **Sun Elevation Down Sensor (Dynamic)** – Optional sensor for seasonal closing thresholds
    - Cover closes when **current sun elevation is lower** than the sensor value
    - Example: Sensor = 0.5° → Closes when sun sets below 0.5°

- New guide with step-by-step instructions: [Dynamic Sun Elevation Guide](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/DYNAMIC_SUN_ELEVATION.md)

- **Benefits**:
  - No more DST adjustments – No manual changes needed when clocks shift
  - Year-round optimization – Covers open/close at consistent solar times
  - Set and forget – Configure once, works automatically forever
  - Smooth transitions – Gradual threshold changes throughout the year


## 🧱 Stability & Hysteresis Improvements

- **Brightness hysteresis to avoid flicker**
  A new brightness hysteresis value prevents the cover from opening and closing repeatedly when light levels hover just above or below your thresholds, protecting both comfort and hardware.

- **Consistent hysteresis on start and end**
  Temperature hysteresis is now applied to both start and end conditions for all configured sensors, making shading decisions much more stable at the edges of your comfort band.

- **Smarter shading end detection**
  Shading end conditions are checked periodically until they remain stable over the configured waiting period or a timeout is reached, so shading does not end prematurely just because of a short‑lived fluctuation.


## 🐛 Contact Sensor Race Condition
- When multiple contact sensors changed state simultaneously (e.g., window sensor + lock sensor within milliseconds), mode: single would block the second trigger, causing it to be lost. This led to incorrect lockout protection behavior where covers could close despite active lockout sensors, potentially locking users out. (Fixed #225)


## ⚡ Resident Mode Fix & Code Refactoring
- **Resident Mode: Cover opens correctly after resident leaves**
  Fixed issue (#174) where cover remained closed when resident left room during daytime with all opening conditions met.
  Cover now evaluates time window and environmental conditions (brightness, sun) when resident leaves.
  Prevents unwanted opening during evening/night hours (after time_down_early).


## 🏖️ Awning & Sunshade Support

- CCA now supports now **awnings and sunshades** with inverted position logic!

  ### Configuration Examples

  #### Roller Shutter (Standard)
  ```yaml
  Cover Type: Blind / Roller Shutter
  Open Position: 100%  # Fully up
  Shading Position: 25%  # Partially down
  Close Position: 0%  # Fully down
  ```

  #### Awning (Inverted)
  ```yaml
  Cover Type: Awning / Sunshade
  Open Position: 0%  # Retracted
  Shading Position: 75%  # Extended for shade
  Close Position: 100%  # Fully extended
  ```


- **Removed: Shading End Behavior parameter**
The parameter `shading_end_behavior` has been removed. Covers now always return to `open_position` when shading ends (fully up for blinds, retracted for awnings).


-  **Important for Existing Users**
  If you upgrade from an older CCA version:
  - **Blinds/Shutters**: Select "Blind / Roller Shutter" (default)
  - **No more changes needed** to your existing configuration


## 📍 Flexible Position Source Support

- **Works with more cover types**
  CCA now supports covers that don't use the standard `current_position` attribute.

- **New Position Settings:**
  - **Position Source Type**: Choose how your cover reports its position
    - Standard `current_position` (default)
    - Alternative `position` attribute
    - External sensor
  - **Custom Position Sensor**: Use any sensor for position tracking

- **When to use:**
  - Your cover doesn't show positions in CCA
  - Manual changes aren't detected
  - You have custom position sensors


## 🛠️ Reliability, Fixes & Internal Optimizations

- **Fix for `current_tilt_position` errors**
  Roller blind setups that support tilt no longer produce errors when reading or using the `current_tilt_position` attribute. (#284)

- **Safe handling when end conditions change**
  If shading end conditions change during the waiting time, the retry logic is reset properly while shading itself remains active, preventing stuck or half‑finished states.

- **Cleaner state handling at midnight**
  The nightly reset also clears the newly introduced `pending` and `end‑pending` shading states to start each day with a clean slate.

- **Protection against stale pending states**
  An additional safety check at the OPEN branch can clear pending shading states older than one hour (currently commented out, ready for advanced users who want this safeguard).

- **Stronger “force” trigger safeguards**
  Force triggers are cross‑checked with internal `_force_disabled` flags to avoid conflicting commands and race conditions between different features.

- **More robust JSON initialization**
  JSON helper usage has been hardened by adding `|default` values for shading and status fields, making the automation more resilient against missing data.

- **Refined shading end behavior with prevent‑options**
  The internal logic for ending shading was reworked so that “prevent opening/closing” options are always respected, avoiding unwanted movements when opening is intentionally blocked.

- **Reduced internal duplication**
  Repeated calls to `as_timestamp(now()) | round(0)` have been replaced with a shared `ts_now` variable, improving readability and slightly reducing processing overhead.

- **Variables refactoring:**
  Consolidated 80+ flag variables into maintainable dictionaries. No functional changes.


## ⏰ Time Early and Time Late can now be identical for both Open and Close

- **Change:** Both Early and Late times can now be set to the same value (e.g., Time Up Early and Time Up Late both at 07:00, or Time Down Early and Time Down Late both at 22:00) to guarantee opening/closing at that exact time, regardless of environmental conditions.

- **Previous behavior:** With different Early and Late times, covers opened/closed at the early time as soon as conditions were met—even when Brightness/Sun Elevation were disabled.

- **Migration:**
  - For fixed opening/closing times without early triggering: Set both Early and Late times to identical values
  - For flexible opening/closing (early when conditions met, late as fallback): Keep Early before Late and enable Brightness/Sun Elevation


## ⚠️ Breaking Changes & Migration

- **New parameter for shading start retries**
  The old `shading_start_behavior` has been replaced by `shading_start_max_duration`, giving you fine‑grained control over how long the blueprint should keep retrying shading start conditions.
  - Previous presets map approximately as follows:
    - `"trigger_reset"` → `0` (no periodic retry, stop immediately)
    - `"trigger_periodic"` → `3600–7200` seconds (1–2 hours)

- **Minor change with “Immediate end by sun position” option**
  The parameter *End Sun Shading – Immediately When Out Of Range* (`is_shading_end_immediate_by_sun_position`) has been removed; please update your configuration accordingly. Parameter update required!

- **Removed: Shading End Behavior**
  Parameter `shading_end_behavior` removed. Covers always return to `open_position` after shading ends.

- **Removed: Time Schedule Helper**
  Parameter 'time_schedule_helper' removed.

- **Clean‑up for manual YAML users**
  If you maintain your automation YAML manually, remove the deprecated variables `shading_start_behavior` and `is_shading_end_immediate_by_sun_position` to keep your configuration aligned with the new logic.


## 🆕 New Tool: Online Configuration Validator

- Added a web-based YAML validator to help users validate configurations before deployment.

  - **URL**: https://hvorragend.github.io/ha-blueprints/validator/
  - **Features**:
    - Validates parameter names and detects typos (with suggestions)
    - Detects deprecated parameters with migration guidance
    - Validates position values based on cover type (blind/awning)
    - Checks shading condition configuration (AND/OR logic)
    - Validates time ordering and calendar setup
    - Shows which parameters are using blueprint defaults
    - Client-side processing (no data sent to servers)
    - Works offline after initial load

- ## 🎯 Why This Tool?

  The CCA internal config check ran inside the blueprint during automation execution, which:
  - Slowed down testing and debugging
  - Required reloading automations to see results
  - Mixed validation output with automation logs

- The new validator:
  - Runs on-demand only when needed
  - Provides instant visual feedback
  - Helps before you deploy changes


## ✅ Config Check Refactoring

- Organized 80+ validation checks into 19 logical sections with clear headers
- Enhanced error messages with more specific language and actionable guidance
- Improved code formatting for consistency (uniform indentation, better line lengths)
- Simplified template expressions (cleaner negation syntax, removed redundant parentheses)
