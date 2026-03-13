**Note:** Previous changes are archived here: [CHANGELOG_OLD.md](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/CHANGELOG_OLD.md).

# 🚀 CCA 2026.03.alpha - Final Fixes, Documentation & Tools Update

## 🔧 Bug Fixes

- **Fixed redundant cover movements** (closes #344): Cover no longer moves when it is already at the target position or within the configured position tolerance window. The `&cover_move_action` anchor now checks the current position before sending a command.

- **Fixed `environment_allows_opening` using incorrect AND logic** (fixes #354): The environment check now correctly uses OR logic — a single permissive condition is sufficient to allow opening. The previous AND logic caused covers to be blocked unnecessarily when only one of several environment conditions was met.

- **Fixed v5 schema remnants causing silent failures after v6 migration**: Several code paths still referenced old v5 JSON helper field names after the migration to the v6 compact schema:
  - `t_reset_timeout` trigger was checking obsolete `manual.t` / `manual.a` fields (v5) instead of `man` / `ts.man` (v6 compact) — the timeout reset was silently broken.
  - The global condition for shading start pending triggers was searching for `"shading"` (v5 key) instead of `"shd"` (v6 key) — all `t_shading_start_pending_*` triggers were permanently blocked by this condition.
  - `shading_end_or_result` was evaluating **all** shading end conditions instead of only the user-configured OR conditions, causing unexpected early shading end.

- **Fixed Branch 3 (Shading Tilt) not writing shade timestamp**: The `update_values` block was writing to key `t` (no-op) instead of `ts.shade`, so the last-shaded timestamp was never persisted from the tilt branch.

## ♻️ Internal Cleanup

- **Migrated remaining `service:` calls to `action:`**: 7 occurrences in YAML anchors updated to the current Home Assistant syntax.

- **Removed redundant `or:` wrappers**: Cleaned up 4 unnecessary single-element `or:` blocks in shading branches.

## 📚 Documentation Updates

- **Added Force State Architecture section to FAQ**: Explains the dual-source design — persisted helper state (background) vs. realtime entity reads (force gates) — and when each source is used.

- **Added State Transition Matrix to FAQ**: Maps each trigger to its corresponding branch and state changes in the helper, with full branch overview table (Branches 0–11).

- **Added Shading Pending Mechanism section to FAQ**: Documents the two-phase trigger flow for `t_shading_start_pending_*` triggers and the role of `ts.shs` as the pending indicator.

- **Added flex-table-card visualization example to FAQ**: Comprehensive card configuration showing how to display all 12 helper fields (status, target position, force overrides, resident/manual flags, timestamps) in a Home Assistant dashboard using `custom:flex-table-card`.

- **Added State Hierarchy documentation to FAQ**: Detailed explanation of the five state layers and how `effective_state` is computed through the priority cascade.

- **Fixed JSON helper schema table in FAQ**: Corrected field values that were documented incorrectly (`win` values `ptl`/`ful` → `tlt`/`opn`; `frc` value `ven` → `vnt`; removed incorrect `shd=2` pending state row).

## 🛠️ Tools Updates

- **CCA Validator updated to v2026.01.25**: Added `sun_elevation_mode` and `enable_background_state_tracking` to the set of known parameters (previously flagged as unknown). Rewrote `validateDynamicSunElevation()` with full mode-aware validation (fixed/dynamic/hybrid), including missing-sensor errors for dynamic mode and informational messages for fixed mode.

- **Trace Analyzer updated to v2.0** (For CCA Blueprint v2026.01.25+):
  - Branch definitions completely rewritten to match new Branch 0–11 structure (was 0–13)
  - Added new trigger IDs: `t_resident_update`, `t_shading_start_pending_6`, `t_shading_start_pending_7`, `t_shading_end_pending_6`
  - `formatHelperValue()` rewritten to support v6 internal, v6 compact, and v5 legacy formats
  - `renderHelperStatus()` rewritten with structured v6 field display (effective state panel, timestamps panel, v5 legacy fallback)

- **Trace Compare updated to v2.0** (For CCA Blueprint v2026.01.25+):
  - Branch definitions rewritten to match Branch 0–11 structure
  - `branchCounts` initialization loop corrected (was iterating 0–13, now 0–11)
  - Expanded trigger explanations for all current trigger IDs
  - `formatHelperValue()` updated with same v6/v5 multi-format support as Trace Analyzer

---


# Force Function Refactoring & State Guard Standardization

## ♻️ Internal Refactoring

- **Standardized `is_forced` checks across all branches** (PR #349): All action branches now include a unified `is_forced` guard to prevent cover movement while any force function is active. Previously only some branches included this check, leading to inconsistent behavior when force functions were enabled.

- **Simplified `force_allows_*` variables to realtime-only checks** (PR #350): Force permission variables (`force_allows_open`, `force_allows_close`, `force_allows_shade`, `force_allows_ventilate`) now evaluate only realtime entity state rather than a mix of persisted helper data and realtime reads. This removes a class of edge cases where stale helper data could incorrectly permit or block movements.

- **Removed obsolete force trigger pattern checks**: Leftover trigger-pattern matching from before the `force_allows_*` system was removed. All force gating is now consistently handled through the permission variables.

- **Renamed force permission variables for clarity** (PR #345): All internal force permission variables renamed:
  - `can_move_open` → `force_allows_open`
  - `can_move_close` → `force_allows_close`
  - `can_move_shade` → `force_allows_shade`
  - `can_move_ventilate` → `force_allows_ventilate`

- **Consolidated force trigger handling**: Multiple overlapping force trigger conditions were merged into a single coherent check per branch.

---


# State Machine v6 Architecture & Compact JSON Helper

This release is a major internal overhaul of the Cover Control Automation engine. The state machine was completely redesigned around a structured JSON helper schema with an explicit priority cascade for state resolution. There are no new user-facing configuration options; all changes are internal architecture improvements that improve reliability, debuggability, and correctness.

## 🏗️ New JSON Helper v6 Compact Schema

- **Redesigned compact schema for `input_text` helper**: The Cover Status Helper now stores all state in a compact, versioned JSON format (typically ~138 chars, well within the 208-char `input_text` limit). The schema replaces the loosely structured v5 format with explicit typed fields.

  **Top-level fields:**

  | Field | Values | Description |
  |-------|--------|-------------|
  | `bas` | `opn` / `cls` | Base state (time-triggered) |
  | `shd` | `0` / `1` | Shading active flag |
  | `win` | `cls` / `tlt` / `opn` | Window contact sensor state |
  | `frc` | `non` / `opn` / `cls` / `shd` / `vnt` | Active force function |
  | `res` | `0` / `1` | Resident present |
  | `man` | `0` / `1` | Manual override active |
  | `ts`  | sub-object | Timestamps for all state transitions |
  | `v`   | `6` | Schema version marker |
  | `t`   | Unix timestamp | Global last-updated timestamp |

  **Timestamp sub-keys (`ts.*`):**

  | Key | Description |
  |-----|-------------|
  | `ts.opn` | Last open transition |
  | `ts.cls` | Last close transition |
  | `ts.shd` | Last shade-active transition |
  | `ts.shs` | Shading start pending (non-zero = pending active) |
  | `ts.she` | Shading end pending (non-zero = end pending active) |
  | `ts.win` | Last window state change |
  | `ts.man` | Last manual override change |

  **Example compact JSON (138 chars):**
  ```json
  {"bas":"opn","shd":0,"win":"cls","frc":"non","res":0,"man":0,"ts":{"opn":0,"cls":0,"shd":0,"shs":0,"she":0,"win":0,"man":0},"v":6,"t":1738368000}
  ```

- **Automatic v5 → v6 migration**: Existing automations with the old v5 helper format are automatically detected (`helper_json` reads and converts) and the migrated v6 schema is persisted on the first helper update. No manual intervention required.

- **Internal long-form field names**: All internal blueprint variables continue to use readable long names (`base`, `shade`, `window`, `force`, `resident`, `manual`). Compact-to-long conversion happens in `helper_json` (read path); long-to-compact conversion happens in `helper_update` (write path). All `update_values` blocks are unchanged.

## ⚙️ New State Machine with Priority Cascade

- **`effective_state` replaces `state_current`**: The computed final cover state is now explicitly resolved by a 5-level priority cascade evaluated on every automation run:

  | Priority | State | Condition |
  |----------|-------|-----------|
  | 1 (highest) | **FORCE** | Any force function active (`frc != non`) |
  | 2 | **LOCKOUT** | Window fully open (`win = opn`) — prevents closing |
  | 3 | **VENTILATION** | Window tilted (`win = tlt`) — ventilation position |
  | 4 | **SHADING** | Shading active (`shd = 1`) |
  | 5 (lowest) | **BASE** | Time-based ground state (`bas = opn/cls`) |

- **Shading state preserved during ventilation**: When a window is tilted while shading is active, the `shd` flag is preserved. When the window closes again, the cover correctly returns to the shading position. Previously the shade state was lost on window events.

- **Base state always updated on time triggers**: Time-based branches (Opening/Closing) now unconditionally update the `bas` field in the helper. This ensures the background target state is always current, even when other overrides (force functions, manual) are active.

## ♻️ State Variable Refactoring

- **Removed legacy `state_current`** (PR #347): The old `state_current` variable has been completely removed from the blueprint. The `effective_state` variable (computed via the priority cascade) replaces it in all 80+ references.

- **Separated state resolution layers** (PR #346, #348): The monolithic `state_target` variable was split into distinct intermediate state variables to cleanly separate each layer of the cascade (force → lockout → ventilation → shading → base → resident modifier → manual override). The state resolution chain is now explicit and follows the documented priority order.

- **`ts_now` cleanup**: Consolidated all `as_timestamp(now()) | round(0)` calls into the shared `ts_now` variable (already introduced in 2025.12.27 refactoring) — removed remaining inline duplications.

## 🔄 Branch Restructuring

- **Cover Control branches renumbered for logical consistency**: Branches were reorganized to group related functionality and reflect the state machine priority order:

  | Branch | Name | Change |
  |--------|------|--------|
  | 0 | Opening | unchanged |
  | 1 | Closing | unchanged |
  | 2 | Shading Start | unchanged |
  | 3 | Shading Tilt | unchanged |
  | 4 | Shading End | unchanged |
  | 5 | Contact Sensor / Lockout | unchanged |
  | **6** | **Resident Update** | **NEW** — moved from Branch 13 (was simple helper update); now full bidirectional handler (see v2026.01.25) |
  | **7** | **Force Functions** | **MERGED** — was 4 separate branches (6: Force Open, 7: Force Close, 8: Force Shade, 9: Force Vent) |
  | 8 | Return After Force | was Branch 12 |
  | 9 | Manual Detection | was Branch 10 |
  | 10 | Reset Override | was Branch 11 |
  | 11 | Midnight Reset | was Branch 13 |

- **Force Functions consolidated into a single Branch 7**: Previously, Force Open, Force Close, Force Shade, and Force Ventilate each had their own trigger and action sequence (Branches 6–9). All four are now handled by a single unified branch with internal state routing via the `frc` helper field.

## 🔧 Bug Fixes

- **Fixed: preserve base state during ventilation** (closes #338): When auto-close was blocked by lockout protection or an open ventilation window, the `bas` field was incorrectly overwritten with `cls`. This caused covers to close prematurely after the window was closed and the ventilation state ended.

- **Fixed: unconditional helper updates for background state tracking**: Helper updates in `&helper_update` were previously guarded by conditions (gated on force function state), causing the background state to become stale whenever a force function was active. The helper is now always updated unconditionally, enabling reliable `Return After Force` recovery (Branch 8).

- **Fixed: force state logic — "Last Wins" for multiple simultaneous force functions** (PR #342): When multiple force functions were activated simultaneously or in rapid succession, the priority logic did not consistently apply. The last-activated force function now correctly takes precedence, with proper recovery defaults when a force function is deactivated.

- **Fixed: shade timestamp updates for all shade deactivation paths**: All code paths that deactivate shading (manual intervention, timeout, sensor condition change, forced override) now correctly write the `ts.shd` timestamp. Previously several paths skipped the timestamp update, causing inaccurate last-shaded values.

- **Fixed: resident arrival/departure logic errors**: Resident arrival handling had inverted boolean logic in some code paths. Permission variables (`can_open_with_resident`, `can_shade_with_resident`, `can_ventilate_with_resident`) are now consolidated into a single evaluation point for clarity and correctness.

- **Fixed: ventilation end respects resident presence**: When auto-ventilation ends (window closes), the cover now correctly checks resident presence before deciding whether to close. Previously ventilation end could close a cover that resident mode should have kept open.

---


# Resident Branch Refactoring

## 🔧 Bug Fixes

- **Fixed resident sensor race condition**: Resolved trigger conflict where `t_open_6` (resident leaving), `t_close_6` (resident arriving), and `t_resident_update` (resident status change) would fire simultaneously, causing no action to execute. Removed both dedicated triggers and replaced simple helper update (BRANCH 13) with comprehensive resident handler (BRANCH 15) that:
  - Always updates helper with new resident status (no blocking `stop:` statement)
  - Optionally opens cover when resident leaves (ON→OFF transition)
  - Optionally closes cover when resident arrives (OFF→ON transition)
  - Respects all environment checks and resident flags
  - Eliminates race condition through single trigger (`t_resident_update`) with intelligent bidirectional handling

- **Enhanced resident sensor force recovery** (#332): Added resident checks to force recovery logic to prevent covers from returning to positions that violate resident requirements. Uses existing computed flags (`can_open_with_resident`, `can_shade_with_resident`, `can_ventilate_with_resident`) for elegant 3-line solution.

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
