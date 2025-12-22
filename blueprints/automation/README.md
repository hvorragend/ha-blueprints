# ☀️ Cover Control Automation (CCA)

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://community-assets.home-assistant.io/original/4X/d/7/6/d7625545838a4970873f3a996172212440b7e0ae.svg
)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fhvorragend%2Fha-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fcover_control_automation.yaml)

🔗 [Community-Link](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539)  | 🔗 [Full Changelog on Github](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/CHANGELOG.md)  | 🔗 [Older Changelog (Archiv)](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/CHANGELOG_OLD.md)

**If you would like to support me or say thank you, please click here:**

🙏 [PayPal Donation](https://www.paypal.com/donate/?hosted_button_id=NQE5MFJXAA8BQ) |  🙏 [Buy me a coffee](https://buymeacoffee.com/herr.vorragend)


## 🔥 FEATURES

1. **Opening and Closing**: Automatically opens and closes roller shutters based on brightness, sun elevation, and within specified time windows.
2. **Ventilation Feature**: Supports two-way sensors for ventilation, allowing for partial opening to ventilate the room.
3. **Resident Feature**: Keeps the cover closed if a resident is detected as asleep, ensuring comfort and privacy.
4. **Drive Delay**: Offers both fixed and random delays for driving the covers, providing flexibility in operation.
5. **Trigger Waiting Time**: Configurable waiting time for triggers to avoid rapid, unnecessary movements.
6. **Position Tolerance**: Adjustable tolerance for cover positions to account for minor discrepancies in cover movement.
7. **Dynamic Conditions**: Features can be activated or deactivated based on dynamic conditions such as:
   - **Vacation Mode**: Keeps covers closed during vacations.
   - **Party Mode**: Prevents covers from closing during parties.
   - **Shading Boolean**: Controls shading activation and deactivation.
   - **Maintenance Mode**: Suspends cover control during maintenance or cleaning.
8. **Manual Override Detection**: Detects manual overrides and adjusts automation to prevent conflicts.
9. **Time-Based Control**: Configures cover control based on workdays and non-workdays, allowing different schedules.
10. **Sun Elevation-Based Control**: Adjusts cover positions based on the sun's elevation to optimize natural light and heat.
11. **Brightness-Based Control**: Uses ambient brightness levels to manage cover positions, enhancing energy efficiency.
12. **Position Management**: Manages multiple positions for different states such as open, close, ventilate, and shading. Added the option to save the current status in a helper. This has the advantage that the roller blind can also be in other positions and the automation can still be executed. And manual interventions are not constantly overridden with every trigger.
13. **Sun Shading / Sun Protection**: Extensive automatic sun shading with many different setting options: Sun azimuth, Sun elevation, Solar irradiation/Light intensity/Illuminance,  Weather Conditions, Temperature sensors (compare thresholds for indoor and/or outdoor sensors), weather forecast comparison

## ❓ FAQ

### General Questions

- **What are the minimum requirements for using the CCA Blueprint?**
   - The cover/shutter must have a `current_position` attribute.
   - Shutters need to be properly integrated into Home Assistant.
   - The `sun.sun` entity must be enabled and working correctly.
   - Minimum required version of Home Assistant: **2024.6.0**

### Configuration Questions
- **How do I set up the basic position settings?**
   - Set `open_position` (typically 100).
   - Set `close_position` (typically 0).
   - Configure `drive_time` (default 90 seconds).

- **What are the important configuration rules?**
   - Ensure time settings follow logical order (early times before late times).
   - Position values should be hierarchical: `open_position > ventilate_position > close_position`.

### Feature Questions
- **How does the ventilation feature work?**
   - Supports two-way sensors for partial opening to ventilate the room.
   - Or use the sensors for lock-out protection

- **What is the resident feature?**
   - Keeps the cover closed if a resident is detected as asleep.
   
- **How can I detect manual overrides?**
   - The blueprint includes a feature to detect manual overrides and adjust automation accordingly.

- **How do the shading start conditions work?**
   - If multiple criteria (e.g. temperature sensors and/or azimuth and/or elevation) are defined, shading will not occur until all criteria are met.

- **How can I use additional conditions like vacation mode or party mode?**
   - Activate vacation mode to keep covers closed during vacations.
   - Use party mode to prevent covers from closing during parties.

### Advanced Questions
- **Can I configure the blueprint based on sun elevation and brightness?**
    - Yes, the blueprint allows adjustments based on sun elevation and ambient brightness levels.

- **How do I manage multiple positions for different states?**
    - The blueprint supports managing positions for open, close, ventilate, and shading.

## 📺 SCREENSHOTS

![image](https://github.com/user-attachments/assets/c213d5ec-f1d4-4830-8e4d-43bc7f46cf44)

![image](https://github.com/user-attachments/assets/e89777fc-73e8-4d79-a01e-e85e36c3450c)

## ❓ Troubleshooting Questions

The CCA blueprint is powerful but requires precise configuration. Below are typical errors users encounter:

### Incomplete or Invalid Configuration
- Time ranges must be logically ordered (e.g., `time_up_early` < `time_up_late`).
- Azimuth values (e.g., `shading_azimuth_start` and `shading_azimuth_end`) must form a valid range.
- Missing required fields can cause the automation to fail silently.

👁️ More important configuration notes
- `time_up_early` should be earlier `than time_up_late`
- `time_up_early_non_workday` should be earlier than `time_up_late`
- `time_down_early` should be earlier than `time_down_late`
- `shading_azimuth_start` should be lower than `shading_azimuth_end`
- `shading_elevation_min` should be lower than `shading_elevation_max`
- `shading_sun_brightness_start` should be higher than `shading_sun_brightness_end`
- `open_position` should be higher than `closed_position`
- `open_position` should be higher than `ventilate_position`
- `closed_position` should be lower than `ventilate_position`
- `shading_cover_position` should be higher than `closed_position`
- `shading_cover_position` should be lower than `open_position`
- `resident` is only allowed to be on/off/true/false
- cover must have a `current_position` attribute


### Why is my trigger sequence not executed even though all conditions are met?

- This is often because the blueprint is configured so that certain actions can only be executed once a day. Particularly in the initial phase, you try out a lot and so an action could theoretically have already been noted as executed.

### What should I do if the cover positions are not working correctly?
   - Verify your cover reports `current_position` correctly.
   - Ensure position values don’t conflict with each other.
   - Check if manual control is working properly.
   - Improper position values (e.g., `open_position` should be greater than `closed_position`). And the `shading_position` must be unique; i.e. it must not match any other values.


### Trying to Trigger the Automation Manually
- This blueprint is **not** designed for manual triggering.
- Manually clicking "Run" will not produce the expected behavior.

### Missing or Invalid Entities
- Required entities like `sun.sun`, sensors, and weather data must be available and return valid values.
- If entities return `unknown`, `unavailable`, or are missing, actions may be skipped.

### Using an Outdated Blueprint Version
- The blueprint is frequently updated.
- Re-import and review after updates.
- Check changelogs for new options or breaking changes.

--- 

## 🥵 Common Issues with Sun Protection / Sunshade Control 

###  Inaccurate Weather Forecast Blocking Activation

If you're using a weather forecast sensor (e.g., OpenWeatherMap), inaccurate "cloudy" or "partlycloudy" predictions may prevent sun shading, even when it's actually sunny.

**Tip:** Use the action `weather.get_forecasts` in the developer console and see what response your weather integration gives.

###  Incorrect Azimuth or Elevation Settings

Improper configuration of the sun’s azimuth or elevation ranges may prevent activation:

- `shading_azimuth_start` must be **less than** `shading_azimuth_end`.
- `shading_elevation_min` should reflect realistic sun elevation levels in your region and time of year.

###  Activation Delay (`shading_wait`)

The `shading_waitingtime_start` parameter defines a wait time (in seconds) between all shading conditions being met and the actual activation. 

This often causes users to think shading isn't working, especially when the sun conditions change quickly.

###  Manual Control Preventing Automation

If blinds are manually moved, the automation may stop responding unless you properly reset the manual override. Or has the automation been modified in the meantime or has Home Assistant even been restarted?

###  Grouped Covers Causing Conflicts

Grouping multiple blinds into one cover entity can lead to issues. If one blind in the group is manually closed, it may prevent the automation from moving any of them.

###  Missing or Misconfigured Sensors

Missing required entities like:

- `sun.sun` (for sun position)
- Brightness sensors
- No definition of necessary helper (e.g. `cover_status_helper`)

...can cause the sun shading logic to silently fail.

###  Time Window Misconfiguration

Shading will not activate outside the specified time range, even if all sun conditions are satisfied.

**Check:** `time_up_early` and `time_down_late` settings to ensure they include your intended shading hours.

### Problem with ending the shading
Check if the conditions for ending shading (e.g., sun elevation dropping below shading_elevation_min) are correctly configured.

---

## 🔢 Why Are My Numeric Triggers Not Firing?

### How does the threshold concept apply to the Cover Control Automation?

- In the CCA Automation, a *threshold* defines the specific brightness level at which your covers (e.g., blinds or shades) are expected to react. For example, if the threshold is set to 75, the automation will only trigger actions (such as opening or closing the covers) when the brightness value crosses that point - either by rising above or falling below it.

### Can you provide an example of how thresholds work in the CCA?

- Let’s say the brightness sensor currently reads **50**, and your CCA Automation is configured to close the covers at a threshold of **75**. If the brightness increases to **60** or even **74**, the automation will *not* fire. It only triggers once the value crosses the threshold—such as reaching **76**. Similarly, the same logic applies when the brightness is dropping below a set lower threshold.

### Why might the CCA Automation not trigger, even though I expect it to?

- If your CCA Automation isn't firing, it could be because the brightness value hasn't actually *crossed* the threshold - only approaching it isn’t enough. Automations using numeric state triggers in Home Assistant only activate when the value transitions from one side of the threshold to the other.

### What should I check if my CCA Automation isn’t working as expected?

- Start by confirming the current brightness level and compare it to your defined threshold values. Ensure that the values are actually moving across the threshold. Next, review your automation conditions to verify that all necessary criteria are being met (e.g., time of day, sun position, presence status, etc.). Lastly, consider checking the automation's trace or logs in Home Assistant to see if and when the trigger conditions are evaluated.


---

## 🧪 How to Use Traces Effectively

Traces allow you to inspect exactly what happened when an automation was run.

### Increase Stored Traces (Optional)
To store more traces, add this to the automation YAML:
```yaml
trace:
  stored_traces: 20
```

<sub>See also: https://www.home-assistant.io/docs/automation/troubleshooting/</sub>


### Providing the traces
1. Go to **Settings → Automations & Scenes**.
2. Click on the relevant CCA automation.
3. Select the **Traces** tab to view execution steps.
4. Use the arrow symbols to switch back and forth between the traces and search for the trigger (see trigger table) that should actually trigger something.
5. Please note that traces for the trigger “`t_manual_x`” are not relevant for debugging. Traces are only required in very rare cases. Then I would also point this out. These triggers are reactions to manual position changes or the attempt to recognize previous actions from the blueprint. If there are problems, then rarely with this trigger, but with the trigger directly before it.
6. Download the trace and make the file available in the thread via filehosters such as Pastebin.

#### Uploading the JSON File

Since the forum does not support uploading `.json` files directly, please use one of the following services to host your file and share the link in your post:

|Service|Link|Account Required?|Notes|
| --- | --- | --- | --- |
|[Pastebin](https://pastebin.com)|✅ For "Unlisted" pastes|Supports syntax highlighting for JSON.||
|[GitHub Gist](https://gist.github.com)|❌ Optional GitHub account|Ideal for structured files; public or secret.||
|[Hastebin](https://hastebin.com)|❌ No|Fast & simple; may expire over time.||
|[0bin](https://0bin.net)|❌ No|End-to-end encrypted; privacy-focused.||
|[file.io](https://www.file.io)|❌ No|File auto-deletes after one download.||

---

#### 🧩 Pastebin Example

1. Go to https://pastebin.com.
2. Paste your **entire JSON content**.
3. Set **Syntax Highlighting** to `json`.
4. Set **Paste Exposure** to `Unlisted`.
5. Click **“Create New Paste”**.
6. Copy the generated link and include it in your forum reply.

By providing the trace in this format, it’s much easier to identify bugs, unexpected behavior, or misconfigurations in your automation setup. Thank you!

---

## 📬 Tips for Creating Helpful Support Requests

When asking for help on the forum, include:

- 🧾 **Your automation YAML configuration** (exported instance).
- 📷 **The exported trace** (especially of failed runs).
- ✅ **Expected behavior** vs ❌ **Actual result**.
- **Tip**: Please do not summarize so many independent problems in one post. It makes support easier for me if we could focus on one possible error per post.


---

### ✅ Summary

- Set up the CCA blueprint carefully with correct values and entity references.
- Do **not** trigger it manually.
- Keep the blueprint up to date.
- Use **Traces** to debug and provide structured support requests.

---

## 🛎️ Trigger overview

|**Trigger** | **Function** | **Description**|
|--- | --- | ---|
|`t_open_1 - 6` | Cover Opening | Trigger for opening|
|`t_close_1 - 6` | Cover Closing | Trigger for closing|
|`t_contact_tilted_on` / `t_contact_opened_on` | Ventilation | Responds to the status of the window contact|
|`t_shading_start_pending_1 - 5` | Shading Pending | Checks relevant conditions (azimuth, elevation, temperature)|
|`t_shading_start_execution` | Shading Executed | Activated when conditions are met|
|`t_manual_1 - 3` | Manual Position Detection | Monitors manual changes and resets status|

---

## 📋 Cover Status Helper - Contents

The Cover Status Helper is the central control element in the latest version of the Cover Control Automation (CCA). It tracks the current state of the roller blinds.


#### Structure and Meaning of the Individual States

Each of these states is an object with at least two key values:

|**State** | **Description** | **a (active)** | **t (timestamp)**|
|--- | --- | --- | ---|
|`open` | Cover is open or was last opened | `0` / `1` | Time the open occurred|
|`close` | Cover is closed or was last closed | `0` / `1` | Time the close occurred|
|`shading` | Cover is in shading mode | `0` / `1` | Time shading activated|
|`shading.p` | Shading detected, not yet started (Pending) | `0` / `1` | End of the waiting time (for trigger)|
|`shading.q` | Time shading was actually executed (Executed) | `0` / `1` | Time executed|
|`vpart` | Partly open for ventilation (window tilted)  | `0` / `1` | Time activated|
|`vfull` | Fully open for maximum ventilation (lock-out protection) | `0` / `1` | Time intervention|
|`manual` | Manual operation detected (UI, switch, etc.) | `0` / `1` | Time intervention|
|`v` | Version of the status format | – | –|
|`t` | Timestamp of last global status change | – | Unix time|


## 🪟 Cover Status Helper - State Overview

This table provides an overview of the different states used in the Cover Status Helper.
Each row represents a specific scenario with corresponding binary values for each state variable.

|Scenario Description|`open`|`close`|`shading`|`vpart`|`vfull`|
| --- | --- | --- | --- | --- | --- |
|Cover is open|1|0|0|0|0|
|Cover is closed|0|1|0|0|0|
|Shading active, then returns to open|1|0|1|0|0|
|Cover is still closed, then moves to shading instead of fully opening|0|1|1|0|0|
|Lockout protection active when closing|0|1|0|0|1|
|Window tilted – no lockout, cover moves to ventilation position instead of closing|0|1|0|1|0|

---
