**Note:** Previous changes are archived here: [CHANGELOG_OLD.md](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/CHANGELOG_OLD.md).

# 🚀 CCA 2026.03.alpha – New State Machine & Mandatory JSON Helper

## 🏗️ New Architecture: State Machine v6 & Mandatory JSON Helper

This release brings a **major internal overhaul** of the Cover Control Automation engine. While there are no new configuration options for you to set up, the improvements make the automation significantly more reliable, predictable, and easier to diagnose.

### 🔄 New State Machine with Priority Cascade

The automation now resolves the cover's target state through a clearly defined **5-level priority cascade**, evaluated on every run. Higher-priority states always win over lower ones:

| Priority | State | When active |
|----------|-------|-------------|
| 1 – highest | **Force** | Any force function is active (Force Open/Close/Shade/Ventilate) |
| 2 | **Lockout** | Window is fully open — cover must not close |
| 3 | **Ventilation** | Window is tilted — cover moves to ventilation position |
| 4 | **Shading** | Sun shading is active |
| 5 – lowest | **Base** | Time-based schedule (open/close time) |

This replaces the previous implicit state resolution that mixed multiple variables without a guaranteed evaluation order. The new cascade makes the cover's behavior predictable in every situation, including when multiple states are active at the same time.

### 📦 New JSON Helper v6 Schema — Now Mandatory

The **Cover Status Helper (`input_text`)** has been redesigned with a compact, versioned JSON schema (v6). This helper is now **required** for the automation to function correctly — it can no longer be omitted.

The helper stores all relevant state information: the current base state, shading status, window sensor state, active force function, resident presence, manual override flag, and timestamps for every state transition.

**What this means for you:**
- If you were already using the helper, it will be **automatically migrated** from the old format (v5) to v6 on the first run — no manual action needed.
- If you were not using a helper yet, you now need to create one. See the blueprint documentation for setup instructions.

---

## 🔧 Bug Fixes

### Redundant cover movements prevented ([#344](https://github.com/hvorragend/ha-blueprints/issues/344))
The cover no longer moves when it is already at the target position or within the configured position tolerance range.

### Opening incorrectly blocked in some conditions ([#354](https://github.com/hvorragend/ha-blueprints/issues/354))
The check that determines whether the environment allows opening was using the wrong logic in certain configurations, unnecessarily blocking the cover. This has been fixed — a single permissive condition is now sufficient to allow opening.

### Silent failures after internal format upgrade (v5 → v6)
Several automation paths were silently broken after the helper format was upgraded:
- The manual override timeout reset was not working.
- Shading start pending triggers were permanently blocked.
- Shading end conditions were being evaluated too broadly, causing early shading end.

All three issues are now fixed.

### Shading timestamp always saved correctly
The timestamp of the last shading event was not being stored in the tilt-based shading path. This is now resolved across all code paths.

### Spurious shading end prevented
An issue where an invalid weather forecast could unintentionally trigger the end of sun shading has been fixed. Only valid conditions will now end shading.

### Shading state preserved during ventilation ([#338](https://github.com/hvorragend/ha-blueprints/issues/338))
When a window was tilted while shading was active, the shading state was lost and the cover would not return to shading after the window closed. The shading state is now correctly preserved throughout the ventilation phase.

### Force recovery respects resident status ([#332](https://github.com/hvorragend/ha-blueprints/issues/332))
When a force function was deactivated and the cover returned to its background state, the resident sensor status was sometimes ignored. This is now always checked before executing the recovery movement.

### Resident sensor race condition eliminated
When multiple simultaneous sensor signals (resident arriving and leaving) fired at the same time, actions were sometimes skipped entirely. A single intelligent trigger now handles both arrival and departure reliably in one unified flow.

### Cover no longer closes during active Force function
When a window closed (ending a ventilation phase), the cover could close even if Force Open was still active. This is now correctly prevented.

### Ventilation end respects resident presence
When auto-ventilation ends (window closes), the automation now checks for resident presence before deciding whether to close.

### Background state always kept up to date
Even when force functions are active, the automation continues to track what it *would* be doing in the background — e.g. "close at 18:00" while Force Open is running. This ensures a correct return to the scheduled state after force ends.

### Force priority: "Last Wins" for multiple simultaneous forces ([PR #342](https://github.com/hvorragend/ha-blueprints/pull/342))
When multiple force functions were active at the same time, the system behaved inconsistently. The rule is now clearly defined: **the last activated force function takes precedence**.

---

## ✨ New Features & Improvements

### Resident handling: arrival and departure in one trigger
Resident control was completely redesigned. A single smart trigger now handles both arrival and departure, including all environment checks and resident flags. This makes resident-based behavior far more reliable.

### Automatic return to background state after force ends
When a force function is deactivated, the cover automatically returns to the state the automation would have applied at that moment — open, closed, shading, or ventilation — without any manual intervention.

---

## 📚 Documentation

New sections added to the FAQ:
- **Force State Architecture** — explains when the persisted helper state vs. real-time entity state is used for force decisions.
- **State Transition Matrix** — maps every trigger to its branch and the resulting helper state changes.
- **Shading Pending Mechanism** — documents the two-phase trigger flow for delayed shading start.
- **Flex-Table-Card Visualization** — complete dashboard card configuration to display all internal helper fields.
- **State Hierarchy** — detailed explanation of the five state layers and how `effective_state` is resolved through the priority cascade.

---

## 🛠️ Tool Updates

### CCA Validator
- Now recognizes `sun_elevation_mode` and `enable_background_state_tracking` (previously flagged as unknown parameters).
- Sun elevation validation rewritten with full mode-aware support (Fixed / Dynamic / Hybrid).
- **New check:** The validator now explicitly checks if the required elevation sensors exist when using Dynamic or Hybrid sun elevation mode, warning you before deployment if they are missing.

### Trace Analyzer v2.0
Fully updated to match the new Branch 0–11 structure and the v6 helper format. Supports v6 internal, v6 compact, and v5 legacy display.

### Trace Compare v2.0
Updated to Branch 0–11 structure, extended trigger explanations, and same v6/v5 multi-format support as the Trace Analyzer.

---


# 🚀 CCA 2026.01.26 - Force Features Self-Blocking Fix

## 🔧 Bug Fixes

- **Fixed Force features blocking themselves** (#339): Force Open/Close/Ventilation/Shading features can now execute properly. Previously, these features failed to move the cover because `cover_move_action` and `tilt_move_action` checked `is_cover_movement_blocked.any`, which was already `true` when the force feature was active. The movement blocking condition now allows Force triggers to bypass the check using regex pattern `trigger.id is match('^t_force_')`, enabling force features to work as intended while maintaining protection for background automations.


---


# 🚀 CCA 2026.01.23 - Force Features & Ventilation Recovery Fix

## 🔧 Bug Fixes

- **Fixed covers closing during ventilation despite active force features** (#337): Ventilation recovery now properly respects force features (force-open, force-close, etc.). Previously, covers would close when windows closed even when force-open was still active. Force feature checks are now centralized in YAML anchors for consistent behavior across all branches.


---


# 🚀 CCA 2026.01.22 - Force Recovery Resident Sensor Fix

## 🔧 Bug Fixes

- **Fixed force recovery ignoring resident sensor status** (#332): Force recovery (BRANCH 12) now validates resident sensor conditions before returning to background state. Previously, when a force function was disabled, the cover could execute an invalid action if the resident sensor status had changed while the force function was active.

---


# 🚀 CCA 2026.01.14 - Force State Preservation Fix

## 🔧 Bug Fixes

- **Fixed force operations incorrectly updating helper status** (#318): Force operations (force-open, force-close, force-ventilate, force-shading) now preserve the background helper state instead of updating it. 

---


# 🚀 CCA 2026.01.12 - Window Tilted Closing Time Fix

## 🔧 Bug Fixes

- **Fixed incorrect open status when window is tilted during closing time**: The "Window tilted - Move to ventilation position" branch (inside BRANCH 1: CLOSE) now correctly sets `open=0, close=1` to reflect that this is a closing action redirected to ventilation position. Previously, it incorrectly set `open=1, close=0`, causing shutters to open instead of close when the window was closed in the morning after being tilted during evening hours.

- **Fixed shading state persistence**: The shading state is now correctly saved to the helper. Previously, this state was lost, preventing the cover from directly entering shading mode when opening the following morning.

---


# 🚀 CCA 2026.01.11 - Manual Position Trigger Fix

## 🔧 Bug Fixes

- **Fixed manual position detection trigger** (#326): Replaced non-functional template trigger with separate state triggers for each position source (current_position, position, custom sensor). Manual position changes are now reliably detected within 60 seconds.

---


# 🚀 CCA 2026.01.09 - Shading Trigger Fix

## 🔧 Bug Fixes

- **Fixed shading not triggering automatically after cover opens** (#325): Shading conditions are now correctly re-evaluated when covers open, ensuring shading activates when all conditions are met.

---


# 🚀 CCA 2026.01.06 - Forecast Temperature Trigger Coverage

## ✨ New Features

- **Added missing state triggers for Forecast Temperature condition**: The `cond_forecast_temp` condition now has dedicated state-change triggers (`t_shading_start_pending_6` and `t_shading_end_pending_6`) for immediate reaction when forecast temperature sensor values change. Previously, forecast temperature was only evaluated via time-based trigger or when other conditions triggered, which caused incomplete AND/OR logic evaluation.

- **Note for Weather Entity Users**: When using a weather entity for forecast temperature (without a dedicated sensor), the existing weather condition trigger (`t_shading_start_pending_5` / `t_shading_end_pending_4`) will fire on weather entity updates. The forecast temperature is then loaded and evaluated in the action sequence, providing indirect coverage for weather entity-based forecast temperature.

---


# 🚀 CCA 2026.01.02 - Sun Elevation Trigger Mode Support

## 🔧 Bug Fixes

- **Fixed sun elevation triggers to respect fixed/dynamic/hybrid modes**: Triggers `t_open_5` and `t_close_5` now correctly implement all three sun elevation modes (fixed, dynamic, hybrid) ensuring consistent threshold calculation across the automation.

---


# 🚀 CCA 2025.12.31 - Force Recovery Environment Check

## 🔧 Bug Fixes

- **Fixed helper status update during force-disabled states** (#312): Helper status is now correctly updated even when force functions (e.g., force-close) are active. This ensures the background state is properly tracked during forced states, allowing covers to return to the correct position when force functions are deactivated. Previously, the helper update condition was stricter than the cover movement condition, causing inconsistent state tracking.

- **Fixed force-disabled recovery respecting environmental conditions** (#310): Covers now check sun elevation and brightness before reopening after force-disabled state ends (e.g., rain protection). Time-based triggers at `time_up_late`/`time_down_late` continue to work as ultimate fallback regardless of conditions.

---


# 🚀 CCA 2025.12.30 - Sun Elevation Modes (Fixed/Dynamic/Hybrid)

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
