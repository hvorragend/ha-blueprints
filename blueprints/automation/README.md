# ☀️ Cover Control Automation (CCA)

**Comprehensive Home Assistant Blueprint for Intelligent Cover Control**

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://community-assets.home-assistant.io/original/4X/d/7/6/d7625545838a4970873f3a996172212440b7e0ae.svg
)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fhvorragend%2Fha-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fcover_control_automation.yaml)

**Resources:**
- 🗣️ [Community Discussion](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539)
- 📚 [Full Changelog](CHANGELOG.md)
- 📦 [Configuration Validator](https://hvorragend.github.io/ha-blueprints/validator/)
- ❓ [FAQ & Troubleshooting](FAQ.md)
- 📖 [Time Control Visualization](TIME_CONTROL_VISUALIZATION.md)
- 📖 [Dynamic Sun Elevation Guide](DYNAMIC_SUN_ELEVATION.md)

**Support Development:**
🙏 [PayPal Donation](https://www.paypal.com/donate/?hosted_button_id=NQE5MFJXAA8BQ) | 🙏 [Buy me a Coffee](https://buymeacoffee.com/herr.vorragend)

---

## ✨ Key Features

### 📍 **Time Control & Scheduling**
- **Flexible Time Input**: Traditional time-based opening/closing with workday/non-workday support
- **Calendar Integration**: Create "Open Cover" / "Close Cover" events in Home Assistant calendars for visual, family-friendly scheduling
- **Early/Late Triggers**: Separate early and late times for flexible opening/closing windows
- **Identical Times Support**: Can set early and late times to identical values for guaranteed exact timing

### ☀️ **Advanced Sun Shading / Sun Protection**
- **Flexible AND/OR Logic Builder**: Customize which shading conditions must ALL be met (AND) vs which act as optional boosters (OR)
- **Independent START/END Configuration**: Separate logic for starting and ending shading with dedicated retry timeouts
- **Multi-Condition Support**:
  - ☀️ Sun position (azimuth & elevation)
  - 🔅 Light brightness/illuminance
  - 🌡️ Temperature sensors (indoor/outdoor/forecast)
  - 🌦️ Weather forecasts (daily/hourly/current conditions)
  - 📊 Per-condition on/off switches
- **Hysteresis Support**: Prevents rapid on/off cycling with configurable hysteresis for all temperature-based triggers
- **Unified Retry Logic**: Periodic condition checks with timeout protection for stable behavior

### 📅 **Dynamic Sun Elevation Adaptation**
- **Seasonal Auto-Adjustment**: Optional template sensors automatically adapt elevation thresholds to the season
- **No Manual DST Adjustments**: Covers open/close at consistent solar times year-round
- **Smooth Transitions**: Gradual threshold changes throughout the year

### 🪟 **Ventilation Management**
- **Window State Detection**: Automatically responds to tilted (partial) and fully opened windows
- **Lockout Protection**: Prevents accidental closure during ventilation (prevents residents getting locked in)
- **Flexible Ventilation Positioning**: Optional delay after window closes, support for higher positions
- **Integration with Shading**: Can transition from shading to ventilation when window tilts
- **Race Condition Protection**: Handles multiple simultaneous sensor changes safely

### 🎯 **Cover Type Support**
- **Blinds/Roller Shutters**: Standard logic (0% = closed down, 100% = open up)
- **Awnings/Sunshades**: Inverted logic (0% = retracted, 100% = extended)
- **Automatic Position Logic Adaptation**: Blueprint adapts comparison logic based on cover type
- **Transparent for End Users**: Position values work intuitively for each cover type

### 🖐️ **Manual Override Intelligence**
- **Smart Detection**: Recognizes manual cover adjustments automatically
- **Respects User Decisions**: Honors manual adjustments for configurable timeout period (default 1 hour)
- **Automatic Resume**: Automation resumes after timeout or manual reset
- **Persistent Status Tracking**: Maintains state across Home Assistant restarts via Cover Status Helper

### 🧱 **Tilt Position Control**
- **Multi-Stage Support**: Up to 4 elevation-based tilt positions for optimal shading angles
- **Z-Wave Compatibility**: "Wait Until Idle" mode for devices that block tilt during motor movement
- **Optional Reposition**: Can close blinds before tilting for accurate positioning
- **Flexible Configuration**: Fixed delay or dynamic wait until idle with timeout protection

### 🏠 **Resident Detection & Sleep Schedules**
- **Privacy Protection**: Closes covers when resident goes to sleep
- **Flexible Waking Logic**: Can open covers when resident wakes based on environmental conditions
- **Selective Feature Control**: Choose which features (open/close/shading/ventilation) are allowed per resident

### 🚀 **Force Functions & Emergency Control**
- **Weather Protection**: Force-close for rain, force-open for wind/frost
- **Background State Tracking**: Automatically returns to target position when force is disabled
- **Real-Time Status Updates**: Helper continues tracking target state even during force functions
- **All Position Types**: Return-to-background works for open, close, shading, and ventilation
- **Safeguard Checks**: Only one force function can be active simultaneously

### 🔌 **Flexible Position Source Support**
- **Multiple Position Attributes**: Works with `current_position`, `position`, or custom sensors
- **Alternative Position Tracking**: Use external sensors when cover doesn't report positions
- **Automatic Detection**: Handles missing attributes gracefully

### ✅ **Extensive Configuration Validation**
- **Online Configuration Validator**: Web-based tool to validate YAML before deployment
- **80+ Validation Checks**: Organized into 19 logical sections with clear headers
- **Client-Side Processing**: Privacy-friendly - no data sent to external servers
- **Instant Feedback**: Get actionable error messages and migration guidance
- **In-Blueprint Validation**: Optional basic plausibility check during execution

---

## 🚀 Quick Start (5 Steps)

1. **Create a Helper**: Set up a text input helper with **minimum 254 characters** (Settings → Devices & Services → Helpers)
2. **Select Your Cover**: Choose the blind or shutter to automate
3. **Enable Features**: Activate the features you need (morning opening? Sun protection? Ventilation mode?)
4. **Configure Basics**: Set opening/closing times and connect your sensors
5. **Test & Refine**: Run the automation and adjust thresholds as needed

---

## 📋 Essential Prerequisites

### Required
- Home Assistant **2024.10.0** or higher
- Text Helper with **minimum 254 characters** (for advanced features)
- Cover entity with `current_position` attribute (or alternative position source)
- `sun.sun` entity enabled for sun-based features

### Important Configuration Rules
- ⏰ **Time ordering**: `time_up_early` < `time_up_late` (and non-workday variants)
- 📍 **Position hierarchy (Blinds)**: `open_position` > `ventilate_position` > `close_position`
- 📍 **Position hierarchy (Awnings)**: `open_position` < `ventilate_position` < `close_position`
- ☀️ **Sun values**: `azimuth_start` < `azimuth_end`, `elevation_min` < `elevation_max`
- 🔅 **Brightness values**: `brightness_start` > `brightness_end`
- 💬 **Resident sensor**: Must be binary (on/off, true/false only)

---

## 🧪 Debugging with Traces

Traces show exactly what happened when an automation ran. They're invaluable for troubleshooting.

### Enable Extended Trace Storage

Add to your automation YAML (optional, for up to 20 traces):
```yaml
trace:
  stored_traces: 20
```

### How to Access Traces

1. Go to **Settings → Automations & Scenes**
2. Click on your CCA automation
3. Select the **Traces** tab
4. Click on a trace to view execution details
5. Use arrow symbols to navigate between steps
6. Look for your expected trigger in the trigger table below

### What Traces Show

- **Trigger**: Which trigger fired the automation
- **Conditions**: Whether each condition was true/false
- **Actions**: Which actions were executed and in what order
- **Variables**: Calculated values at each step

### When You Don't Need Traces

Manual position change triggers (`t_manual_*`) are usually not the issue. If problems exist, look at the trigger **before** the manual detection trigger. Manual triggers are reaction events, not causation events.

### Sharing Traces for Support

Since the forum doesn't support `.json` uploads, use these services:

| Service | Account Required | Notes |
|---------|------------------|-------|
| [Pastebin](https://pastebin.com) | ✅ For "Unlisted" | Syntax highlighting for JSON |
| [GitHub Gist](https://gist.github.com) | ❌ Optional | Ideal for structured files |
| [Hastebin](https://hastebin.com) | ❌ | Fast & simple |
| [0bin](https://0bin.net) | ❌ | End-to-end encrypted |
| [file.io](https://www.file.io) | ❌ | Auto-deletes after download |

**To share via Pastebin:**
1. Download the trace JSON from Home Assistant
2. Go to https://pastebin.com
3. Paste the entire JSON content
4. Set Syntax Highlighting to `json`
5. Set Exposure to `Unlisted`
6. Click "Create New Paste"
7. Share the generated link

---

## 📬 Tips for Creating Helpful Support Requests

When posting on the community forum:

1. **Include your automation YAML** (exported from your Home Assistant instance)
2. **Provide the trace file** (especially for failed runs) - use one of the services above
3. **Describe expected vs actual behavior** clearly
4. **Focus on one problem per post** - easier to troubleshoot that way
5. **Check the changelog** - your issue may already be fixed in a newer version

---

## 🛎️ Trigger Overview

| Trigger | Function | When It Fires |
|---------|----------|---------------|
| `t_open_1` | Opening | Early opening time reached |
| `t_open_2` | Opening | Late opening time reached |
| `t_open_4` | Opening | Brightness above threshold for duration |
| `t_open_5` | Opening | Sun elevation above threshold for duration |
| `t_open_6` | Opening | Resident wakes up (leaves sleeping state) |
| `t_close_1` | Closing | Early closing time reached |
| `t_close_2` | Closing | Late closing time reached |
| `t_close_4` | Closing | Brightness below threshold for duration |
| `t_close_5` | Closing | Sun elevation below threshold for duration |
| `t_close_6` | Closing | Resident goes to sleep |
| `t_contact_tilted_changed` | Ventilation | Window tilted state changed |
| `t_contact_opened_changed` | Ventilation | Window opened state changed |
| `t_shading_start_pending_*` | Shading | Shading conditions being evaluated |
| `t_shading_start_execution` | Shading | Shading conditions confirmed, execution time |
| `t_shading_tilt_*` | Shading | Tilt position adjustment based on sun elevation |
| `t_shading_end_pending_*` | Shading | End conditions being evaluated |
| `t_shading_end_execution` | Shading | End conditions confirmed, execution time |
| `t_force_enabled_*` | Force | Force function activated |
| `t_force_disabled_*` | Force | Force function deactivated (return to background) |
| `t_manual_position` | Manual | Manual cover position change detected |
| `t_manual_tilt` | Manual | Manual tilt change detected |
| `t_reset_fixedtime` | Override Reset | Manual override timeout reached (fixed time) |
| `t_reset_timeout` | Override Reset | Manual override timeout reached (duration-based) |
| `t_calendar_event_start` | Calendar | Calendar event started |
| `t_calendar_event_end` | Calendar | Calendar event ended |

---

## 📋 Cover Status Helper - JSON Structure

The Cover Status Helper is a text input that stores the current cover state as JSON. It tracks what the automation intends to do, even when force functions are active.

### JSON Structure

```json
{
  "open": {"a": 1, "t": 1234567890},
  "close": {"a": 0, "t": 1234567890},
  "shading": {"a": 1, "t": 1234567890, "p": 0, "q": 0},
  "vpart": {"a": 0, "t": 1234567890},
  "vfull": {"a": 0, "t": 1234567890},
  "manual": {"a": 0, "t": 1234567890},
  "v": 5,
  "t": 1234567890
}
```

### Field Meanings

| Field | Description | Active Values | Notes |
|-------|-------------|----------------|-------|
| **open** | Cover is open or was last opened | 0/1 | Timestamp when state changed |
| **close** | Cover is closed or was last closed | 0/1 | Timestamp when state changed |
| **shading** | Cover is in shading mode | 0/1 | Active state, p=pending start, q=pending end |
| **shading.p** | Shading start pending (waiting) | 0 or timestamp | Unix timestamp of when to execute |
| **shading.q** | Shading end pending (waiting) | 0 or timestamp | Unix timestamp of when to execute |
| **vpart** | Partial ventilation (window tilted) | 0/1 | Timestamp when activated |
| **vfull** | Full ventilation/lockout (window open) | 0/1 | Timestamp when activated |
| **manual** | Manual operation detected | 0/1 | Timestamp when detected |
| **v** | Version number | 5 | Allows format upgrades |
| **t** | Last global status change | Unix timestamp | Overall helper update time |

### Common State Scenarios

| Scenario | open | close | shading | vpart | vfull | Description |
|----------|------|-------|---------|-------|-------|-------------|
| Cover is open | 1 | 0 | 0 | 0 | 0 | Normal daytime state |
| Cover is closed | 0 | 1 | 0 | 0 | 0 | Normal nighttime state |
| Shading active | 1 | 0 | 1 | 0 | 0 | Sun protection engaged |
| Shading + pending open | 1 | 0 | 1 | 0 | 0 | Waiting for shading to end |
| Window tilted (ventilation) | 1 | 0 | 0 | 1 | 0 | Partial opening for air flow |
| Window open (lockout) | 1 | 0 | 0 | 0 | 1 | Full opening + lockout protection |
| Manual adjustment | * | * | * | * | * | Depends on what was adjusted |

---

## 🎓 Understanding Cover Types

### Blinds / Roller Shutters (Standard)
- **0% = Fully Closed** (down)
- **100% = Fully Open** (up)
- **Intermediate positions** = Partially open

Position hierarchy: `open (100) > shading (25) > ventilate (30) > close (0)`

Example configuration:
```
Open Position: 100%
Shading Position: 25%
Ventilate Position: 30%
Close Position: 0%
```

### Awnings / Sunshades (Inverted)
- **0% = Fully Retracted** (closed)
- **100% = Fully Extended** (open)
- **Intermediate positions** = Partially extended

Position hierarchy: `open (0) < ventilate (25) < shading (75) < close (100)`

Example configuration:
```
Open Position: 0%
Shading Position: 75%
Close Position: 100%
```

**Note:** The blueprint automatically adjusts all comparison logic based on the selected cover type. You don't need to worry about inversion - just set positions intuitively for your hardware.

---

## ✅ Troubleshooting Checklist

- [ ] Cover has `current_position` attribute (or alternative source configured)
- [ ] Helper has minimum 254 characters length
- [ ] Sun entity (`sun.sun`) is enabled and working
- [ ] All required sensors are available and returning valid values
- [ ] Time values are in correct order (early < late)
- [ ] Position values follow hierarchy rules
- [ ] Resident sensor (if used) is binary (on/off or true/false)
- [ ] No multiple force functions active simultaneously
- [ ] Calendar events (if used) have correct titles
- [ ] Blueprint is version 2024.10.0 or higher
- [ ] Checked the online validator for configuration errors

---

## 📺 Screenshots

![CCA Automation Configuration UI](https://github.com/user-attachments/assets/c213d5ec-f1d4-4830-8e4d-43bc7f46cf44)

![CCA Shading Configuration](https://github.com/user-attachments/assets/e89777fc-73e8-4d79-a01e-e85e36c3450c)

---

## 📝 License & Attribution

This blueprint is open-source. When modifying or redistributing:
- Maintain attribution to the original author
- Link to the original [GitHub repository](https://github.com/hvorragend/ha-blueprints)
- Respect all license terms

⚠️ **Copies created via "Take Control"** are not officially supported. Custom modifications may prevent technical support.

 