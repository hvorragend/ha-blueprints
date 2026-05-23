# 🚀 CCA 2026.05.23 — New State Machine, Priority Cascade, Force Pause & 30+ Bug Fixes

This is the biggest CCA update since the initial release — a **complete architecture overhaul** of the automation engine, combined with powerful new features and months of stability fixes.

**What's new at a glance:**
- 🧠 **New State Machine v6** with a clearly defined 7-layer Priority Cascade
- 📦 **Mandatory JSON Helper v6** with automatic migration from v5
- ⏸️ **Force Pause** — suspend all movements while keeping state in sync
- ⚙️ **AND/OR operators** for brightness & sun elevation conditions
- ☀️ **Flexible Shading Logic** — AND/OR condition builder with independent START/END configuration
- 📅 **Calendar Integration** — schedule covers via Home Assistant calendars
- 🛝 **Awning & Sunshade Support** — inverted position logic for awnings
- 📝 **Optional Logbook** entries for debugging without trace limits
- 🪟 **Keep Cover Open** on full-to-tilt window transition
- 🔌 **Flexible Position Source** — support for alternative position attributes and external sensors
- 🧱 **Tilt Wait Until Idle** — reliable tilt control for Z-Wave devices
- ✨ **Dynamic Sun Elevation** — seasonal auto-adjustment via template sensors
- 🔧 **30+ bug fixes** across shading, force functions, ventilation, manual override & more
- ⚠️ **Behavior change**: BASE=OPN now beats VENT in the priority cascade

---

## ⚠️ Breaking Changes & Migration

### Priority Cascade: BASE=OPN now beats VENT

When the time schedule is in the *open* window (`bas=opn`) and a window is tilted, the cover now **opens fully** instead of stopping at the ventilation position.

| Situation | Before | After |
|-----------|--------|-------|
| Daytime (`bas=opn`), window tilted, no shading/privacy | Cover at ventilation position (e.g. 50%) | **Cover fully open (100%)** |
| Closing time (`bas=cls`), window tilted | Cover at ventilation position | Cover at ventilation position *(unchanged)* |
| Shading active, window tilted | Cover at ventilation position | Cover at ventilation position *(unchanged)* |

**Rationale:** A tilted window expresses ventilation intent — and a fully open cover provides the maximum possible airflow. VENT now acts as a *floor*: it only kicks in when the cover would otherwise close, shade, or be restricted from opening.

**To restore previous behavior:** Close the window or remove the time schedule (so `bas` never reaches `opn`).

### Automation Options Consolidated

All enable/disable decisions are now centrally located in the **Automation Options** section (`auto_options`):

| Before | After | Breaking? |
|--------|-------|-----------|
| `time_control: time_control_disabled` | Uncheck `time_control_enabled` in `auto_options` | ⚠️ Legacy (still works, but deprecated) |
| Brightness & Sun Elevation operator in Sun Elevation section | Moved to Automation Options section | ✅ No |

New `auto_options` values:
```yaml
auto_options:
  - auto_up_enabled          # Morning opening (existing)
  - auto_down_enabled        # Evening closing (existing)
  - time_control_enabled     # NEW — enables time-based triggers
  - auto_brightness_enabled  # Brightness-based opening/closing
  - auto_sun_enabled         # Sun elevation-based opening/closing
  - auto_ventilate_enabled   # Ventilation mode (existing)
  - auto_shading_enabled     # Sun protection / shading (existing)
```

**Backward compatible:** Existing automations without `time_control_enabled` in `auto_options` continue to work as before.

### Removed Parameters

The following parameters have been removed — please update your configuration:

- `shading_start_behavior` → replaced by `shading_start_max_duration` (in seconds, e.g. 3600)
- `shading_end_behavior` → covers now always return to `open_position` when shading ends
- `is_shading_end_immediate_by_sun_position` → removed
- `time_schedule_helper` → removed

### Helper Schema Cleanup

The shading-pending state is now type-safe: a single `pnd` enum (`non` / `beg` / `end`) plus `ts.due` (fire time) and `ts.arm` (retry anchor). Helper version remains v6 — **auto-migration handles everything**.

A defensive cleanup also fires whenever the stored `ts.*` contains keys that are no longer part of the schema — this preserves all live state and resets any pending to idle.

**For custom card templates / external tooling:** Use the new keys (`pnd`, `ts.due`, `ts.arm`). See the updated card examples in [`examples/`](https://github.com/hvorragend/ha-blueprints/tree/main/examples).

---

## 🧠 New Architecture: State Machine v6 & Priority Cascade

The automation now resolves the cover's target state through a clearly defined **priority cascade**, evaluated on every run. Higher-priority states always win:

| Priority | State | When active |
|----------|-------|-------------|
| 1 – highest | **FORCE** | Any force function is active (Force Open/Close/Shade/Ventilate) |
| 2 | **LOCKOUT** | Window is fully open — cover must not close |
| 3 | **BASE=OPN** | Time schedule = open, no privacy/shading/restriction → fully open |
| 4 | **VENT** | Window tilted **and** cover would otherwise be below ventilation height |
| 5 | **PRIVACY** | Resident present + closing trigger configured → close |
| 6 | **SHADING** | Sun shading is active |
| 7 – lowest | **BASE=CLS** | Time schedule = close |

This replaces the previous implicit state resolution and makes the cover's behavior **predictable in every situation**, including when multiple states are active simultaneously.

### Mandatory JSON Helper v6

The **Cover Status Helper** (`input_text`, minimum 254 characters) is now **required**. It stores all relevant state: base state, shading status, window sensor state, force function, resident presence, manual override flag, and timestamps for every state transition.

- **Existing helper users:** Automatic migration from v5 to v6 on first run — no manual action needed
- **New users:** Create an `input_text` helper with at least 254 characters (Settings → Devices & Services → Helpers)

---

## ✨ New Features

### ⏸️ Force Pause — Suspend All Movements

A new optional `force_pause` input (`input_boolean` or `switch`) allows suspending all automatic cover movements while keeping the background state fully up to date.

- While active: all triggers fire, helper is updated — only movement is blocked
- When turned off: cover **immediately drives** to the correct target position
- **Superior to the global condition:** the global condition freezes state tracking, so when you re-enable, the helper is stale and the cover only catches up at the next scheduled trigger (possibly hours away). Force Pause solves this.

**Use case:** A manual/automatic toggle switch. Flip it off to pause, flip it back on → instant correct position.

### ☀️ Flexible Shading Logic — AND/OR Condition Builder

A powerful AND/OR condition builder for shading start and end conditions:

- **Independent START and END logic**: Separate configuration paths for starting and ending shading
- **Per-condition on/off switches**: Each individual shading trigger (azimuth, elevation, brightness, temperatures, weather) can be enabled or disabled independently
- **Unified retry behavior**: Both shading start and end use a unified retry loop with configurable timeout protection
- **Maximum duration settings**: Prevent endless "waiting for conditions" states

### ⚙️ AND/OR Operator for Brightness & Sun Elevation

The combination of *Brightness* and *Sun Elevation* conditions is now configurable via `brightness_sun_operator`:

- **OR (default):** Cover opens/closes when **either** condition crosses the threshold (matches previous behavior)
- **AND:** Cover opens/closes only when **both** conditions cross their thresholds — useful to avoid premature triggers

When only one sensor is enabled, the operator is irrelevant.

### 📅 Calendar Integration for Time Control

Use Home Assistant calendars for flexible cover scheduling:

- **Calendar Control Mode**: Select "Use a Home Assistant calendar" in Time Control Configuration
- **Simple Event Titles**: Create calendar events with titles "Open Cover" / "Close Cover"
- **Instant Response**: Automation reacts immediately when events start or end
- **Benefits over Time Scheduler**: Different times per weekday, holiday/vacation schedules, visual planning in calendar view, family-friendly

### 🛝 Awning & Sunshade Support

CCA now supports **awnings and sunshades** with inverted position logic:

- **Blinds/Roller Shutters (Standard)**: 0% = closed down, 100% = open up
- **Awnings/Sunshades (Inverted)**: 0% = retracted, 100% = extended
- Automatic position logic adaptation based on cover type
- Transparent for end users: position values work intuitively for each cover type

### 📝 Optional Logbook Entries

A new opt-in **Logging** section (`enable_logbook`) writes a structured logbook entry on every automation run:

- Trigger ID, effective state, current cover position
- Window / resident / force sensor states
- Full `update_values` JSON written to the helper
- Selected branches attach extra context (shading retry, pending timing)

**Default: off.** Toggle on while debugging — the 5-trace limit in Home Assistant no longer caps your ability to reconstruct what the cover did over the course of a day.

### 🪟 Keep Cover Open on Full-to-Tilt Transition

New option `ventilation_keep_open_on_full_to_tilt`: when a window changes from fully opened to tilted, the cover stays at the open position instead of lowering to the ventilation position. Useful for terrace doors where you come back inside, tilt the door, and don't want the cover moving down.

### 🔌 Flexible Position Source Support

CCA now supports covers that don't use the standard `current_position` attribute:

- **Position Source Type**: Choose between `current_position`, `position` attribute, or external sensor
- **Custom Position Sensor**: Use any sensor for position tracking
- Automatic detection and graceful handling of missing attributes

### 🧱 Tilt Position Control — Wait Until Idle Mode

New optional mode for reliable tilt control on Z-Wave devices (e.g., Shelly Qubino Wave Shutter):

- **Wait Until Idle**: Monitors cover state before sending tilt commands
- **Tilt Wait Timeout**: Maximum wait time (default: 30s) with warning logs
- Fully backward compatible — existing "Fixed Delay" mode remains the default

### ✨ Dynamic Sun Elevation Adaptation

Optional template sensors automatically adapt sun elevation thresholds to the season:

- **Three modes**: Fixed (default), Dynamic (sensor-only), Hybrid (sensor + offset)
- **No more DST adjustments**: Covers open/close at consistent solar times year-round
- **Set and forget**: Configure once, works automatically forever

See the [Dynamic Sun Elevation Guide](DYNAMIC_SUN_ELEVATION.md) for setup instructions.

### ⏰ Identical Early and Late Times

Both Early and Late times can now be set to the same value (e.g., Time Up Early and Time Up Late both at 07:00) to guarantee opening/closing at that exact time, regardless of environmental conditions.

### 🏠 Resident Handling Redesign

Resident control was completely redesigned. A single smart trigger now handles both arrival and departure, including all environment checks and resident flags. When a force function is deactivated, the cover automatically returns to the correct state (open, closed, shading, or ventilation) without manual intervention.

### 🌡️ Forecast & Temperature Intelligence

- **Dedicated forecast inputs**: Separated fields for standard weather entities (`weather.*`) and direct forecast temperature sensors (`sensor.*`)
- **Smart source priority**: When both are configured, the direct sensor is preferred
- **Configurable forecast mode**: Daily, hourly, or live (current weather attributes)
- **Forecast temperature triggers**: Dedicated state-change triggers (`t_shading_start_pending_6` / `t_shading_end_pending_6`) for immediate reaction

---

## 🔧 Bug Fixes

### Force Functions

- **Force features blocking themselves** ([#339](https://github.com/hvorragend/ha-blueprints/issues/339)): Force Open/Close/Ventilation/Shading failed to move the cover because `is_cover_movement_blocked.any` was already `true`. Force triggers now bypass this check.
- **Covers closing during ventilation despite active force** ([#337](https://github.com/hvorragend/ha-blueprints/issues/337)): Ventilation recovery now properly respects active force features. Force checks centralized via YAML anchors.
- **Force recovery ignoring resident sensor** ([#332](https://github.com/hvorragend/ha-blueprints/issues/332)): Force recovery now validates resident conditions before returning to background state.
- **Force operations incorrectly updating helper** ([#318](https://github.com/hvorragend/ha-blueprints/issues/318)): Force operations now preserve the background helper state.
- **Force priority: "Last Wins"** ([#342](https://github.com/hvorragend/ha-blueprints/pull/342), [#377](https://github.com/hvorragend/ha-blueprints/pull/377)): When multiple forces are active, the last activated one wins. Disabling one force correctly falls back to the remaining active force.
- **Cover incorrectly closes when window closes during Force-Ventilation** ([#445](https://github.com/hvorragend/ha-blueprints/issues/445)): The contact handler now respects the active force.
- **Background state always kept up to date during force functions**: The automation continues to track the scheduled state while force is running.
- **Force-disabled recovery respecting environmental conditions** ([#310](https://github.com/hvorragend/ha-blueprints/issues/310), [#312](https://github.com/hvorragend/ha-blueprints/issues/312)): Covers now check sun elevation and brightness before reopening after force ends.

### Shading

- **Shading never starts with `weather_attributes` forecast mode** ([#399](https://github.com/hvorragend/ha-blueprints/issues/399)): Weather condition was read from attribute instead of entity state. Fixed.
- **Shading-start retry aborts on a fresh day** ([#408](https://github.com/hvorragend/ha-blueprints/issues/408), [#416](https://github.com/hvorragend/ha-blueprints/issues/416)): A dedicated retry anchor (`ts.arm`) now ensures the configured retry window is honored correctly.
- **Cover stuck in shading when conditions change rapidly** ([#395](https://github.com/hvorragend/ha-blueprints/issues/395)): Stale pending state blocked all subsequent shading-end attempts. Pending is now cleared correctly.
- **Shading-start pending stuck outside shading window** ([#430](https://github.com/hvorragend/ha-blueprints/issues/430)): Pending armed inside the shading window was never cleared when the window moved past. Fixed.
- **Shading not triggering after cover opens** ([#325](https://github.com/hvorragend/ha-blueprints/issues/325)): Shading conditions are now re-evaluated when covers open.
- **Manual override ignored when shading state is stale** ([#447](https://github.com/hvorragend/ha-blueprints/issues/447)): The "Manual: unknown position" branch now clears stale shading state and pending.
- **Pending shading-start silent exit**: Added explicit `stop:` in `default:` branch so the trace clearly reports the termination reason.
- **Shading state persistence**: Correctly saved to the helper across reboots.
- **Defensive fallback for missing weather forecast**: Missing data treated as "no forecast available" instead of Jinja2 errors.

### Ventilation & Window Sensors

- **Window-opened sensor always takes priority over tilted**: Every branch explicitly checks that *opened* is not active before processing *tilted*. Lockout always beats ventilation.
- **Lockout works independently of `resident_allow_ventilation`**: Lockout is now a standalone safety feature. Only the tilted sub-branch requires `resident_allow_ventilation`.
- **Incorrect open status when window tilted during closing time**: The tilted-closing branch now correctly sets the base state to closed.
- **Base state not updated when closing trigger fires with tilted window**: The CLOSE handler now always records the base-state change, fixing `prevent_multiple_times` for the next day.
- **Contact sensor race condition** ([#225](https://github.com/hvorragend/ha-blueprints/issues/225)): When multiple contact sensors changed state simultaneously, `mode: single` could block the second trigger, causing incorrect lockout behavior. Fixed.
- **Window-tilted ventilation: missing guards added**: Several tilt-related branches now include guards preventing redundant or conflicting cover moves.
- **Ventilation-after-shading blocked by stale lockout gate** ([#426](https://github.com/hvorragend/ha-blueprints/issues/426)): Removed incorrect guard.

### Manual Override

- **`man` flag cleared in non-movement blocks**: Manual override was prematurely cleared after triggers that didn't drive the cover. `man: 0` is now only written when the cover actually moves.
- **Manual position detection trigger** ([#326](https://github.com/hvorragend/ha-blueprints/issues/326)): Replaced non-functional template trigger with separate state triggers. Manual changes reliably detected within 60 seconds.
- **Manual override flag not cleared after auto-driven tilt** ([#425](https://github.com/hvorragend/ha-blueprints/issues/425)): `man` flag is now correctly cleared when the automation drives the cover.

### Environment Sensors

- **Cover opens at early time without waiting for sensor threshold** ([#436](https://github.com/hvorragend/ha-blueprints/issues/436)): With only one sensor enabled + OR operator, the disabled sensor short-circuited the check to `true`. Both opening and closing now branch explicitly on which sensors are enabled.
- **Sun elevation triggers respect fixed/dynamic/hybrid modes**: Triggers `t_open_5` and `t_close_5` now correctly implement all three modes.
- **Brightness, temp1, temp2 trust their pending trigger**: A transient `invalid_states` no longer overrides a sensor that just fired the pending trigger.

### Resident Handling

- **Resident leaving correctly restores shading/ventilation position**: Previously the cover sometimes closed instead.
- **Resident leaving with window open no longer falls through to shading** (lockout takes priority).
- **Resident handler reads live sensor state**, not the helper's stale `res` value — eliminating race conditions.
- **Cover opens correctly after resident leaves** ([#174](https://github.com/hvorragend/ha-blueprints/issues/174)): Cover now evaluates time window and environmental conditions when resident leaves.

### Other Fixes

- **Redundant cover movements prevented** ([#344](https://github.com/hvorragend/ha-blueprints/issues/344)): Cover no longer moves when already at target position.
- **Dead helper write in Force-Shade activation** ([#427](https://github.com/hvorragend/ha-blueprints/issues/427)): Removed unused `ts.shd` write.
- **Silent failures after v5 → v6 upgrade**: Fixed manual override timeout, shading start pending, and shading end conditions.
- **`current_tilt_position` errors** ([#284](https://github.com/hvorragend/ha-blueprints/issues/284)): Roller blind setups with tilt no longer produce errors.
- **`prevent_multiple_times` flags respect manual intervention**: Automation will not retry if the user manually changed the cover position.
- **Opening incorrectly blocked** ([#354](https://github.com/hvorragend/ha-blueprints/issues/354)): A single permissive condition is now sufficient to allow opening.

---

## 🧱 Stability & Hysteresis Improvements

- **Brightness hysteresis**: New brightness hysteresis value prevents flicker when light levels hover near thresholds.
- **Consistent hysteresis on start and end**: Temperature hysteresis now applied to both start and end conditions for all sensors.
- **Smarter shading end detection**: Conditions checked periodically until stable over the waiting period, preventing premature shading end.

---

## 🛠️ Tool Updates

### CCA Configuration Validator
- Recognizes all new parameters (`sun_elevation_mode`, `force_pause`, `auto_options`, `brightness_sun_operator`, `enable_logbook`, `ventilation_keep_open_on_full_to_tilt`, etc.)
- Sun elevation validation rewritten with full mode-aware support (Fixed / Dynamic / Hybrid)
- New check: warns when required elevation sensors are missing for Dynamic/Hybrid mode
- 80+ validation checks organized into 19 logical sections with clear headers

### Trace Analyzer v2.0
Fully updated for the new Branch 0–11 structure and v6 helper format. Supports v6 internal, v6 compact, and v5 legacy display. Includes new runtime variables and an aligned shading deep-dive view.

### Trace Compare v2.0
Updated to Branch 0–11 structure, extended trigger explanations, and same v6/v5 multi-format support.

---

## 📚 Documentation Updates

New FAQ sections:
- **State Hierarchy** — detailed explanation of how `effective_state` is resolved through the priority cascade
- **Force State Architecture** — when persisted helper state vs. real-time entity state is used
- **State Transition Matrix** — maps every trigger to its branch and resulting helper changes
- **Shading Pending Mechanism** — documents the two-phase trigger flow for delayed shading start
- **Window Sensor Priority** — why *opened* always beats *tilted*
- **How does a force function work?** — moved from inline help into the FAQ

New dashboard card examples (in [`examples/`](https://github.com/hvorragend/ha-blueprints/tree/main/examples)):
- **CCA Status Tile Card** — compact tile-style visualization
- **Flex-Table-Card** — full-row visualization of all helper fields

New guides:
- **[Dynamic Sun Elevation Guide](DYNAMIC_SUN_ELEVATION.md)** — seasonal adaptation with template sensors
- **[Window-Sun-Angle Aware Shading](WINDOW_SUN_ANGLE.md)** — window-orientation-aware shading via Force Shading

---

## 📦 Helper Schema Update — `ts.arm`

The v6 JSON helper schema gained one additional field: **`ts.arm`** — a dedicated retry-sequence anchor timestamp used by the shading-start and shading-end retry logic. Automatically initialized on first run; no manual action required.

---

## 🛠️ Internal Improvements

- **Variables refactoring**: Consolidated 80+ flag variables into maintainable dictionaries
- **Reduced internal duplication**: Shared `ts_now` variable replaces repeated `as_timestamp(now()) | round(0)` calls
- **Stronger force trigger safeguards**: Cross-checked with internal `_force_disabled` flags
- **More robust JSON initialization**: Added `|default` values for shading and status fields
- **Cleaner midnight reset**: Nightly reset also clears pending and end-pending shading states
