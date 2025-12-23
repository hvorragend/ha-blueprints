# ❓ Cover Control Automation (CCA) - Frequently Asked Questions

This comprehensive FAQ covers the most common questions about Cover Control Automation. For additional support, visit the [CCA Community Thread](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539), check out the [Trace Analyzer](https://hvorragend.github.io/ha-blueprints/trace-analyzer/) for debugging, or report issues on [GitHub](https://github.com/hvorragend/ha-blueprints/issues).

---

## 📑 Table of Contents

1. [General Questions](#general-questions)
2. [Installation & Requirements](#installation--requirements)
3. [Configuration Basics](#configuration-basics)
4. [Time & Schedule Control](#time--schedule-control)
5. [Position Settings](#position-settings)
6. [Cover Types (Blinds vs. Awnings)](#cover-types-blinds-vs-awnings)
7. [Sun Shading & Sun Protection](#sun-shading--sun-protection)
8. [Ventilation & Contact Sensors](#ventilation--contact-sensors)
9. [Manual Override & Detection](#manual-override--detection)
10. [Resident Mode](#resident-mode)
11. [Force Functions & Emergency Control](#force-functions--emergency-control)
12. [Cover Status Helper](#cover-status-helper)
13. [Troubleshooting](#troubleshooting)
14. [Advanced Features](#advanced-features)
15. [Support & Debugging](#support--debugging)

---

## General Questions

### Q: What is Cover Control Automation (CCA)?

**A:** CCA is a comprehensive Home Assistant blueprint that automatically manages window coverings (roller shutters, blinds, awnings) based on time, sun position, weather conditions, and your preferences. It largely eliminates the need for manual adjustments.

---

### Q: Can I automate multiple covers with one automation?

**A:** Create **one automation per cover** for reliable results. While cover groups are technically possible, position detection becomes inaccurate when covers are at different positions simultaneously.

**Why one automation per cover?**
- Accurate position detection
- Individual manual override tracking
- Proper helper status management
- Easier debugging and troubleshooting

**Example:** If one cover in a group is at 100% and another at 0%, the group shows 50% - making position detection unreliable.

---

### Q: What are the main benefits of using CCA?

**A:** 
- ✅ **Intelligent automation** - Adapts to sun position, weather, and your routines
- ✅ **Manual override respect** - Recognizes and respects your manual adjustments
- ✅ **Lockout protection** - Won't close covers on open windows
- ✅ **Force functions** - Emergency control for rain, wind, frost protection
- ✅ **Extensive customization** - Fine-tune every aspect to your needs
- ✅ **Active development** - Regular updates based on community feedback

---

### Q: Can I trigger CCA manually?

**A:** ⚠️ **Not directly** - The automation runs on time triggers and sensor changes. However, force triggers allow manual override of automatic behavior when needed.

**Why not manual triggering?**
- CCA is event-driven (time, sensors, calendar)
- Manual "Run" button will not produce expected behavior
- Use force functions for manual control instead

---

## Installation & Requirements

### Q: What are the minimum requirements for using CCA?

**A:** 
- **Cover/shutter** must have a `current_position` attribute (or alternative position source)
- **Home Assistant** version **2024.10.0** or newer
- **Sun integration** (`sun.sun`) enabled and working correctly (for sun-based features)
- **Accurate location** - Correct latitude/longitude in Home Assistant configuration

---

### Q: Is the Helper mandatory for all features?

**A:** The helper is **required** for sun shading and ventilation features. Time-based opening/closing works with basic position detection alone, but you lose:
- Manual override protection
- Advanced state tracking
- Persistent status across restarts
- Ventilation mode functionality
- Sun shading capabilities

**How to create a helper:**
1. Go to Settings → Devices & Services → Helpers
2. Click "Create Helper" → Text
3. Set **Maximum length: 254 characters** (NOT the default 100!)
4. Name it (e.g., "CCA Status - Living Room")

---

### Q: Do I need special hardware or integrations?

**A:** No special hardware required! CCA works with:
- Any Home Assistant-integrated cover with position feedback
- Standard binary sensors (window contacts, motion sensors)
- Weather integrations (for forecast-based shading)
- Optional: Brightness sensors, temperature sensors

---

### Q: How do I install CCA?

**A:**
1. Click the import button in the [forum thread](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539) or use this URL:
   ```
   https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/cover_control_automation.yaml
   ```
2. Go to Settings → Automations & Scenes → Blueprints
3. The blueprint should appear automatically
4. Create a new automation using the CCA blueprint

---

## Configuration Basics

### Q: How do I set up the basic position settings?

**A:** For **Blinds/Roller Shutters** (Standard):
```yaml
Cover Type: Blind / Roller Shutter
Open Position: 100%      # Fully up
Shading Position: 25%    # Partially down for sun protection
Ventilate Position: 30%  # Slightly down for air flow
Close Position: 0%       # Fully down
Position Tolerance: 5%   # Acceptable variance
```

For **Awnings/Sunshades** (Inverted):
```yaml
Cover Type: Awning / Sunshade
Open Position: 0%        # Retracted
Shading Position: 75%    # Extended for sun protection
Close Position: 100%     # Fully extended
```

---

### Q: What are the important configuration rules?

**A:** 

**Time Settings:**
- `time_up_early` must be earlier than `time_up_late`
- `time_up_early_non_workday` must be earlier than `time_up_late_non_workday`
- `time_down_early` must be earlier than `time_down_late`
- `time_down_early_non_workday` must be earlier than `time_down_late_non_workday`
- ✅ NEW: Times can now be identical for guaranteed execution at exact time

**Position Values (for Blinds):**
- `open_position` > `shading_position` > `ventilate_position` > `close_position`
- All positions must be unique (considering tolerance)
- Example: 100% > 25% > 30% > 0%

**Position Values (for Awnings):**
- `close_position` > `shading_position` > `open_position`
- Example: 100% > 75% > 0%

**Shading Thresholds:**
- `shading_azimuth_start` < `shading_azimuth_end`
- `shading_elevation_min` < `shading_elevation_max`
- `shading_sun_brightness_start` > `shading_sun_brightness_end`

**Binary Sensors:**
- `resident_sensor` must be on/off/true/false (binary)
- Contact sensors must be binary sensors

---

### Q: What is Drive Time and how should I configure it?

**A:** **Drive Time** is the duration your cover needs to move from fully closed to fully open (or vice versa).

**How to configure:**
1. Manually time how long your cover takes to move completely
2. Round up slightly (add 5-10 seconds buffer)
3. Default: 90 seconds

**Why it matters:**
- Used to recognize manual control vs. automation-triggered movement
- Prevents CCA from reacting to its own commands
- Too short: Manual changes might be missed
- Too long: Response to manual changes is delayed

**Recommendation:** Rather round up than be too precise!

---

### Q: Can I use CCA with covers that don't have current_position?

**A:** Yes! Since version 2025.12.22, CCA supports alternative position sources:

**Position Source Options:**
1. **Standard `current_position`** (default) - Most covers use this
2. **Alternative `position` attribute** - Some integrations use this instead
3. **Custom position sensor** - Use any external sensor

**When to use alternatives:**
- Your cover doesn't show positions in CCA
- Manual changes aren't detected properly
- You have custom position tracking sensors
- Non-standard cover integrations

**Configuration:** Navigate to "Cover Position Settings" → "Position Source Type"

---

### Q: Why is my automation not working even though all conditions are met?

**A:** Common causes:

**1. Once-per-day restrictions:**
- Check "Behavior Customization" options
- "Open/Close/Shade only once per day" might be active
- Restarting Home Assistant resets daily counters

**2. Manual override active:**
- Check if manual detection is blocking automation
- Reset manual override or wait for timeout

**3. Incomplete configuration:**
- Use the [Configuration Validator](https://hvorragend.github.io/ha-blueprints/validator/)
- Check for typos and missing parameters

**4. Entity states:**
- Verify all sensors return valid values (not "unknown" or "unavailable")
- Check sun.sun integration is enabled

---

## Time & Schedule Control

### Q: What's the difference between "Early" and "Late" times?

**A:** 
**Early Time (time_up_early / time_down_early):**
- Earliest time when cover CAN move
- Movement only happens if environmental conditions are met (brightness, sun elevation)
- Example: "Open earliest at 06:00 if sun is up"

**Late Time (time_up_late / time_down_late):**
- Latest time when cover MUST move
- Guaranteed execution regardless of conditions (fallback)
- Example: "Open by 08:00 even if cloudy"

**Special Case - Identical Times (NEW in 2025.12.22):**
Set both to the same time for guaranteed execution:
```yaml
time_up_early: "07:00:00"
time_up_late: "07:00:00"   # Opens exactly at 07:00, no environmental checks
```

**Migration Guide:**
- **Fixed timing (no early trigger):** Set both Early and Late to same value
- **Flexible timing:** Keep Early before Late, enable Brightness/Sun Elevation

---

### Q: How does Calendar Integration work?

**A:** Calendar mode replaces traditional time inputs with visual, family-friendly scheduling:

**Setup:**
1. Select "Time Control Configuration" → "Use a Home Assistant calendar"
2. Choose your calendar entity
3. Configure event titles (default: "Open Cover" and "Close Cover")

**How to use:**
- Create calendar events with configured titles
- Event start time = earliest action time
- Event end time = latest action time
- Works like Early/Late time windows

**Example Schedule:**
```
Monday-Friday: "Open Cover" 06:00-20:00
Saturday-Sunday: "Open Cover" 08:00-22:00
Vacation Week: "Close Cover" all day (keeps closed)
```

**Benefits:**
- Visual planning
- Easy exceptions (holidays, vacations)
- Family-friendly (anyone can adjust)
- No automation reload needed
- Different schedule per day

---

### Q: Can I use both time inputs and calendar?

**A:** No, choose one mode:
- **Time input mode:** Traditional configuration with Early/Late times
- **Calendar mode:** Calendar-based scheduling
- **Disabled mode:** No time-based triggers (sun/brightness only)

Switching modes: Go to "Time Control Configuration" and select your preferred option.

---

### Q: How do workday sensors work?

**A:** Workday sensors enable different schedules for workdays vs. non-workdays (weekends, holidays):

**Configuration:**
- **Workday Today:** Used for opening times
- **Workday Tomorrow:** Used for closing times (optional)

**Why Workday Tomorrow?**
- Close covers earlier on Sunday if Monday is a workday
- Respects school schedules (early bed on school nights)

**Recommendation:** Use the [Workday Integration](https://www.home-assistant.io/integrations/workday/)

**Example:**
```yaml
# Monday-Friday (workday)
time_up_early: 06:00
time_up_late: 07:00

# Saturday-Sunday (non-workday)
time_up_early_non_workday: 08:00
time_up_late_non_workday: 09:00
```

---

## Position Settings

### Q: What is Position Tolerance and how should I set it?

**A:** Position Tolerance is the acceptable variance when comparing cover positions.

**Purpose:**
- Accounts for imprecise position reporting
- Prevents unnecessary movements for small differences
- Example: Target 100%, Actual 98% → Within tolerance, no movement needed

**Recommended Values:**
- **Precise covers (motors with encoders):** 2-5%
- **Standard covers:** 5-10%
- **Less precise covers:** 10-15%

**Important:** All position values must remain unique even with tolerance applied!

**Example with 5% tolerance:**
```yaml
Open Position: 100%  # Range: 95-100%
Shading Position: 25%  # Range: 20-30%
Close Position: 0%  # Range: 0-5%
# All ranges non-overlapping ✅
```

---

### Q: Why should positions be unique?

**A:** Overlapping positions cause ambiguous state detection:

**Problem scenario:**
```yaml
Ventilate Position: 30%
Close Position: 25%
Position Tolerance: 10%
# Ventilate range: 20-40%
# Close range: 15-35%
# OVERLAP at 20-35%! ❌
```

**Result:** CCA can't determine if cover is ventilating or closing!

**Solution:** Keep positions clearly separated considering tolerance:
```yaml
Ventilate Position: 30%
Close Position: 0%
Position Tolerance: 5%
# Ventilate range: 25-35%
# Close range: 0-5%
# No overlap! ✅
```

**Use the validator:** [Configuration Validator](https://hvorragend.github.io/ha-blueprints/validator/) checks for overlaps!

---

### Q: What positions should I not use?

**A:** 
**For Ventilation Position:**
- ❌ Avoid exactly 100% - Use 99% instead
- Reason: May conflict with Open Position detection
- Also note position tolerance implications

**For Shading Position:**
- Must be unique (not matching any other position)
- Must be between Open and Close positions
- Consider tolerance when choosing values

---

## Cover Types (Blinds vs. Awnings)

### Q: What's the difference between Blind and Awning mode?

**A:** 

**Blinds/Roller Shutters (Traditional):**
- 0% = Closed (fully down)
- 100% = Open (fully up)
- Shading uses lower positions (e.g., 25% = partially down)
- Logic: Higher percentage = more open

**Awnings/Sunshades (Inverted):**
- 0% = Retracted (closed/stored)
- 100% = Extended (fully out)
- Shading uses higher positions (e.g., 75% = extended for shade)
- Logic: Higher percentage = more extended

**CCA automatically adapts:** Just select your cover type, and all position logic adjusts automatically!

---

### Q: Can I use CCA for awnings?

**A:** Yes! Full awning support since version 2025.12.22:

**What's supported:**
- ✅ Inverted position logic
- ✅ Sun shading (extends for shade)
- ✅ Force functions
- ✅ Manual override detection
- ✅ Time-based control
- ✅ Calendar integration

**Not supported for awnings:**
- ❌ Ventilation mode (doesn't make sense for awnings)
- ❌ Tilt position control (awnings don't tilt)

**Configuration:**
```yaml
Cover Type: Awning / Sunshade
Open Position: 0%     # Retracted
Shading Position: 75% # Extended for shade
Close Position: 100%  # Fully extended
```

---

### Q: What if I have both blinds and awnings?

**A:** Create separate automations:
- One automation per cover (recommended anyway)
- Each automation configured with correct cover type
- Different position values per automation

---

## Sun Shading & Sun Protection

### Q: What's the difference between Sun Elevation and Sun Protection?

**A:** These are **two completely different features**:

**Sun Elevation (☀️):**
- Controls **WHEN** cover opens/closes
- Based on sunrise/sunset timing
- Think: "Follow the sun's daily cycle"
- Example: Open when sun rises, close when sun sets

**Sun Protection/Shading (🥵):**
- Controls **HOW MUCH** cover closes when sun hits window
- Based on direct sunlight hitting the window
- Think: "React to sun shining on window"
- Example: Partial close at midday to block heat

**Example of a summer day:**
```
06:00 - Sun Elevation triggers opening (sun rose)
07:00 - Time-based opening (but already open)
12:00 - Sun Protection activates (sun hits window → partial close)
18:00 - Sun Protection ends (sun moved away → opens again)
21:00 - Sun Elevation triggers closing (sun set)
```

---

### Q: How do shading start conditions work?

**A:** Since version 2025.12.22, CCA uses flexible **AND/OR logic**:

**AND Conditions (Required):**
- ALL selected conditions must be true
- If ANY fails, shading won't start
- Use for critical conditions

**OR Conditions (Optional Boosters):**
- AT LEAST ONE must be true
- Useful for redundant sensors
- Use for alternative triggers

**Example Configurations:**

**Conservative (all must be perfect):**
```
AND: Azimuth, Elevation, Brightness, Temp1, Temp2
OR: (none)
Result: Shading only when everything is perfect
```

**Flexible (sun position + temperature):**
```
AND: Azimuth, Elevation
OR: Brightness, Temp1, Temp2
Result: Sun must be in range + (bright OR warm)
```

**Aggressive (sun only, temperature optional):**
```
AND: Azimuth
OR: Elevation, Brightness, Temp1, Forecast
Result: Sun in range + at least one other condition
```

---

### Q: What conditions can I use for shading?

**A:** Available shading conditions:

1. **Sun Azimuth** - Sun's horizontal angle (e.g., 95° to 265°)
2. **Sun Elevation** - Sun's height in sky (e.g., 25° to 90°)
3. **Brightness** - Light sensor reading (e.g., > 35,000 lux)
4. **Temperature Sensor 1** - Indoor temp (e.g., > 23°C)
5. **Temperature Sensor 2** - Outdoor temp (e.g., > 28°C)
6. **Forecast Temperature** - Predicted max temp (e.g., > 30°C)
7. **Weather Conditions** - Current/forecast conditions (e.g., sunny, clear)

**Each condition can be:**
- ✅ Enabled individually
- ✅ Placed in AND or OR list
- ✅ Configured with hysteresis to prevent flickering

---

### Q: What does "Pending" status mean?

**A:** "Pending" means conditions are actively being evaluated:

**Shading Start Pending:**
- Initial conditions met
- Waiting for stable readings (waiting time)
- Periodic re-checking if configured
- Will execute when conditions remain stable

**Shading End Pending:**
- End conditions detected
- Waiting for stable readings (waiting time)
- Ensures changes aren't temporary
- Will execute when conditions remain invalid

**Why pending?**
- Prevents rapid cycling from brief condition changes
- Protects motor from excessive wear
- Ensures stable weather before reacting

**Adjust if needed:**
- "Shading Start - Waiting Time" (default: 300s)
- "Shading End - Waiting Time" (default: 300s)
- "Maximum duration for retry" (timeout settings)

---

### Q: How does hysteresis work?

**A:** Hysteresis prevents rapid on/off cycling near threshold values by creating two different thresholds:

**Example with Temperature:**
```
Threshold: 25°C
Hysteresis: 2°C

Activation threshold: 25°C + 2°C = 27°C
Deactivation threshold: 25°C - 2°C = 23°C

Behavior:
- Temperature rises to 27°C → Shading starts
- Temperature drops to 26°C → Shading continues (still above 23°C)
- Temperature drops to 25°C → Shading continues (still above 23°C)
- Temperature drops to 22°C → Shading ends
```

**Benefits:**
- Prevents flickering
- Reduces motor wear
- More stable behavior
- Works with temperature, brightness, and forecast

**Recommended Values:**
- **Temperature:** 1-3°C (default: 1.5°C)
- **Brightness:** 5000-10000 lux
- **Set to 0 to disable**

---

### Q: Why isn't my sun shading working?

**A:** Common issues:

**1. Inaccurate Weather Forecast:**
- Forecast shows "cloudy" but it's actually sunny
- Solution: Don't rely solely on forecast conditions
- Test with direct sensors (brightness, temperature)

**2. Incorrect Azimuth/Elevation:**
- `shading_azimuth_start` must be < `shading_azimuth_end`
- Check your window's actual sun exposure
- Use sun position card or developer tools

**3. Waiting Time Too Long:**
- Default 300 seconds (5 minutes)
- Conditions might change before activation
- Reduce "Shading Start - Waiting Time" if needed

**4. Missing Sensors:**
- Verify all configured sensors are available
- Check for "unknown" or "unavailable" states
- `sun.sun` must be enabled

**5. Time Window:**
- Shading only works within configured time window
- Check `time_up_early` to `time_down_late` range

**6. Manual Override Active:**
- Manual changes block automation
- Reset override or wait for timeout

**Debugging:** Use [Traces](#how-to-use-traces-effectively) to see exactly why conditions aren't met!

---

### Q: Can I use only forecast-based shading without sun position?

**A:** Yes! Since version 2025.12.22, "Independent Shading via Temperature Comparison" allows this:

**Enable in "Sun Shading - Configuration":**
```yaml
☑ Independent Shading via Temperature Comparison
```

**How it works:**
- Shading starts based solely on temperature
- Ignores other conditions (brightness, sun position)
- Useful for early morning shading based on forecast

**Example:**
```
06:00 - Forecast shows 35°C max today
06:00 - Shading activates immediately (forecast > threshold)
      - Cover stays in shading position all day
      - No need to wait for sun to hit window
```

**Use cases:**
- Heat wave protection
- Energy saving (AC reduction)
- Prevent room from heating up

---

### Q: How do I configure forecast-based shading?

**A:** Two methods available:

**Method 1: Weather Entity (Recommended)**
```yaml
Forecast Weather Entity: weather.home
Forecast Source: Use the daily weather forecast service
Forecast Temperature Value: 30°C
```

**Method 2: Direct Temperature Sensor (Alternative)**
```yaml
Direct Temperature Sensor: sensor.forecast_temperature_max
Forecast Temperature Value: 30°C
```

**Priority:** Temperature sensor takes priority if both configured

**Benefits of sensors:**
- Faster updates (no API calls)
- Better performance
- Direct values

**Benefits of weather entity:**
- Can check weather conditions
- More integration options
- Standard method

---

## Ventilation & Contact Sensors

### Q: How does the ventilation feature work?

**A:** Ventilation mode reacts to window/door contacts:

**Tilted Window (Partial Ventilation):**
- Cover moves to "Ventilate Position"
- Allows air flow while maintaining privacy
- Optional lockout protection

**Fully Opened Window:**
- Cover opens completely
- **Always has lockout protection**
- Prevents accidental closure

**Window Closed:**
- Cover returns to previous state:
  - Was shading → Returns to shading
  - Was open → Returns to open
  - Was closed → Returns to closed

**Configuration:**
```yaml
Contact Sensor For Open Window: binary_sensor.window_opened
Contact Sensor For Tilted Window: binary_sensor.window_tilted
```

**Important:** Don't use the same sensor for both!

---

### Q: What is lockout protection?

**A:** Lockout protection prevents covers from closing while windows are open, avoiding:
- Locking yourself out
- Damaging window mechanisms
- Trapping cords/objects

**When it's active:**
- Window fully opened → **Always protected**
- Window tilted → Configurable per scenario

**Configurable for tilted windows:**
```yaml
Lockout Protection Options:
☑ When closing the cover
☑ When starting sun shading
☑ When sun shading ends
```

**Behavior with lockout:**
- Closing prevented → Cover stays up or moves to ventilation position
- Status saved in helper for later execution

---

### Q: Why do I need two contact sensors?

**A:** To differentiate between tilted (partial ventilation) and fully opened (full ventilation + lockout):

**Tilted sensor:**
- Detects window in tilt position
- Moves to ventilation position
- Optional lockout protection

**Opened sensor:**
- Detects fully opened window/door
- Moves to fully open position
- **Mandatory lockout protection**

**Can't I use one sensor?**
- Not directly - binary sensors are on/off
- Three-way sensors require template conversion
- See [forum example](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539/593)

---

### Q: What is "Contact Trigger Delay" and why increase it?

**A:** Contact Trigger Delay prevents race conditions when multiple sensors change simultaneously:

**The Problem:**
```
00:00.000 - Window sensor: off → on
00:00.005 - Lock sensor: off → on (5ms later)
00:00.002 - First trigger fires
00:00.005 - Second trigger blocked (mode: queued)
Result: Lockout sensor change lost! ❌
```

**The Solution (Delay = 2 seconds):**
```
00:00.000 - Window sensor: off → on
00:00.005 - Lock sensor: off → on
00:02.000 - Trigger fires with both sensors in final state
Result: All changes captured! ✅
```

**Symptoms of race conditions:**
- Cover closes despite active lockout
- "max_exceeded: warning" in logs
- Inconsistent ventilation behavior

**Recommendation:**
- Default: 2 seconds (usually sufficient)
- Multiple sensors changing together: 3-5 seconds
- Check logs for "max_exceeded" warnings

**Fixed in version 2025.12.22:** Switched to `mode: queued` for better handling

---

### Q: Can I use ventilation without lockout protection?

**A:** Yes, lockout protection is optional for tilted windows:

**Disable for tilted position:**
```yaml
Lockout Protection Options:
☐ When closing the cover (unchecked)
```

**Behavior without lockout:**
- Window tilted → Cover moves to ventilation position
- Close time arrives → Cover closes to close position (not prevented)
- Window still tilted after close → Cover stays closed

**Use case:** Small bathroom window where lockout isn't critical

**Note:** Lockout for fully opened windows is **always active** and cannot be disabled!

---

## Manual Override & Detection

### Q: How does manual override detection work?

**A:** CCA detects when you manually adjust the cover (via switch, UI, voice control):

**Detection triggers:**
- Position change not caused by CCA
- Tilt change not caused by CCA
- Change occurs after "Drive Time" buffer period

**What happens:**
- Helper status set to "manual"
- Automation pauses for configured timeout (default: 1 hour)
- Your manual decision is respected
- After timeout, automation resumes

**Why respect manual changes?**
- You know better than automation in the moment
- Prevents annoying override fights
- Maintains user control

---

### Q: Can I ignore manual overrides for specific actions?

**A:** Yes! Configure which actions can override manual changes:

**Options in "Manual Override" section:**
```yaml
Ignore/override next automatic opening after manual changes
Ignore/override next automatic closing after manual changes
Ignore/override next automatic ventilation after manual changes
Ignore/override next automatic sun shading after manual changes
```

**Example scenario:**
- You manually close a cover for privacy
- ☑ "Ignore next automatic opening" → Cover stays closed until timeout
- ☐ "Ignore next automatic shading" → Shading still works if sun hits

---

### Q: How do I reset manual override?

**A:** Three options:

**1. Automatic timeout (default):**
```yaml
Reset Configuration: Reset after a timeout in minutes
Number of minutes: 60 (default)
```

**2. Fixed time reset:**
```yaml
Reset Configuration: Reset at a specified time
Time to reset: 00:01:00 (resets at midnight)
```

**3. No automatic reset:**
```yaml
Reset Configuration: No timed reset for manual override
```
Manual override persists until:
- You move cover to a defined position
- You restart Home Assistant
- You manually trigger reset action (if configured)

---

### Q: Why does CCA still move my cover after I manually adjusted it?

**A:** Possible causes:

**1. Drive Time too short:**
- CCA thinks the manual change is its own action
- Increase Drive Time to match actual cover movement + buffer

**2. Manual override not enabled:**
- Check "Manual Override" section is configured
- Ensure helper is created and assigned

**3. Override timeout expired:**
- Default 60 minutes
- Increase timeout if needed

**4. Position within tolerance:**
- Manual position too close to automated position
- Increase Position Tolerance or choose more distinct position

**5. Force function active:**
- Force functions override manual detection
- Disable force to restore normal behavior

---

## Resident Mode

### Q: What is the resident feature?

**A:** Resident mode keeps covers closed when someone is sleeping:

**Purpose:**
- Bedroom covers stay closed while resident is asleep
- Maintains privacy and darkness for sleep
- Prevents early morning disturbance

**How it works:**
- Binary sensor (e.g., bed occupancy, motion sensor, input_boolean)
- Sensor "on" = resident present/sleeping
- Sensor "off" = resident away/awake

**Behavior:**
- **Closing:** Immediate when resident goes to sleep
- **Opening:** Respects time window and conditions when resident wakes

---

### Q: How do I configure resident mode?

**A:** 

**1. Create or select sensor:**
```yaml
# Examples:
binary_sensor.bedroom_occupied
input_boolean.guest_sleeping
binary_sensor.motion_bedroom (inverted logic)
```

**2. Configure in CCA:**
```yaml
Resident Sensor: binary_sensor.bedroom_occupied

Resident Configuration:
☑ Enable automatic opening when resident wakes up
☑ Enable automatic closing when resident goes to sleep
☑ Allow sun protection when resident is still present
☑ Allow opening the cover when resident is still present
☐ Allow ventilation when resident is still present
```

---

### Q: Why doesn't the cover open when resident wakes up?

**A:** Fixed in version 2025.12.22! Previous versions had this bug (#174).

**Current behavior (correct):**
- Resident wakes up (sensor: on → off)
- CCA evaluates:
  - ✅ Within time window? (not after `time_down_early`)
  - ✅ Environmental conditions met? (brightness, sun)
- If yes → Cover opens
- If no → Cover stays closed

**Example:**
```
Morning scenario:
07:00 - Resident wakes up
07:00 - Time window: 06:00-08:00 ✅
07:00 - Sun is up ✅
Result: Cover opens

Evening scenario:
22:00 - Resident wakes up
22:00 - Time window: closed (after 20:00) ❌
Result: Cover stays closed (correct!)
```

---

### Q: Can I still manually control covers in resident mode?

**A:** Yes! Resident mode doesn't prevent manual control:

**Manual control always works:**
- Wall switches
- Home Assistant UI
- Voice commands
- Physical buttons

**What resident mode does:**
- Prevents **automatic** opening when resident is present
- Allows **automatic** closing when resident goes to sleep
- Respects your manual adjustments

**Optional override:**
```yaml
☑ Allow opening the cover when resident is still present
```
Enables automatic opening even if resident sensor is "on"

---

## Force Functions & Emergency Control

### Q: What are force functions?

**A:** Force functions provide immediate manual override for emergency scenarios:

**Available force functions:**
- **Force Open** - Immediately open (e.g., fire alarm, window cleaning)
- **Force Close** - Immediately close (e.g., rain, hail protection)
- **Force Ventilation** - Move to ventilation position
- **Force Shading** - Activate shading position

**How to use:**
1. Create input_boolean or use binary sensor
2. Configure in "Force Features" section
3. Turn on input_boolean when needed
4. Cover reacts immediately
5. Turn off when emergency is over

---

### Q: What is "Return to Target State After Force Disable"?

**A:** NEW in 2025.12.22! Automatic recovery after emergency:

**How it works:**
- Force function active → Cover moves to forced position
- CCA continues tracking in background: "What should cover be doing?"
- Force disabled → Cover automatically returns to target position

**Example scenario:**
```
10:00 - Normal: Cover open
12:00 - Shading active
14:00 - Heavy rain → Force Close activated
14:00 - Cover closes immediately
14:00 - Helper tracks: "Should be shading"
15:00 - Rain stops → Force Close disabled
15:00 - Cover automatically returns to shading position
18:00 - Evening close time
18:00 - Cover closes normally
```

**Configuration:**
```yaml
Return to Target State After Force Disable:
✅ Enable Automatic Return to Target State
```

**Use cases:**
- 🌧️ Rain protection
- 💨 Wind protection
- ❄️ Frost protection
- 🔥 Emergency scenarios
- 🏠 Cleaning/maintenance
- 🌡️ Extreme heat protection
- 🎬 Movie mode

---

### Q: Can multiple force functions be active simultaneously?

**A:** No! Only ONE force function can be active at a time:

**What happens with conflicts:**
- CCA checks for conflicts at runtime
- Warning logged if multiple forces active
- Last activated force wins (not recommended)

**Recommendation:**
- Use only one force at a time
- Disable previous force before activating new one
- Use automation to manage force priorities if needed

**Example automation for prioritized forces:**
```yaml
# Rain protection takes priority over wind protection
trigger:
  - platform: state
    entity_id: input_boolean.force_close_rain
    to: 'on'
action:
  - service: input_boolean.turn_off
    entity_id: input_boolean.force_open_wind
  - service: input_boolean.turn_on
    entity_id: input_boolean.force_close_rain
```

---

### Q: How long can a force function stay active?

**A:** Force functions stay active until manually disabled:

**Duration:**
- No automatic timeout
- Stays active through restarts
- Must be manually turned off

**Why no timeout?**
- Emergency situations have unpredictable duration
- User must consciously end emergency state
- Prevents unexpected behavior

**Recommendation:**
- Create automation to auto-disable based on conditions:
  ```yaml
  # Example: Disable force-close when rain stops
  trigger:
    - platform: state
      entity_id: binary_sensor.rain
      to: 'off'
      for: '00:30:00'
  action:
    - service: input_boolean.turn_off
      entity_id: input_boolean.force_close_rain
  ```

---

## Cover Status Helper

### Q: What does the Cover Status Helper store?

**A:** The helper stores comprehensive state information in JSON format:

**Main States:**

| State | Description | Values |
|-------|-------------|--------|
| `open` | Cover is open or was last opened | `a`: 0/1, `t`: timestamp |
| `close` | Cover is closed or was last closed | `a`: 0/1, `t`: timestamp |
| `shading` | Cover is in shading mode | `a`: 0/1, `t`: timestamp, `p`: pending start, `q`: pending end |
| `vpart` | Partly open for ventilation (tilted) | `a`: 0/1, `t`: timestamp |
| `vfull` | Fully open for ventilation (lockout) | `a`: 0/1, `t`: timestamp |
| `manual` | Manual operation detected | `a`: 0/1, `t`: timestamp |
| `v` | Helper version number | Number |
| `t` | Last global status change | Unix timestamp |

**Key Values:**
- `a` (active): 0 = inactive, 1 = active
- `t` (timestamp): When state was last changed
- `p` (pending): Shading start pending execution time
- `q` (pending): Shading end pending execution time

**Common State Scenarios:**

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

### Q: Can I view the helper contents?

**A:** Yes, in Developer Tools:

**Method 1: States Tab**
1. Go to Developer Tools → States
2. Find your helper (e.g., `input_text.cca_status_living_room`)
3. View current JSON content

**Method 2: Template Tab**
```yaml
{{ states('input_text.cca_status_living_room') }}
```

**Example content:**
```json
{
  "open": {"a": 1, "t": 1703250600},
  "close": {"a": 0, "t": 1703164200},
  "shading": {"a": 0, "t": 1703237000, "p": 0, "q": 0},
  "vpart": {"a": 0, "t": 1703150600},
  "vfull": {"a": 0, "t": 1703150600},
  "manual": {"a": 0, "t": 1703150600},
  "v": 5,
  "t": 1703250600
}
```

---

### Q: Common helper errors - How to fix?

**A:** 

**Problem: Helper length too short**
```
Error: JSON content truncated
Symptom: Automation doesn't work, helper shows incomplete data
Solution: Recreate helper with max: 254 characters
```

**Problem: Can I use 255 characters?**
```
Answer: Yes, 254 or 255 both work
CCA requires minimum 254
```

**Problem: Helper empty after creating automation**
```
Cause: Helper created with wrong length
Solution:
1. Delete and recreate helper with correct length
2. Wait for next trigger to refill
3. Or restart automation
```

**Problem: Can I share one helper between multiple covers?**
```
Answer: NO!
Each cover automation MUST have its own unique helper
Sharing breaks functionality completely
```

---

### Q: Can I manually edit the helper?

**A:** Not recommended, but possible for debugging:

**When it might be useful:**
- Clear "manual" status after testing
- Reset pending states
- Force specific state for debugging

**How to edit:**
1. Developer Tools → States
2. Find helper entity
3. Modify JSON carefully
4. Set new state

**Risks:**
- Invalid JSON breaks automation
- Inconsistent state causes unpredictable behavior
- CCA may overwrite immediately

**Better alternatives:**
- Use reset manual override function
- Wait for midnight reset
- Restart automation

---

## Troubleshooting

### Q: How do I use traces effectively?

**A:** Traces show exactly what happened during automation execution:

**Enable more traces (optional):**
```yaml
# In automation YAML
trace:
  stored_traces: 20  # Default: 5
```

**Viewing traces:**
1. Settings → Automations & Scenes
2. Click your CCA automation
3. Select "Traces" tab
4. Choose trace from list

**What to look for:**
- **Trigger**: Which trigger fired? (see [Trigger Overview](#trigger-overview))
- **Conditions**: Which failed? (red X marks)
- **Variables**: Current values at each step
- **Actions**: Which executed? Which skipped?

**Navigation:**
- Use arrow buttons to switch between traces
- Click steps to expand details
- Check "Changed Variables" for state changes

---

### Q: How do I download and share traces?

**A:** For support requests:

**Download trace:**
1. Open trace in Traces tab
2. Click three dots (⋮) menu
3. Select "Download trace"
4. Saves as JSON file

**Share trace (forum doesn't allow JSON):**

| Service | URL | Account Required? |
|---------|-----|-------------------|
| [Pastebin](https://pastebin.com) | ✅ For "Unlisted" | Syntax highlighting |
| [GitHub Gist](https://gist.github.com) | Optional | Public or secret |
| [Hastebin](https://hastebin.com) | No | Fast & simple |
| [0bin](https://0bin.net) | No | Encrypted |

**Pastebin example:**
1. Go to https://pastebin.com
2. Paste entire JSON content
3. Set Syntax: `json`
4. Set Exposure: `Unlisted`
5. Click "Create New Paste"
6. Share the link in forum

---

### Q: Why are my numeric triggers not firing?

**A:** Understanding Home Assistant threshold concepts:

**The Threshold Rule:**
- Triggers fire when value **crosses** threshold
- Approaching threshold is NOT enough
- Must transition from one side to other

**Example:**
```
Current brightness: 50 lux
Threshold: 75 lux
Trigger: "above 75"

Changes that DON'T fire:
- 50 → 60 (still below)
- 50 → 74 (still below)
- 60 → 70 (still below)

Changes that DO fire:
- 50 → 76 (crossed threshold!)
- 74 → 76 (crossed threshold!)
```

**Common causes:**
- Sensor never crosses threshold
- Sensor value stable at threshold
- Changes happen too slowly
- Multiple automations using same sensor

**Solutions:**
- Check sensor history in Developer Tools
- Adjust threshold closer to typical values
- Use wider threshold range (Early vs. Late times)
- Enable "for" duration if sensor fluctuates

---

### Q: Why isn't my cover moving during the time window?

**A:** Check these common issues:

**1. Environmental conditions not met:**
```yaml
# You configured:
time_up_early: 06:00
time_up_late: 08:00
Brightness: Enabled (threshold: 10000 lux)

# Current situation:
Time: 07:00 ✅
Brightness: 8000 lux ❌

Result: Cover won't move until 08:00 (late time)
```

**Solution:** Disable brightness/sun elevation for guaranteed time-based movement, OR adjust thresholds

**2. Identical Early and Late times (NEW behavior):**
```yaml
time_up_early: 07:00
time_up_late: 07:00

Result: Opens exactly at 07:00, ignores environmental conditions
```

**3. Resident sensor blocking:**
```yaml
Resident sensor: on (sleeping)
Resident Configuration: Opening NOT enabled

Result: Cover won't open automatically
```

**4. Manual override active:**
- Check helper status for "manual": true
- Reset override or wait for timeout

**5. Once-per-day restriction:**
- Cover already opened today
- Check "Behavior Customization" settings

---

### Q: How do I validate my configuration?

**A:** Use the online validator BEFORE deploying:

**🔗 [CCA Configuration Validator](https://hvorragend.github.io/ha-blueprints/validator/)**

**What it checks:**
- ✅ Parameter names and typos (with suggestions!)
- ⚠️ Deprecated parameters (with migration guide)
- 📊 Position values (blind vs. awning logic)
- 🌞 Shading condition configuration
- ⏰ Time ordering
- 📅 Calendar setup
- ℹ️ Missing parameters using defaults

**How to use:**
1. Export your automation as YAML
2. Copy entire YAML OR just the `input:` section
3. Paste into validator
4. Review results
5. Fix issues before deploying

**Benefits:**
- Instant feedback (no waiting for automation run)
- Privacy-friendly (client-side processing)
- Works offline after initial load
- Catches issues early

---

### Q: What information should I provide when requesting support?

**A:** For efficient support, include:

**Essential:**
- 🧾 **Automation YAML** (exported from HA)
- 📷 **Trace file** (especially failed runs) - [How to share](#how-do-i-download-and-share-traces)
- ✅ **Expected behavior** vs. ❌ **Actual result**
- 📝 **Steps to reproduce**

**Helpful:**
- CCA version number
- Home Assistant version
- Cover type and integration
- Relevant sensor states at time of issue

**Tips:**
- ✅ **One issue per post** - easier to track and resolve
- ✅ **Be specific** - "doesn't work" → "cover doesn't close at 22:00"
- ✅ **Include context** - recent changes, when it stopped working
- ❌ **Don't summarize** - multiple problems in one post is hard to debug

**Template:**
```markdown
**Issue:** Cover doesn't close at configured evening time

**Expected:** Cover closes at 22:00
**Actual:** Cover stays open

**Configuration:**
- CCA Version: 2025.12.22
- HA Version: 2024.10.0
- Cover: cover.living_room_blind (Shelly integration)

**YAML:** [Link to Pastebin]
**Trace:** [Link to Pastebin]

**Recent changes:** Updated CCA from 2025.08.15 yesterday
```

---

## Advanced Features

### Q: What is Dynamic Sun Elevation?

**A:** Automatically adapts sun elevation thresholds to seasons:

**The Problem:**
- Fixed thresholds don't work year-round
- Winter: Sun stays lower → opens too late
- Summer: Sun stays higher → opens too early

**The Solution:**
- Template sensors with sinusoidal interpolation
- Automatically adjusts throughout year
- Smooth transitions

**Benefits:**
- ✅ No DST adjustments needed
- ✅ Year-round optimization
- ✅ Opens/closes at consistent solar times
- ✅ Set once, works forever

**Setup Guide:**
📚 [Dynamic Sun Elevation Guide](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/DYNAMIC_SUN_ELEVATION.md)

---

### Q: What are the "Additional Conditions" used for?

**A:** Dynamic control based on external factors:

**Use cases:**

**Vacation Mode:**
```yaml
Additional Condition For Opening:
  condition: state
  entity_id: input_boolean.vacation_mode
  state: 'off'

Result: Covers stay closed during vacation
```

**Party Mode:**
```yaml
Additional Condition For Closing:
  condition: state
  entity_id: input_boolean.party_mode
  state: 'off'

Result: Covers don't close during party
```

**Maintenance Mode:**
```yaml
Additional Condition (Global):
  condition: state
  entity_id: input_boolean.maintenance_mode
  state: 'off'

Result: All automation disabled during maintenance
```

**Season-based shading:**
```yaml
Additional Condition For Shading:
  condition: template
  value_template: "{{ now().month in [6, 7, 8] }}"

Result: Shading only in summer months
```

---

### Q: Can I customize cover movement commands?

**A:** Yes! "Additional Actions" allow custom behavior:

**Available hooks:**
- Before/After Opening
- Before/After Closing
- Before/After Ventilation
- Before/After Shading Start
- Before/After Shading End
- After Manual Change
- After Override Reset

**Use cases:**

**Example 1: Notifications**
```yaml
Additional Actions After Opening:
  - service: notify.mobile_app
    data:
      message: "Living room cover opened"
```

**Example 2: Scene activation**
```yaml
Additional Actions After Closing:
  - service: scene.turn_on
    target:
      entity_id: scene.evening_lights
```

**Example 3: Custom devices**
```yaml
Additional Actions Before Shading:
  - service: light.turn_on
    target:
      entity_id: light.window_plants
    data:
      brightness: 255
```

---

### Q: What is "Prevent Default Cover Actions"?

**A:** Disables CCA's built-in cover commands:

**When to use:**
- Custom cover integration requires special commands
- Shelly devices need combined position+tilt scripts
- Homematic devices need custom service calls
- Testing without actual cover movement

**Configuration:**
```yaml
Behavior Customization:
☑ Use custom actions only

Additional Actions After Opening:
  - service: script.my_custom_cover_open
    data:
      entity_id: cover.living_room
```

**Examples:**

**Shelly combined position+tilt:**
```yaml
Additional Actions After Shading:
  - service: script.cover_position_tilt
    data:
      entity_id: cover.living_room
      position: 25
      tilt: 20
```

**Homematic combined positioning:**
```yaml
Additional Actions After Shading:
  - service: homematicip_local.set_cover_combined_position
    data:
      entity_id: cover.living_room
      position: 25
      tilt_position: 20
```

---

### Q: How does "Wait Until Idle" tilt mode work?

**A:** NEW in 2025.12.22! For Z-Wave and timing-sensitive devices:

**The Problem:**
- Some devices block tilt commands during movement
- Fixed delay doesn't work reliably
- Tilt commands get ignored

**The Solution:**
- Monitors cover state
- Waits until cover reports "open" or "closed"
- Then sends tilt command
- Timeout protection (default: 30s)

**Configuration:**
```yaml
Tilt Wait Mode: Wait Until Idle (Z-Wave devices)
Tilt Wait Timeout: 30 seconds
```

**Benefits:**
- ✅ Reliable tilt without delay guessing
- ✅ Works with Shelly Qubino Wave Shutter
- ✅ Fully backward compatible
- ✅ Timeout with warning if stuck

**When to use:**
- Tilt positions unreliable with fixed delay
- Z-Wave covers
- Devices that ignore tilt during movement
- Testing shows intermittent tilt failures

---

### Q: What are the "Behavior Customization" options?

**A:** Fine-tune automation behavior:

**Position Management:**
```yaml
☑ Don't raise cover when closing for the evening
```
Prevents opening if cover is already lower than close position

```yaml
☑ Keep shading position during evening close
```
If shading, don't lower further when closing time arrives

**Feature Control:**
```yaml
☑ Stay shaded: Don't open cover when sun shading ends
```
Keeps cover in shading position instead of opening

```yaml
☑ Keep closed: Don't open cover when ventilation ends
```
Useful for bedrooms - stays closed after ventilation

**Frequency Limits:**
```yaml
☑ Open cover only once per day
☑ Close cover only once per day
☑ Shade cover only once per day
```
Prevents repeated actions, useful during testing/debugging

**Hardware Compatibility:**
```yaml
☑ Use custom actions only
```
Disables default cover commands for custom integrations

---

## Support & Debugging

### Q: Trigger overview - What do the trigger IDs mean?

**A:** 

| Trigger ID | Function | Description |
|------------|----------|-------------|
| `t_open_1` - `t_open_6` | Cover Opening | Time, brightness, sun elevation, resident, force, calendar |
| `t_close_1` - `t_close_6` | Cover Closing | Time, brightness, sun elevation, resident, force, calendar |
| `t_calendar_event_start` | Calendar Event Start | Calendar event becomes active |
| `t_calendar_event_end` | Calendar Event End | Calendar event ends |
| `t_contact_tilted_changed` | Ventilation - Tilted | Window tilted sensor change |
| `t_contact_opened_changed` | Ventilation - Opened | Window opened sensor change |
| `t_shading_start_pending_1` - `_5` | Shading Pending | Checks azimuth, elevation, brightness, temp, forecast |
| `t_shading_start_execution` | Shading Executed | Pending time elapsed, conditions met |
| `t_shading_tilt_1` - `_4` | Shading Tilt | Elevation-based tilt adjustment |
| `t_shading_end_pending_1` - `_5` | Shading End Pending | End conditions detected |
| `t_shading_end_execution` | Shading End Executed | End pending time elapsed |
| `t_shading_reset` | Shading Reset | Midnight reset of shading status |
| `t_manual_position` | Manual Position Detection | Position changed manually |
| `t_manual_tilt` | Manual Tilt Detection | Tilt changed manually |
| `t_reset_fixedtime` | Reset Override - Fixed Time | Manual override reset at configured time |
| `t_reset_timeout` | Reset Override - Timeout | Manual override timeout expired |
| `t_force_enabled_*` | Force Enabled | Force function activated |
| `t_force_disabled_*` | Force Disabled | Force function deactivated |

**Debugging tips:**
- Look for triggers that SHOULD have fired but didn't
- Check conditions (red X = failed)
- `t_manual_*` triggers are rarely the issue - look at trigger before it
- Multiple traces of same trigger = good for comparison

---

### Q: Where can I get help?

**A:** Multiple support channels:

**Community Forum:**
- 💬 [CCA Discussion Thread](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539)
- Search existing posts first
- Post new questions with proper information
- Community members help each other

**GitHub:**
- 🐛 [Report Bugs](https://github.com/hvorragend/ha-blueprints/issues)
- ✨ [Feature Requests](https://github.com/hvorragend/ha-blueprints/issues)
- 📖 [Documentation](https://github.com/hvorragend/ha-blueprints)
- Check existing issues before creating new ones

**Documentation:**
- 📚 [Dynamic Sun Elevation Guide](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/DYNAMIC_SUN_ELEVATION.md)
- 📊 [Time Control Visualization](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/TIME_CONTROL_VISUALIZATION.md)
- 📋 [Full Changelog](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/CHANGELOG.md)

**Tools:**
- � [Configuration Validator](https://hvorragend.github.io/ha-blueprints/validator/)
- 🔍 [Trace Analyzer](https://hvorragend.github.io/ha-blueprints/trace-analyzer/) - Debug automation execution

---

### Q: How can I support the project?

**A:** Several ways to help:

**Financial Support:**
- 🙏 [PayPal Donation](https://www.paypal.com/donate/?hosted_button_id=NQE5MFJXAA8BQ)
- ☕ [Buy Me a Coffee](https://buymeacoffee.com/herr.vorragend)

**Community Contributions:**
- ⭐ Star the project on GitHub
- 📝 Improve documentation
- 🐛 Report bugs with detailed information
- 💡 Suggest features
- 🤝 Help others in forum
- 📢 Share CCA with others

**Testing:**
- 🧪 Test beta versions
- 📊 Provide feedback on new features
- 🔍 Report edge cases

---

## ✅ Troubleshooting Checklist

Before posting for support, verify these essential points:

- [ ] Cover has `current_position` attribute (or alternative source configured)
- [ ] Helper has minimum 254 characters length
- [ ] Sun entity (`sun.sun`) is enabled and working
- [ ] All required sensors are available and returning valid values
- [ ] Time values are in correct order (early < late for same action)
- [ ] Position values follow hierarchy rules (considering tolerance)
- [ ] Resident sensor (if used) is binary (on/off or true/false only)
- [ ] No multiple force functions active simultaneously
- [ ] Calendar events (if used) have correct titles
- [ ] Blueprint is version 2024.10.0 or higher
- [ ] Checked the [online validator](https://hvorragend.github.io/ha-blueprints/validator/) for configuration errors
- [ ] No typos in entity IDs or sensor names

---

## 🎓 Understanding Cover Types Details

### Blinds / Roller Shutters (Standard)

**Position Logic:**
- **0% = Fully Closed** (down)
- **100% = Fully Open** (up)
- **Intermediate positions** = Partially open

**Position Hierarchy:**
```
100% (Open)
  ↓
25% (Shading)
  ↓
30% (Ventilate)
  ↓
0% (Close)
```

**Example Configuration:**
```yaml
Cover Type: Blind / Roller Shutter
Open Position: 100%
Shading Position: 25%
Ventilate Position: 30%
Close Position: 0%
Position Tolerance: 5%
```

**Real-World Examples:**
- Roller shutters (Somfy, Shelly, Z-Wave)
- Vertical blinds
- Horizontal blinds with up/down movement
- Most integrated covers use this logic

---

### Awnings / Sunshades (Inverted)

**Position Logic:**
- **0% = Fully Retracted** (closed/stored)
- **100% = Fully Extended** (open/deployed)
- **Intermediate positions** = Partially extended

**Position Hierarchy:**
```
100% (Close)
  ↓
75% (Shading)
  ↓
0% (Open)
```

**Example Configuration:**
```yaml
Cover Type: Awning / Sunshade
Open Position: 0%
Shading Position: 75%
Close Position: 100%
```

**Real-World Examples:**
- Retractable awnings
- External sunshades
- Motorized outdoor blinds
- Terrace covers

**How CCA Adapts:**
The blueprint automatically:
- ✅ Inverts comparison logic (> becomes <)
- ✅ Adjusts position hierarchies
- ✅ Reverses open/close direction
- ✅ Makes everything transparent to end user

You simply set positions intuitively and CCA handles the rest!

---

## 📊 Complete Trigger Overview & Reference

All triggers available in CCA and their purposes:

### Time-Based Triggers

| Trigger ID | Category | Description |
|------------|----------|-------------|
| `t_open_1` | Opening | Early opening time reached |
| `t_open_2` | Opening | Late opening time reached (guaranteed if conditions didn't trigger early) |
| `t_close_1` | Closing | Early closing time reached |
| `t_close_2` | Closing | Late closing time reached (guaranteed if conditions didn't trigger early) |

### Condition-Based Triggers

| Trigger ID | Category | Description |
|------------|----------|-------------|
| `t_open_4` | Opening | Brightness above threshold maintained for configured duration |
| `t_open_5` | Opening | Sun elevation above threshold maintained for configured duration |
| `t_close_4` | Closing | Brightness below threshold maintained for configured duration |
| `t_close_5` | Closing | Sun elevation below threshold maintained for configured duration |

### Resident-Based Triggers

| Trigger ID | Category | Description |
|------------|----------|-------------|
| `t_open_6` | Opening | Resident wakes up (resident sensor changes from on to off) |
| `t_close_6` | Closing | Resident goes to sleep (resident sensor changes from off to on) |

### Calendar Triggers

| Trigger ID | Category | Description |
|------------|----------|-------------|
| `t_calendar_event_start` | Calendar | Calendar event becomes active (cover configured action starts) |
| `t_calendar_event_end` | Calendar | Calendar event ends (cover configured action ends) |

### Ventilation/Contact Triggers

| Trigger ID | Category | Description |
|------------|----------|-------------|
| `t_contact_tilted_changed` | Ventilation | Window/door tilted state changed |
| `t_contact_opened_changed` | Ventilation | Window/door fully opened state changed |

### Shading Start Triggers

| Trigger ID | Category | Description |
|------------|----------|-------------|
| `t_shading_start_pending_1` | Shading | Sun Azimuth condition evaluated |
| `t_shading_start_pending_2` | Shading | Sun Elevation condition evaluated |
| `t_shading_start_pending_3` | Shading | Brightness condition evaluated |
| `t_shading_start_pending_4` | Shading | Temperature Sensor 1 condition evaluated |
| `t_shading_start_pending_5` | Shading | Temperature Sensor 2/Forecast condition evaluated |
| `t_shading_start_execution` | Shading | Start pending time elapsed + conditions confirmed → execute shading |

### Shading Tilt Triggers

| Trigger ID | Category | Description |
|------------|----------|-------------|
| `t_shading_tilt_1` | Shading | Sun elevation < tilt threshold 1 |
| `t_shading_tilt_2` | Shading | Sun elevation < tilt threshold 2 |
| `t_shading_tilt_3` | Shading | Sun elevation < tilt threshold 3 |
| `t_shading_tilt_4` | Shading | Sun elevation < tilt threshold 4 |

### Shading End Triggers

| Trigger ID | Category | Description |
|------------|----------|-------------|
| `t_shading_end_pending_1` | Shading | Sun Azimuth out of range |
| `t_shading_end_pending_2` | Shading | Sun Elevation out of range |
| `t_shading_end_pending_3` | Shading | Brightness below threshold |
| `t_shading_end_pending_4` | Shading | Temperature Sensor 1 below threshold |
| `t_shading_end_pending_5` | Shading | Temperature Sensor 2/Forecast below threshold |
| `t_shading_end_execution` | Shading | End pending time elapsed + conditions confirmed → end shading |
| `t_shading_reset` | Shading | Midnight reset of daily shading counter |

### Manual Override Triggers

| Trigger ID | Category | Description |
|------------|----------|-------------|
| `t_manual_position` | Manual | Manual cover position change detected |
| `t_manual_tilt` | Manual | Manual tilt position change detected |

### Override Reset Triggers

| Trigger ID | Category | Description |
|------------|----------|-------------|
| `t_reset_fixedtime` | Override Reset | Manual override timeout reset at configured time (midnight or specified time) |
| `t_reset_timeout` | Override Reset | Manual override timeout expired (duration-based) |

### Force Function Triggers

| Trigger ID | Category | Description |
|------------|----------|-------------|
| `t_force_enabled_open` | Force | Force-Open activated |
| `t_force_enabled_close` | Force | Force-Close activated |
| `t_force_enabled_shade` | Force | Force-Shade activated |
| `t_force_enabled_ventilate` | Force | Force-Ventilate activated |
| `t_force_disabled_open` | Force | Force-Open deactivated → return to target |
| `t_force_disabled_close` | Force | Force-Close deactivated → return to target |
| `t_force_disabled_shade` | Force | Force-Shade deactivated → return to target |
| `t_force_disabled_ventilate` | Force | Force-Ventilate deactivated → return to target |

### Debugging with Trigger Overview

**What to look for:**
- ✅ **Did the right trigger fire?** Check trigger list for expected action
- ✅ **Did unexpected triggers fire?** May explain unwanted behavior
- ✅ **Is a trigger missing?** Check conditions in automation trace
- ✅ **Trigger fired but no action?** Problem is in conditions/actions, not trigger

**Example debugging:**
```
Problem: "Covers don't open at 07:00"

Check trace:
- ❌ t_open_1 didn't fire
- ❌ t_open_2 didn't fire
- ❌ t_open_4 didn't fire
- ❌ t_open_5 didn't fire

Likely causes: Manual override active OR time values incorrect
```

---

## 📚 Additional Resources

**Official Documentation:**
- [GitHub Repository](https://github.com/hvorragend/ha-blueprints)
- [Full Changelog](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/CHANGELOG.md)
- [Dynamic Sun Elevation Guide](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/DYNAMIC_SUN_ELEVATION.md)
- [Time Control Visualization](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/TIME_CONTROL_VISUALIZATION.md)

**Tools:**
- [Configuration Validator](https://hvorragend.github.io/ha-blueprints/validator/)

**Community:**
- [Forum Discussion Thread](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539)
- [GitHub Issues](https://github.com/hvorragend/ha-blueprints/issues)

