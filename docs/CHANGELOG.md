**Note:** Previous changes are archived here: [CHANGELOG_OLD.md](https://hvorragend.github.io/ha-blueprints/CHANGELOG_OLD).

# CCA 2026.05.29 V3

- 🐛 **Fix:** When a resident was present and shading conditions became true in the meantime (shading blocked by resident presence because `resident_allow_shading` was not configured), the cover opened normally after the resident left but shading never activated on that day — the sun-position template triggers only fire on FALSE→TRUE transitions and do not re-fire when conditions were already TRUE during residence. `resident_flags.allow_shade` is removed from the top-level "Check for shading start" conditions so the pending mechanism arms normally; the existing "Save shading state for the future" branch in the execution handler is extended with `OR not resident_flags.allow_shade`, so it saves `shd=1` alongside the already-handled `effective_state == 'cls'` case. The existing "Resident leaving: target SHADED" branch then drives to the shading position when the resident leaves.

---

# CCA 2026.05.29 V2

- 🐛 **Fix:** `ts.opn` no longer overwritten by the late opening trigger when the cover was already opened earlier the same day. The "Already in open position" branch now catches all cases where the cover is at open position with `effective_state=opn` — including the case where `bas=opn` and `ts.opn` is already from today. `ts.opn` is only refreshed when there is a real base-state transition or when the timestamp is from a previous day; otherwise the existing value is preserved. Additionally, the late trigger no longer redundantly drives the cover or clears the manual override ([#495](https://github.com/hvorragend/ha-blueprints/issues/495))

---

# CCA 2026.05.29

- 🐛 **Fix:** Shading never executed when pending-start (`pnd=beg`) armed before the opening time window and the opening trigger fired at window-start — the opening handler's "Shading detected" branch matched on `helper_state_pending_start`, cleared the pending state (`pnd=non`, `ts.due=0`) without driving the cover (because `effective_state != 'shd'` while `shd` was still `0`), causing the `t_shading_start_execution` trigger to be silently killed. The opening handler now defers to the execution trigger: a new "Opening skipped: Shading start pending" branch preserves `pnd`, `ts.due`, and `ts.arm`, updates only the base state (`bas=opn`, `ts.opn`), and lets the execution trigger fire 1 second later to handle the drive — including the correct retry/abort logic for manual overrides.

---

# CCA 2026.05.28 V2

- ✨ **Feature:** New input *"Independent Temperature Threshold"* (`shading_independent_temp`) for the *"Independent Shading via Temperature Comparison"* mode — previously this mode shared the same threshold as the normal forecast condition, causing both paths to be blocked simultaneously when the threshold wasn't met. The dedicated threshold can be set lower (e.g. 23 °C) while keeping a stricter value in the AND conditions, without either path interfering with the other ([#491](https://github.com/hvorragend/ha-blueprints/issues/491))
- 🔧 **Improvement:** Clarified selector label and description for *"Also trigger if Temperature Sensor 2 exceeds Forecast Temperature Value"* — the previous label implied a forecast-vs-sensor comparison but the actual logic checks whether Sensor 2 exceeds the (independent) threshold

---

# CCA 2026.05.28

- 🐛 **Fix:** Cover no longer closes when the window is closed while a resident is present but privacy-closing is not configured. The contact "window closed" handler treated any resident presence as a privacy-close trigger ("Return to open" required the resident to be absent; "Return to close" fired on mere presence). It now mirrors `effective_state`: privacy-close applies only when `resident_closing_enabled` is configured, or when opening is not permitted (`resident_allow_opening` unset). With `bas=opn` and no shading, the cover correctly returns to the open position after the window closes.

---

# CCA 2026.05.27 V2

- 🐛 **Fix:** Contact sensor "window closed" branches no longer destroy active shading pending phase (`pnd`, `ts.due`, `ts.arm`) — briefly opening and closing a door/window during shading-start or shading-end pending no longer prevents shading from executing ([#484](https://github.com/hvorragend/ha-blueprints/issues/484))
- 🐛 **Fix:** "Window closed" branches no longer fire spuriously when cover is at open position but was never in ventilation mode — removed overly broad `in_open_position` fallback from the "was ventilating before" OR condition ([#484](https://github.com/hvorragend/ha-blueprints/issues/484))
- 🐛 **Fix:** Shading end never triggered when only elevation (or only azimuth) was configured as end condition — the combined sun-position trigger `t_shading_end_pending_5` used OR logic for azimuth and elevation in a single template, so when azimuth left the range first (without meeting end conditions), the trigger stayed TRUE and never re-fired when elevation later dropped below threshold ([#483](https://github.com/hvorragend/ha-blueprints/issues/483))

---

# CCA 2026.05.27

- ✨ **Feature:** New ventilation option to disable the drive delay when ventilation starts (window opens/tilts) — useful for setups with many covers where a large fixed delay is needed for staggering, but single-cover ventilation reactions should be instant
- 🐛 **Fix:** Shading start pending armed before time window opens no longer aborts immediately — `ts.due` is now set to `max(now + waitingtime, window_start)`, ensuring execution fires after the window opens instead of aborting with only seconds elapsed of a multi-hour `max_duration` budget ([#475](https://github.com/hvorragend/ha-blueprints/issues/475))
- 🐛 **Fix:** Shading End never executed when using Calendar time control — `t_shading_end` triggers were missing from the `calendar.get_events` performance filter, causing `is_shading_allowed_window` to always evaluate to `false` ([#477](https://github.com/hvorragend/ha-blueprints/issues/477))

---

# CCA 2026.05.26

- 🐛 **Fix:** Contact handler incorrectly lowered cover to ventilation position when base state was open (`bas=opn`) and window transitioned from fully open to tilted ([#460](https://github.com/hvorragend/ha-blueprints/issues/460))
- 🔧 **Improvement:** `effective_state` now reads the window state from **live contact sensors** instead of the stale helper field — eliminates an entire class of stale-state bugs where `effective_state` returned `lock` instead of the correct cascade result during contact handler execution
- 🐛 **Fix:** Shading condition regex `"shd"\s*:\s*1` falsely matched the `ts.shd` timestamp (e.g. `"shd":1779701945`) inside the nested `ts` object, blocking all `t_shading_start_pending_*` triggers even when shading was inactive ([#467](https://github.com/hvorragend/ha-blueprints/issues/467))

---

# CCA 2026.05.25

- 🐛 **Fix:** Shading start pending blocked when status helper is uninitialized (e.g. after fresh setup)
- 🔧 **Trace Analyzer:** Shading Conditions Deep-Dive now shows independent temperature mode status — displays whether the temperature bypass is active and the effective start decision. This makes it visible when independent mode overrides the standard AND/OR conditions. ([#459](https://github.com/hvorragend/ha-blueprints/issues/459))

---

# 🚀 CCA 2026.05.24 — New State Machine, Priority Cascade, Force Pause & 30+ Bug Fixes

This is the biggest CCA update since the initial release — a **complete architecture overhaul** of the automation engine, combined with powerful new features and months of stability fixes.

**What's new at a glance:**
- 🧠 **New State Machine v6** with a clearly defined 7-layer Priority Cascade
- 📦 **Mandatory JSON Helper v6** with automatic migration from v5
- ⏸️ **Force Pause** — suspend all movements while keeping state in sync
- ⚙️ **AND/OR operators** for brightness & sun elevation conditions
- 📝 **Optional Logbook** entries for debugging without trace limits
- 🪟 **Keep Cover Open** on full-to-tilt window transition
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

**Backward compatible:** Existing automations without `time_control_enabled` in `auto_options` continue to work as before.

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

### ⚙️ AND/OR Operator for Brightness & Sun Elevation

The combination of *Brightness* and *Sun Elevation* conditions is now configurable via `brightness_sun_operator`:

- **OR (default):** Cover opens/closes when **either** condition crosses the threshold (matches previous behavior)
- **AND:** Cover opens/closes only when **both** conditions cross their thresholds — useful to avoid premature triggers

When only one sensor is enabled, the operator is irrelevant.

### 📝 Optional Logbook Entries

A new opt-in **Logging** section (`enable_logbook`) writes a structured logbook entry on every automation run:

- Trigger ID, effective state, current cover position
- Window / resident / force sensor states
- Full `update_values` JSON written to the helper
- Selected branches attach extra context (shading retry, pending timing)

**Default: off.** Toggle on while debugging — the 5-trace limit in Home Assistant no longer caps your ability to reconstruct what the cover did over the course of a day.

### 🪟 Keep Cover Open on Full-to-Tilt Transition

New option `ventilation_keep_open_on_full_to_tilt`: when a window changes from fully opened to tilted, the cover stays at the open position instead of lowering to the ventilation position. Useful for terrace doors where you come back inside, tilt the door, and don't want the cover moving down.

### 🏠 Resident Handling Redesign

Resident control was completely redesigned. A single smart trigger now handles both arrival and departure, including all environment checks and resident flags. When a force function is deactivated, the cover automatically returns to the correct state (open, closed, shading, or ventilation) without manual intervention.

---

## 🔧 Bug Fixes

### Force Functions

- **Force features blocking themselves** ([#339](https://github.com/hvorragend/ha-blueprints/issues/339)): Force triggers now bypass the `is_cover_movement_blocked.any` check.
- **Covers closing during ventilation despite active force** ([#337](https://github.com/hvorragend/ha-blueprints/issues/337)): Ventilation recovery now respects active force features.
- **Force recovery ignoring resident sensor** ([#332](https://github.com/hvorragend/ha-blueprints/issues/332)): Force recovery now validates resident conditions.
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

### Other Fixes

- **Redundant cover movements prevented** ([#344](https://github.com/hvorragend/ha-blueprints/issues/344)): Cover no longer moves when already at target position.
- **Dead helper write in Force-Shade activation** ([#427](https://github.com/hvorragend/ha-blueprints/issues/427)): Removed unused `ts.shd` write.
- **Silent failures after v5 → v6 upgrade**: Fixed manual override timeout, shading start pending, and shading end conditions.
- **Opening incorrectly blocked** ([#354](https://github.com/hvorragend/ha-blueprints/issues/354)): A single permissive condition is now sufficient to allow opening.

---

## 📦 Helper Schema Update — `ts.arm`

The v6 JSON helper schema gained one additional field: **`ts.arm`** — a dedicated retry-sequence anchor timestamp used by the shading-start and shading-end retry logic. Automatically initialized on first run; no manual action required.

---

## 🛠️ Tool Updates

### CCA Configuration Validator
- Recognizes all new parameters (`sun_elevation_mode`, `force_pause`, `auto_options`, `brightness_sun_operator`, `enable_logbook`, `ventilation_keep_open_on_full_to_tilt`, etc.)
- Sun elevation validation rewritten with full mode-aware support (Fixed / Dynamic / Hybrid)
- New check: warns when required elevation sensors are missing for Dynamic/Hybrid mode

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

New guide:
- **[Window-Sun-Angle Aware Shading](WINDOW_SUN_ANGLE.md)** — step-by-step guide for window-orientation-aware shading via Force Shading

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
  Perfect for users who want fully automated seasonal adaptation without manual intervention. Use with the [Dynamic Sun Elevation Guide](https://hvorragend.github.io/ha-blueprints/DYNAMIC_SUN_ELEVATION).

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
