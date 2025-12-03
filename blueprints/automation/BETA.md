# 🎉 CCA 2025.12.03 BETA - The Most Powerful Update Yet! 🚀

Hey CCA Community! 👋

I'm absolutely **thrilled** to announce the **BETA release of CCA 2025.12.03** - this is hands down the most feature-packed, intelligent, and flexible version I've ever built! 🎊

After months of community feedback, debugging sessions, and countless iterations, I am ready to invite you to test the future of automated cover control. This isn't just an update - it's a **complete evolution** of what CCA can do! ✨

---

## ⚠️ **Important Beta Notice**

🔬 **This is a BETA release!** During the beta phase, all GitHub links point to the **`beta` branch**. Once testing is complete and stable, the changes will be merged to the main branch.

**Beta Blueprint URL:**
```
https://github.com/hvorragend/ha-blueprints/blob/beta/blueprints/automation/cover_control_automation.yaml
```

**Beta Documentation:**
- All guides and documentation linked below use the `beta` branch
- After stable release, links will point to `main` branch

---

## 🌟 Headline Features

### 📅 **Calendar Integration - Game Changer!**

Say goodbye to rigid time schedules! You can now use **Home Assistant calendars** for cover scheduling:

- ✅ Create "Open Cover" and "Close Cover" events in any calendar
- ✅ Different schedules for weekdays, weekends, holidays, vacations
- ✅ **Instant response** when events start/end - no automation reload needed!
- ✅ **Family-friendly** - anyone can adjust the schedule in their calendar app
- ✅ Visual planning with calendar view

**Example:** Monday-Friday 06:00-20:00 open, Saturday-Sunday 08:00-22:00 open, vacation week all day closed. Just create the events - CCA handles the rest!

This is **huge** for people who want flexible, exception-friendly scheduling without touching YAML! 🎯

---

### 🧠 **Smart State Memory & Force Return**

Ever forced your covers open for rain protection, then forgot to return them to normal? **Not anymore!**

When `enable_background_state_tracking` is enabled:
- ✅ CCA tracks what position the cover *should* be in (background state)
- ✅ Even during Force-Open/Close/Shading, the helper updates in the background
- ✅ When force ends, cover **automatically returns** to the correct target position!

**Real-world scenarios:**
- 🌧️ Rain protection → Auto-return to shading after rain stops
- 💨 Wind protection → Auto-return to scheduled state when wind calms
- ❄️ Frost protection → Auto-return to normal automation after sunrise
- 🎬 Movie mode → Auto-return to open/shading when movie ends

This is **seamless automation** - CCA now truly handles emergency scenarios and returns to normal without manual intervention! 🙌

---

### ☀️ **Flexible Shading Logic - AND/OR Condition Builder**

This is where things get **seriously powerful**! You now have **full control** over shading conditions:

**New capabilities:**
- ✅ **Separate START and END logic** - strict criteria for starting, relaxed for ending (or vice versa!)
- ✅ **AND conditions** - "ALL must be true" (e.g., sun position + brightness + temperature)
- ✅ **OR conditions** - "AT LEAST ONE must be true" (e.g., redundant temperature sensors)
- ✅ **Per-condition on/off switches** - enable/disable individual triggers independently
- ✅ **Unified retry behavior** with configurable timeouts

**Example configurations:**
```yaml
Conservative: AND(azimuth, elevation, brightness, temp) + OR(none)
Flexible: AND(azimuth, elevation) + OR(brightness, temp1, temp2)
Aggressive: AND(azimuth) + OR(brightness, temp1, forecast)
```

You can now fine-tune between conservative and aggressive sun protection **without changing sensors**! 🎨

---

### 🌡️ **Enhanced Forecast & Temperature Intelligence**

Forecast handling just got **way smarter**:

- ✅ **Dedicated inputs** - separate fields for weather entities vs. temperature sensors
- ✅ **Smart source priority** - direct sensors preferred for faster updates
- ✅ **Configurable forecast mode** - daily/hourly/live weather attributes
- ✅ **Full hysteresis** for ALL temperature paths (no more rapid cycling!)
- ✅ **Independent temperature-based shading** - start shading based on forecast alone

Now you can shade early in the morning if high temperatures are forecasted, even before the sun hits! ☀️🌡️

---

### 🖼️ **Awning & Sunshade Support**

Finally! CCA now supports **awnings and sunshades** with inverted position logic:

**Blinds/Shutters (Standard):**
- 0% = closed (down)
- 100% = open (up)
- Shading = lower positions (e.g., 25%)

**Awnings/Sunshades (Inverted):**
- 0% = retracted (closed)
- 100% = extended (open)
- Shading = higher positions (e.g., 75% extended)

Just select your cover type, and CCA handles all the logic automatically! The position comparison system works flawlessly for both types. 🎪

---

### 📈 **Dynamic Sun Elevation - Set & Forget**

No more manual adjustments for DST or seasonal changes! 🎉

**The problem:** Fixed sun elevation thresholds don't work year-round. Winter sun stays lower, summer higher.

**The solution:** Optional template sensors that automatically adapt thresholds to the season using **sinusoidal interpolation**.

**Benefits:**
- ✅ No DST adjustments needed
- ✅ Year-round optimization
- ✅ Covers open/close at **consistent solar times**
- ✅ Smooth transitions throughout the year
- ✅ Configure once, works forever!

Check out the new [Dynamic Sun Elevation Guide](https://github.com/hvorragend/ha-blueprints/blob/beta/blueprints/automation/DYNAMIC_SUN_ELEVATION.md) for setup! 📚

---

### 🔄 **Tilt Position - Wait Until Idle Mode**

Z-Wave users, this one's for you! 🎯

**The issue:** Some Z-Wave devices (like Shelly Qubino Wave Shutter) block tilt commands during motor movement, causing unreliable tilt positioning.

**The fix:** New "Wait Until Idle" mode that monitors cover state before sending tilt commands!

**Configuration:**
- **Tilt Wait Mode:** "Fixed Delay" (default) or "Wait Until Idle"
- **Tilt Wait Timeout:** Maximum wait time (default: 30s)

**Benefits:**
- ✅ Reliable tilt without manual delay tuning
- ✅ Fully backward compatible
- ✅ Timeout protection with warning logs

No more guessing delay values - CCA waits intelligently! ⏱️

---

## 🛡️ **Critical Bug Fixes**

### Contact Sensor Race Condition ⚡
**Fixed #225** - When multiple contact sensors changed simultaneously (e.g., window + lock within milliseconds), `mode: single` would block the second trigger, potentially locking users out.

**Solution:** Switched to `mode: queued` - all triggers are processed in order, none are lost! This ensures lockout protection works correctly even with rapid sensor changes. 🔒✅

### Resident Mode Fix 🛏️
**Fixed #174** - Cover remained closed when resident left room during daytime with all opening conditions met.

**Solution:** Cover now evaluates time window and environmental conditions when resident leaves. "Open immediately" now respects daytime phase (only opens before evening closing time). 🌅

---

## ⚠️ **Breaking Changes & Migration**

**Please update your configuration:**

1. **`shading_start_behavior` → `shading_start_max_duration`**
   - Old "trigger_reset" ≈ `0` (no periodic retry)
   - Old "trigger_periodic" ≈ `3600-7200` seconds (1-2 hours)

2. **Removed: `is_shading_end_immediate_by_sun_position`**
   - Use the new flexible AND/OR condition logic instead

3. **Removed: `shading_end_behavior`**
   - Covers now always return to `open_position` after shading ends
   - For awnings: This means retracted (0%)
   - For blinds: This means fully up (100%)

4. **Time Early = Time Late now supported!**
   - Both can be identical for **guaranteed** open/close at exact time
   - Previous behavior: Early time with met conditions
   - New behavior: Set both to same value for fixed time operation

---

## 🎨 **Quality of Life Improvements**

### Config Check Refactoring ✅
- **80+ validation checks** organized into **19 logical sections**
- **Enhanced error messages** with specific, actionable guidance
- **Improved formatting** for consistency and readability
- **Better debugging** - you'll know exactly what's wrong!

### Code Optimizations 🚀
- **Variables refactoring** - consolidated 80+ flag variables into maintainable dictionaries
- **Reduced duplication** - shared `ts_now` variable across actions
- **Cleaner state handling** at midnight
- **Stronger force trigger safeguards**
- **More robust JSON initialization**

---

## 📊 **Full Changelog**

Check out the complete [CHANGELOG.md](https://github.com/hvorragend/ha-blueprints/blob/beta/blueprints/automation/CHANGELOG.md) for every detail!

**Version:** 2025.12.03

---

## 🧪 **Beta Testing - I Need You!**

This is a **massive update** with fundamental changes to core logic. While I've tested extensively, **real-world scenarios are invaluable!**


---

## 📥 **Installation**

**🔬 BETA Blueprint URL:**
```
https://github.com/hvorragend/ha-blueprints/blob/beta/blueprints/automation/cover_control_automation.yaml
```

⚠️ **Important:** During beta testing, use the **`beta` branch** URL above. After stable release, the blueprint will be merged to the `main` branch.

**Installation via GitHub import:**
1. Go to Settings → Automations & Scenes → Blueprints
2. Click "Import Blueprint"
3. Paste the **beta branch URL** above
4. Confirm import

**Existing users:**
- Remove old blueprint import (main branch)
- Import beta version using URL above
- Review breaking changes before enabling new features

**Switching back to stable:**
- If you need to revert, simply re-import from the `main` branch URL
- Your configurations will remain intact

---

## 💡 **Resources**

**📖 Beta Documentation (all links use `beta` branch):**
- **Dynamic Sun Elevation Guide:** [GUIDE](https://github.com/hvorragend/ha-blueprints/blob/beta/blueprints/automation/DYNAMIC_SUN_ELEVATION.md)
- **Time Control Visualization:** [GUIDE](https://github.com/hvorragend/ha-blueprints/blob/beta/blueprints/automation/TIME_CONTROL_VISUALIZATION.md)
- **Full Changelog:** [CHANGELOG.md](https://github.com/hvorragend/ha-blueprints/blob/beta/blueprints/automation/CHANGELOG.md)

**❤️ Support Development:**
- [PayPal Donation](https://www.paypal.com/donate/?hosted_button_id=NQE5MFJXAA8BQ)
- [Buy Me a Coffee](https://buymeacoffee.com/herr.vorragend)

---

**Ready to upgrade?** Remember to use the **beta branch URL** during testing! Drop your feedback below! Let's make this the best CCA release yet! 🎉

## 🙏 **Thank You!**
