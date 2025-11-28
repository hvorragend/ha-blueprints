# CCA Time Control - How It Works

## 📊 Opening in the Morning
```
Time:     06:00        07:00        08:00        09:00
          ├────────────┼────────────┼────────────┤
          Early        │            Late         
          ▼            │            ▼            
          
Brightness/
Sun:      ─────────────┼────────────────────────
          Too dark     │ Bright enough          
                       │                         
                       ▼                         
                  Cover opens here               
                  (threshold reached)            

Behavior:
├─ Before 06:00 (Early): ❌ Cover stays closed
├─ 06:00-08:00:          ✅ Opens when brightness/sun > threshold
└─ After 08:00 (Late):   ✅ Opens ALWAYS (regardless of sensors)
```

## 📊 Closing in the Evening
```
Time:     16:00        18:00        20:00        22:00
          ├────────────┼────────────┼────────────┤
          Early        │            Late         
          ▼            │            ▼            
          
Brightness/
Sun:      ────────────────────────┼─────────────
          Bright enough            │ Too dark    
                                   │             
                                   ▼             
                              Cover closes       
                              (below threshold)  

Behavior:
├─ Before 16:00 (Early): ❌ Cover stays open
├─ 16:00-22:00:          ✅ Closes when brightness/sun < threshold
└─ After 22:00 (Late):   ✅ Closes ALWAYS (regardless of sensors)
```

## 🌅 Detailed Daily Overview
```
┌─────────────────────────────────────────────────────────────┐
│ MORNING - Opening Behavior                                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Brightness/                                                  │
│  Elevation     ████████████████████▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀           │
│                               ▲                               │
│  Threshold    ─────────────────┼───────────────────────      │
│                               │                               │
│  Time:     05:00    06:00    07:00    08:00    09:00         │
│            ├────────┼────────┼────────┼────────┤             │
│            │   Early│        │   Late │                       │
│            │        ▼        │        ▼                       │
│                                                               │
│  Status:   🔒 CLOSED 🔒 CLOSED 🔓 OPENS  🔓 OPEN             │
│                                                               │
│  ⚠️  Important:                                               │
│  • Before Early: No action (even if bright)                  │
│  • Early-Late: Opens when threshold exceeded                 │
│  • After Late: Opens GUARANTEED (forced if needed)           │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ EVENING - Closing Behavior                                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Brightness/                                                  │
│  Elevation  ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀████████████████████           │
│                               ▼                               │
│  Threshold    ─────────────────┼───────────────────────      │
│                               │                               │
│  Time:     16:00   18:00   20:00   22:00   23:00             │
│            ├────────┼────────┼────────┼────────┤             │
│            │  Early │        │   Late │                       │
│            │        ▼        │        ▼                       │
│                                                               │
│  Status:   🔓 OPEN   🔓 OPEN   🔒 CLOSES  🔒 CLOSED          │
│                                                               │
│  ⚠️  Important:                                               │
│  • Before Early: No action (even if dark)                    │
│  • Early-Late: Closes when below threshold                   │
│  • After Late: Closes GUARANTEED (forced if needed)          │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## 📈 Sensor Thresholds

### Brightness
```
Lux Value
  ▲
  │
  │     ╔════════════════════════╗
  │     ║  Cover OPEN            ║
8000├─────╬════════════════════════╬──── brightness_up (open)
  │     ║                        ║
  │     ║   Hysteresis Range     ║
  │     ║   (no change)          ║
  │     ║                        ║
6000├─────╬════════════════════════╬──── brightness_down (close)
  │     ║  Cover CLOSED          ║
  │     ╚════════════════════════╝
  │
  └────────────────────────────────────▶ Time

Example Configuration:
- brightness_up = 8000 lx
- brightness_down = 6000 lx
- brightness_hysteresis = 500 lx

Opens when: Brightness > 8500 lx (8000 + 500)
Closes when: Brightness < 5500 lx (6000 - 500)
```

### Sun Elevation
```
Elevation (°)
  ▲
  │
  │     ╔════════════════════════╗
  │     ║  Cover OPEN            ║
 +5├─────╬════════════════════════╬──── sun_elevation_up (open)
  │     ║                        ║
  0├─────╬────────────────────────╬──── Horizon (sunrise/sunset)
  │     ║                        ║
 -5├─────╬════════════════════════╬──── sun_elevation_down (close)
  │     ║  Cover CLOSED          ║
  │     ╚════════════════════════╝
  │
  └────────────────────────────────────▶ Time

Example Configuration:
- sun_elevation_up = +5°
- sun_elevation_down = -5°

Opens when: Sun > +5° above horizon
Closes when: Sun < -5° below horizon
```

## 🔄 Combined Behavior

### Opening (Morning)
```
┌─────────────────────────────────────────────────────────┐
│ CONDITION                    │ RESULT                   │
├─────────────────────────────────────────────────────────┤
│ Before time_up_early         │ ❌ No action             │
├─────────────────────────────────────────────────────────┤
│ After time_up_early AND      │                          │
│ (Brightness > threshold      │ ✅ Cover opens           │
│  OR                          │                          │
│  Sun > threshold)            │                          │
├─────────────────────────────────────────────────────────┤
│ After time_up_late           │ ✅ Cover opens           │
│ (REGARDLESS of sensors)      │    GUARANTEED            │
└─────────────────────────────────────────────────────────┘

⚠️  OR Logic: Only ONE sensor needs to exceed threshold!
```

### Closing (Evening)
```
┌─────────────────────────────────────────────────────────┐
│ CONDITION                    │ RESULT                   │
├─────────────────────────────────────────────────────────┤
│ Before time_down_early       │ ❌ No action             │
├─────────────────────────────────────────────────────────┤
│ After time_down_early AND    │                          │
│ (Brightness < threshold      │ ✅ Cover closes          │
│  OR                          │                          │
│  Sun < threshold)            │                          │
├─────────────────────────────────────────────────────────┤
│ After time_down_late         │ ✅ Cover closes          │
│ (REGARDLESS of sensors)      │    GUARANTEED            │
└─────────────────────────────────────────────────────────┘

⚠️  OR Logic: Only ONE sensor needs to fall below threshold!
```

## 🎯 Practical Examples

### Example 1: Winter Morning (dark for long time)
```
Configuration:
- time_up_early: 06:00
- time_up_late: 08:00
- brightness_up: 8000 lx

Timeline:
06:00 ─ Still dark (5000 lx) ──────────────── ❌ Stays closed
06:30 ─ Still dark (6000 lx) ───────────────── ❌ Stays closed
07:00 ─ Getting brighter (7000 lx) ──────────── ❌ Stays closed
07:45 ─ Bright enough! (8500 lx) ─────────────► ✅ OPENS!
08:00 ─ (Would have opened latest at this time)

💡 Advantage: Waits for sufficient brightness,
             but opens latest at 08:00
```

### Example 2: Summer Evening (bright for long time)
```
Configuration:
- time_down_early: 18:00
- time_down_late: 22:00
- sun_elevation_down: -5°

Timeline:
18:00 ─ Sun still high (+15°) ────────────── ❌ Stays open
19:00 ─ Sun descending (+5°) ───────────────── ❌ Stays open
20:00 ─ Sun at horizon (0°) ─────────────────── ❌ Stays open
20:45 ─ Sun below horizon (-6°) ──────────────► ✅ CLOSES!
22:00 ─ (Would have closed latest at this time)

💡 Advantage: Uses daylight optimally,
             but closes latest at 22:00
```

### Example 3: Cloudy Day
```
Configuration:
- time_up_early: 06:00, time_up_late: 08:00
- brightness_up: 8000 lx
- sun_elevation_up: +5°

Timeline:
06:30 ─ Cloudy, but sun above horizon:
        • Brightness: 6000 lx (❌ too dark)
        • Elevation: +8° (✅ high enough)
        ────────────────────────────────────► ✅ OPENS!
        
💡 Advantage: OR logic ensures opening,
             even when brightness reduced by clouds
```

## ⚙️ Recommended Configurations

### Conservative (safe, opens/closes later)
```yaml
# Morning
time_up_early: "07:00"
time_up_late: "08:30"
brightness_up: 10000  # Very bright
sun_elevation_up: 10  # Sun already higher

# Evening  
time_down_early: "17:00"
time_down_late: "21:00"
brightness_down: 8000  # Still relatively bright
sun_elevation_down: 5  # Sun still above horizon
```

### Balanced (Standard)
```yaml
# Morning
time_up_early: "06:00"
time_up_late: "08:00"
brightness_up: 8000
sun_elevation_up: 0  # Sunrise

# Evening
time_down_early: "18:00"
time_down_late: "22:00"
brightness_down: 6000
sun_elevation_down: 0  # Sunset
```

### Aggressive (maximize daylight usage)
```yaml
# Morning
time_up_early: "05:30"
time_up_late: "07:00"
brightness_up: 5000  # Already at dawn
sun_elevation_up: -6  # Civil twilight

# Evening
time_down_early: "19:00"
time_down_late: "23:00"
brightness_down: 3000  # Only when dark
sun_elevation_down: -6  # Civil twilight
```

## ❓ Frequently Asked Questions (FAQ)

### Q: Why doesn't the cover open at time_up_early?

**A:** This is normal! `time_up_early` is the **earliest possible** time. The cover opens when:
- It's after `time_up_early` AND
- The sensors (brightness OR sun elevation) exceed the threshold

**Guaranteed opening** only happens at `time_up_late`!

---

### Q: The cover closes too late in the evening

**A:** Check the following:
1. **Thresholds too low?** 
   - Increase `brightness_down` (e.g., from 5000 to 7000 lx)
   - Increase `sun_elevation_down` (e.g., from -5° to 0°)

2. **Early time too late?**
   - Set `time_down_early` earlier (e.g., from 19:00 to 18:00)

3. **Late time as safety net:**
   - Set `time_down_late` to your desired latest time

---

### Q: How does hysteresis work?

**A:** Hysteresis prevents "flapping" (constant opening/closing):
```
Without Hysteresis (BAD):
Threshold: 7000 lx
Brightness fluctuates: 6900 → 7100 → 6900 → 7100
Result: Opens, closes, opens, closes... 😵

With Hysteresis (GOOD):
Threshold: 7000 lx, Hysteresis: 500 lx
Opens at: > 7500 lx
Closes at: < 6500 lx
Brightness fluctuates: 6900 → 7100 → 6900 → 7100
Result: Stays closed (below 7500 lx) ✅
```

---

### Q: What does "OR logic" for sensors mean?

**A:** Only **ONE** of the enabled sensors needs to reach the threshold:
```
Brightness Sensor: ✅ Active (above threshold)
Sun Elevation Sensor: ❌ Not yet (below threshold)
────────────────────────────────────────────
Result: ✅ Cover opens anyway!

Advantage: Clouds can reduce brightness, but 
          sun elevation still indicates "daytime".
```

---

### Q: When should I adjust Early/Late times?

**A:** 

**Adjust Early time:**
- ⏰ Set EARLIER if: Cover should be able to react sooner
- ⏰ Set LATER if: Too early actions are disturbing (e.g., bedroom)

**Adjust Late time:**
- ⏰ Set EARLIER if: Guaranteed open/close desired sooner
- ⏰ Set LATER if: More time for sensor-based control wanted

**Rule of thumb:**
```
Early: Earliest sensible time
Late: Latest acceptable time
Difference: 1-2 hours optimal
```

---

## 🎓 Advanced Concepts

### Schedule Helper vs. Fixed Times
```
┌────────────────────────────────────────────────────────┐
│ FIXED TIMES (time_up/down_early/late)                  │
├────────────────────────────────────────────────────────┤
│ Pro:  • Simple configuration                            │
│       • Workday/non-workday distinction possible       │
│ Con:  • Same times every day (per weekday type)        │
│       • Changes only in blueprint config               │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│ SCHEDULE HELPER (time_schedule_helper)                 │
├────────────────────────────────────────────────────────┤
│ Pro:  • Individual times per weekday                    │
│       • Changes without blueprint restart              │
│       • Graphical calendar view in HA                  │
│ Con:  • More complex to configure                       │
│       • Fixed times still needed as fallback           │
└────────────────────────────────────────────────────────┘

Recommendation: Start with fixed times, later expand to
               Schedule Helper if needed
```

---

## 🛠️ Troubleshooting

### Problem: Cover doesn't open/close
```
Checklist:
☐ Automation enabled?
☐ Helper correctly configured? (254 characters!)
☐ Sensors providing valid values?
☐ Time windows correct? (Early < Late)
☐ Thresholds realistic?
☐ Triggers visible in Home Assistant log?
☐ Manual override active? (check helper status)

Debug tip: 
Execute automation manually → Enable config check
```

### Problem: Too frequent opening/closing
```
Solution:
1. Increase hysteresis:
   • brightness_hysteresis: 0 → 1000
   • Prevents reaction to small fluctuations

2. Increase wait times:
   • brightness_time_duration: 30s → 120s
   • sun_time_duration: 30s → 120s

3. Widen threshold gap:
   • Larger difference between up/down values
```

### Problem: Time control ignored
```
Possible causes:
1. ❌ Time Control = "disabled" set
   → Enable time_control_input or schedule

2. ❌ Resident sensor blocking
   → Check resident_sensor status

3. ❌ Force trigger active
   → Check force entities (should all be "off")

4. ❌ Manual override active
   → Wait for reset or manual reset
```

---

## 📚 Related Topics

- 🌞 **Sun Shading:** More complex logic with azimuth/elevation
- 💨 **Ventilation Mode:** Window contact integration
- 🔒 **Lockout Protection:** Protection against unwanted closing
- 🎯 **Manual Override:** Intelligent detection of manual interventions

---

*This documentation refers to CCA Version 2025.11.26*
