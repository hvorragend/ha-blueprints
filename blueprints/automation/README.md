# ☀️ Cover Control Automation (CCA)

**Comprehensive Home Assistant Blueprint for Intelligent Cover Control**

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://community-assets.home-assistant.io/original/4X/d/7/6/d7625545838a4970873f3a996172212440b7e0ae.svg
)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fhvorragend%2Fha-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fcover_control_automation.yaml)

**Resources:**
- 🗣️ [Community Discussion](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539)
- 📚 [Full Changelog](CHANGELOG.md)
- 📦 [Configuration Validator](https://hvorragend.github.io/ha-blueprints/validator/)
- 🔍 [Trace Analyzer](https://hvorragend.github.io/ha-blueprints/trace-analyzer/)
- 🔄 [Trace Compare](https://hvorragend.github.io/ha-blueprints/trace-compare/)
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
- **Hybrid Scheduling**: Combine time-based triggers with calendar integration for maximum flexibility
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
- **Last-Wins Priority**: If multiple force functions are active, the most recently activated one takes precedence

### ⏸️ **Force Pause (Manual/Auto Toggle)**
- **Suspend all cover movements** via an `input_boolean` or `switch` while the automation keeps tracking state in the background
- **Instant resume**: When you turn the pause off, the cover immediately drives to the correct target position — no waiting for the next trigger
- **Superior to global conditions**: Unlike a global `condition:`, pause does not freeze the helper, so state stays in sync and the cover catches up the moment you re-enable automation

### 🔌 **Flexible Position Source Support**
- **Multiple Position Attributes**: Works with `current_position`, `position`, or custom sensors
- **Alternative Position Tracking**: Use external sensors when cover doesn't report positions
- **Automatic Detection**: Handles missing attributes gracefully

### ⚡ **Performance & Reliability**
- **RF Interference Prevention**: Configurable fixed and random delays to prevent radio interference when controlling multiple covers
- **Race Condition Protection**: Handles multiple simultaneous sensor changes safely (e.g., ventilation + shading triggers)
- **Smart State Tracking**: Helper integration maintains state persistently across Home Assistant restarts

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

 
