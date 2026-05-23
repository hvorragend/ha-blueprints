# :rocket: CCA 2026.05.24 — New State Machine, Priority Cascade, Force Pause & 30+ Bug Fixes

This is the biggest CCA update since the initial release — a **complete architecture overhaul** of the automation engine, combined with powerful new features and months of stability fixes.

**What's new at a glance:**
- :brain: **New State Machine v6** with a clearly defined 7-layer Priority Cascade
- :package: **Mandatory JSON Helper v6** with automatic migration from v5
- :pause_button: **Force Pause** — suspend all movements while keeping state in sync
- :gear: **AND/OR operators** for brightness & sun elevation conditions
- :notebook: **Optional Logbook** entries for debugging without trace limits
- :wrench: **30+ bug fixes** across shading, force functions, ventilation, manual override & more
- :warning: **Behavior change**: BASE=OPN now beats VENT in the priority cascade

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://community-assets.home-assistant.io/original/4X/d/7/6/d7625545838a4970873f3a996172212440b7e0ae.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fhvorragend%2Fha-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fcover_control_automation.yaml)

---

## :warning: Breaking Changes & Migration

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
| `time_control: time_control_disabled` | Uncheck `time_control_enabled` in `auto_options` | :warning: Legacy (still works, but deprecated) |
| Brightness & Sun Elevation operator in Sun Elevation section | Moved to Automation Options section | :white_check_mark: No |

**Backward compatible:** Existing automations without `time_control_enabled` in `auto_options` continue to work as before.

### Removed Parameters

The following parameters have been removed — please update your configuration:

- `shading_start_behavior` → replaced by `shading_start_max_duration` (in seconds, e.g. 3600)
- `shading_end_behavior` → covers now always return to `open_position` when shading ends
- `is_shading_end_immediate_by_sun_position` → removed

### Helper Schema Cleanup

The shading-pending state is now type-safe: a single `pnd` enum (`non` / `beg` / `end`) plus `ts.due` (fire time) and `ts.arm` (retry anchor). Helper version remains v6 — **auto-migration handles everything**.

**For custom card templates / external tooling:** Use the new keys (`pnd`, `ts.due`, `ts.arm`). See the updated card examples in [`examples/`](https://github.com/hvorragend/ha-blueprints/tree/main/examples).

---

## :brain: New Architecture: State Machine v6 & Priority Cascade

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

## :sparkles: New Features

### :pause_button: Force Pause — Suspend All Movements

A new optional `force_pause` input (`input_boolean` or `switch`) allows suspending all automatic cover movements while keeping the background state fully up to date.

- While active: all triggers fire, helper is updated — only movement is blocked
- When turned off: cover **immediately drives** to the correct target position
- **Superior to the global condition:** the global condition freezes state tracking, so when you re-enable, the helper is stale and the cover only catches up at the next scheduled trigger (possibly hours away). Force Pause solves this.

**Use case:** A manual/automatic toggle switch. Flip it off to pause, flip it back on → instant correct position.

### :gear: AND/OR Operator for Brightness & Sun Elevation

The combination of *Brightness* and *Sun Elevation* conditions is now configurable via `brightness_sun_operator`:

- **OR (default):** Cover opens/closes when **either** condition crosses the threshold (matches previous behavior)
- **AND:** Cover opens/closes only when **both** conditions cross their thresholds — useful to avoid premature triggers

When only one sensor is enabled, the operator is irrelevant.

### :notebook: Optional Logbook Entries

A new opt-in **Logging** section (`enable_logbook`) writes a structured logbook entry on every automation run:

- Trigger ID, effective state, current cover position
- Window / resident / force sensor states
- Full `update_values` JSON written to the helper
- Selected branches attach extra context (shading retry, pending timing)

**Default: off.** Toggle on while debugging — the 5-trace limit in Home Assistant no longer caps your ability to reconstruct what the cover did over the course of a day.

### :house: Keep Cover Open on Full-to-Tilt Transition

New option `ventilation_keep_open_on_full_to_tilt`: when a window changes from fully opened to tilted, the cover stays at the open position instead of lowering to the ventilation position. Useful for terrace doors where you come back inside, tilt the door, and don't want the cover moving down.

### :family: Resident Handling Redesign

Resident control was completely redesigned. A single smart trigger now handles both arrival and departure, including all environment checks and resident flags. When a force function is deactivated, the cover automatically returns to the correct state (open, closed, shading, or ventilation) without manual intervention.

### :new: Forecast Temperature Triggers

Dedicated state-change triggers for forecast temperature sensors (`t_shading_start_pending_6` / `t_shading_end_pending_6`) ensure immediate reaction when forecast temperature values change — previously forecast temperature was only evaluated on time-based triggers.

---

## :wrench: Bug Fixes

### Force Functions

- **Force features blocking themselves** ([#339](https://github.com/hvorragend/ha-blueprints/issues/339)): Force Open/Close/Ventilation/Shading failed to move the cover because `is_cover_movement_blocked.any` was already `true` when the force was active. Force triggers now bypass this check.
- **Covers closing during ventilation despite active force** ([#337](https://github.com/hvorragend/ha-blueprints/issues/337)): Ventilation recovery now properly respects active force features. Force checks are centralized via YAML anchors.
- **Force recovery ignoring resident sensor** ([#332](https://github.com/hvorragend/ha-blueprints/issues/332)): Force recovery now validates resident conditions before returning to background state.
- **Force operations incorrectly updating helper** ([#318](https://github.com/hvorragend/ha-blueprints/issues/318)): Force operations now preserve the background helper state instead of overwriting it.
- **Force priority: "Last Wins"** ([#342](https://github.com/hvorragend/ha-blueprints/pull/342), [#377](https://github.com/hvorragend/ha-blueprints/pull/377)): When multiple forces are active, the last activated one wins. Disabling one force correctly falls back to the remaining active force.
- **Cover incorrectly closes when window closes during Force-Ventilation** ([#445](https://github.com/hvorragend/ha-blueprints/issues/445)): The contact handler now respects the active force.
- **Background state always kept up to date during force functions**: The automation continues to track the scheduled state (e.g. "close at 18:00") while force is running, ensuring correct return after force ends.

### Shading

- **Shading never starts with `weather_attributes` forecast mode** ([#399](https://github.com/hvorragend/ha-blueprints/issues/399)): The weather condition was read from an attribute instead of the entity state, returning `None` permanently. Fixed.
- **Shading-start retry aborts on a fresh day** ([#408](https://github.com/hvorragend/ha-blueprints/issues/408), [#416](https://github.com/hvorragend/ha-blueprints/issues/416)): Duration check used yesterday's timestamp as anchor. A dedicated retry anchor (`ts.arm`) now ensures the configured retry window is honored correctly.
- **Cover stuck in shading when conditions change rapidly** ([#395](https://github.com/hvorragend/ha-blueprints/issues/395)): Stale pending state blocked all subsequent shading-end attempts. Pending is now cleared correctly.
- **Shading-start pending stuck outside shading window** ([#430](https://github.com/hvorragend/ha-blueprints/issues/430)): Pending armed inside the shading window was never cleared when the window moved past. Fixed.
- **Shading not triggering after cover opens** ([#325](https://github.com/hvorragend/ha-blueprints/issues/325)): Shading conditions are now re-evaluated when covers open.
- **Manual override ignored when shading state is stale** ([#447](https://github.com/hvorragend/ha-blueprints/issues/447)): The "Manual: unknown position" branch now clears stale shading state and pending.

### Ventilation & Window Sensors

- **Window-opened sensor now always takes priority over tilted**: Every branch explicitly checks that *opened* is not active before processing *tilted*. Lockout always beats ventilation.
- **Lockout works independently of `resident_allow_ventilation`**: Lockout protection is now a standalone safety feature. Only the tilted sub-branch requires `resident_allow_ventilation`.
- **Incorrect open status when window tilted during closing time**: The tilted-closing branch now correctly sets the base state to closed.
- **Base state not updated when closing trigger fires with tilted window**: The CLOSE handler now always records the base-state change, fixing `prevent_multiple_times` for the next day.

### Manual Override

- **`man` flag cleared in non-movement blocks**: Manual override was prematurely cleared after triggers that didn't even drive the cover. `man: 0` is now only written when the cover actually moves.
- **Manual position detection trigger** ([#326](https://github.com/hvorragend/ha-blueprints/issues/326)): Replaced non-functional template trigger with separate state triggers for each position source. Manual changes are now reliably detected within 60 seconds.
- **Manual override flag not cleared after auto-driven tilt** ([#425](https://github.com/hvorragend/ha-blueprints/issues/425)): `man` flag is now correctly cleared when the automation drives the cover.

### Environment Sensors

- **Cover opens at early time without waiting for sensor threshold** ([#436](https://github.com/hvorragend/ha-blueprints/issues/436)): With only one sensor enabled + OR operator, the disabled sensor short-circuited the check to `true`. Both opening and closing now branch explicitly on which sensors are enabled.
- **Sun elevation triggers respect fixed/dynamic/hybrid modes**: Triggers `t_open_5` and `t_close_5` now correctly implement all three modes.
- **Brightness, temp1, temp2 trust their pending trigger**: A transient `invalid_states` no longer overrides a sensor that just fired the pending trigger.

### Resident Handling

- **Resident leaving correctly restores shading/ventilation position**: Previously the cover sometimes closed instead.
- **Resident leaving with window open no longer falls through to shading** (lockout takes priority).
- **Resident handler reads live sensor state**, not the helper's stale `res` value — eliminating race conditions during transitions.
- **Force recovery respecting environmental conditions** ([#310](https://github.com/hvorragend/ha-blueprints/issues/310), [#312](https://github.com/hvorragend/ha-blueprints/issues/312)): Covers now check sun elevation and brightness before reopening after force ends.

### Other Fixes

- **Ventilation-after-shading blocked by stale lockout gate** ([#426](https://github.com/hvorragend/ha-blueprints/issues/426)): Removed incorrect guard.
- **Dead helper write in Force-Shade activation** ([#427](https://github.com/hvorragend/ha-blueprints/issues/427)): Removed unused `ts.shd` write.
- **Redundant cover movements prevented** ([#344](https://github.com/hvorragend/ha-blueprints/issues/344)): Cover no longer moves when already at target position.
- **Shading state persistence**: The shading state is now correctly saved to the helper across reboots.
- **Defensive fallback for missing weather forecast configuration**: Missing data is treated as "no forecast available" instead of producing Jinja2 errors.
- **Silent failures after v5 → v6 upgrade**: Fixed manual override timeout, shading start pending, and shading end conditions.

---

## :hammer_and_wrench: Tool Updates

### CCA Configuration Validator
- Recognizes all new parameters (`sun_elevation_mode`, `force_pause`, `auto_options`, `brightness_sun_operator`, `enable_logbook`, `ventilation_keep_open_on_full_to_tilt`, etc.)
- Sun elevation validation rewritten with full mode-aware support (Fixed / Dynamic / Hybrid)
- New check: warns when required elevation sensors are missing for Dynamic/Hybrid mode

### Trace Analyzer v2.0
Fully updated for the new Branch 0–11 structure and v6 helper format. Supports v6 internal, v6 compact, and v5 legacy display. Includes new runtime variables and an aligned shading deep-dive view.

### Trace Compare v2.0
Updated to Branch 0–11 structure, extended trigger explanations, and same v6/v5 multi-format support.

---

## :books: Documentation Updates

New FAQ sections:
- **State Hierarchy** — detailed explanation of how `effective_state` is resolved through the priority cascade
- **Force State Architecture** — when persisted helper state vs. real-time entity state is used
- **State Transition Matrix** — maps every trigger to its branch and resulting helper changes
- **Shading Pending Mechanism** — documents the two-phase trigger flow for delayed shading start
- **Window Sensor Priority** — why *opened* always beats *tilted*

New dashboard card examples (in [`examples/`](https://github.com/hvorragend/ha-blueprints/tree/main/examples)):
- **CCA Status Tile Card** — compact tile-style visualization
- **Flex-Table-Card** — full-row visualization of all helper fields

New guide:
- **Window-sun-angle aware shading via Force Shading** — step-by-step guide for window-orientation-aware shading

---

## :link: Resources

- :book: [Full Changelog](https://hvorragend.github.io/ha-blueprints/CHANGELOG)
- :question: [FAQ & Troubleshooting](https://hvorragend.github.io/ha-blueprints/FAQ)
- :wrench: [Configuration Validator](https://hvorragend.github.io/ha-blueprints/validator/)
- :mag: [Trace Analyzer](https://hvorragend.github.io/ha-blueprints/trace-analyzer/)
- :chart_with_upwards_trend: [Trace Compare](https://hvorragend.github.io/ha-blueprints/trace-compare/)
- :sunny: [Dynamic Sun Elevation Guide](https://hvorragend.github.io/ha-blueprints/DYNAMIC_SUN_ELEVATION)
- :clock1: [Time Control Visualization](https://hvorragend.github.io/ha-blueprints/TIME_CONTROL_VISUALIZATION)
- :bug: [Report Issues](https://github.com/hvorragend/ha-blueprints/issues)

---

**Enjoying CCA?** :pray: [Buy me a Coffee](https://buymeacoffee.com/herr.vorragend) or tip via [PayPal](https://www.paypal.com/donate/?hosted_button_id=NQE5MFJXAA8BQ). Thank you! :raised_hands:
